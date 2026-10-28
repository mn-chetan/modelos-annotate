/*
 * Review: the bench where a person makes the AI's labels their own. Items below the line come
 * first, least confident first. The item sits on the left (an image to draw on, or a document
 * to read); its labels sit on the right, each with accept, correct and reject. One action
 * finishes the item: Approve and next.
 */
import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, CircleAlert, Download, Loader2, Pencil, Redo2, Trash2, Undo2, X } from 'lucide-react';
import { exportLabels, routeOf, useAssets, type Annotation, type ExportFormat, type LiveAsset, type LiveProject, type Route } from '../../store';
import { navigate, projectHref } from '../../router';
import { EmptyState, PageHead, fmt, projectEyebrow } from '../shared';
import { OTHER_COLOUR, RouteChip, aiConfidence, classColours, colourStyle, decisionOf, modelName } from '../annotation-ui';
import { spansOf } from '../text/text-model';
import { useEdits, type Edits } from './useEdits';
import { ImageCanvas } from './ImageCanvas';
import { TextDoc, setDocLabel } from './TextDoc';
import '../text/text.css';
import './review.css';

type Queue = 'toReview' | 'approvedByAi' | 'all';

const EXPORTS: Record<LiveProject['kind'], [ExportFormat, string][]> = {
  boxes: [
    ['coco', 'COCO JSON'],
    ['yolo', 'YOLO'],
  ],
  spans: [['json', 'JSON']],
  document: [
    ['json', 'JSON'],
    ['csv', 'CSV'],
  ],
};

const ORDER: Route[] = ['toReview', 'approvedByAi', 'approved', 'rejected', 'failed', 'notRun'];

/** Items in review order: below the line first, least confident first. */
function inOrder(assets: LiveAsset[]) {
  return [...assets].sort((a, b) => {
    const d = ORDER.indexOf(routeOf(a)) - ORDER.indexOf(routeOf(b));
    if (d) return d;
    return (a.mean_confidence ?? 2) - (b.mean_confidence ?? 2);
  });
}

export function ReviewPage({ project: p, itemId }: { project: LiveProject; itemId?: string }) {
  const assets = useAssets(p.id);
  const [queue, setQueue] = useState<Queue>('toReview');
  const ordered = useMemo(() => inOrder((assets ?? []).filter((a) => !['notRun', 'failed'].includes(routeOf(a)))), [assets]);
  const list = ordered.filter((a) => queue === 'all' || routeOf(a) === queue);
  const asset = (itemId && ordered.find((a) => a.id === itemId)) || list[0];
  // Opening an item from elsewhere shows the queue it belongs to.
  useEffect(() => {
    if (!asset) return;
    const r = routeOf(asset);
    if (queue !== 'all' && r !== queue) setQueue(r === 'toReview' || r === 'approvedByAi' ? r : 'all');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asset?.id]);

  const waiting = ordered.filter((a) => routeOf(a) === 'toReview').length;
  const byAi = ordered.filter((a) => routeOf(a) === 'approvedByAi').length;

  const head = (
    <PageHead
      eyebrow={projectEyebrow(p)}
      title="Review"
      lede={
        waiting
          ? `${fmt(waiting)} ${waiting === 1 ? p.unit.replace(/s$/, '') : p.unit} below the ${p.line.toFixed(2)} line, least confident first. Accept what’s right, correct what isn’t.`
          : `Nothing below the line. ${fmt(byAi)} ${p.unit} were approved by the AI; you can still open any of them.`
      }
      actions={<ExportMenu project={p} />}
    />
  );

  if (!assets) {
    return (
      <div className="page review-page">
        {head}
        <p className="page-status" role="status">
          <Loader2 size={16} className="spin" aria-hidden /> Loading {p.unit}…
        </p>
      </div>
    );
  }

  if (!ordered.length) {
    return (
      <div className="page review-page">
        {head}
        <EmptyState
          project={p}
          title={`No drafted ${p.unit} yet`}
          line={`Run the AI on your ${p.unit} first. Anything it isn’t sure of lands here.`}
          actions={
            <a className="btn btn-primary" href={projectHref(p.id, 'ai')}>
              Open AI results
            </a>
          }
        />
      </div>
    );
  }

  return (
    <div className="page review-page">
      {head}
      <div className="toolbar rv-queue">
        <div className="seg" role="group" aria-label="Which items">
          {(
            [
              ['toReview', 'Below the line', waiting],
              ['approvedByAi', 'Approved by AI', byAi],
              ['all', 'All drafted', ordered.length],
            ] as [Queue, string, number][]
          ).map(([q, label, n]) => (
            <button key={q} aria-pressed={queue === q} onClick={() => setQueue(q)}>
              {label} <span className="ai-count">{fmt(n)}</span>
            </button>
          ))}
        </div>
      </div>
      {asset ? (
        <Bench key={asset.id} project={p} asset={asset} list={list.length ? list : [asset]} />
      ) : (
        <EmptyState
          project={p}
          title={queue === 'toReview' ? 'Nothing below the line' : 'Nothing here'}
          line={queue === 'toReview' ? `Every drafted ${p.unit.replace(/s$/, '')} has been decided or approved by the AI.` : 'Try another filter.'}
        />
      )}
    </div>
  );
}

function ExportMenu({ project: p }: { project: LiveProject }) {
  const [error, setError] = useState('');
  return (
    <div className="rv-export">
      <span className="rv-export-label">Export approved</span>
      {EXPORTS[p.kind].map(([f, name]) => (
        <button
          key={f}
          className="btn btn-ghost btn-sm"
          onClick={() => exportLabels(p.id, f).catch((e) => setError(e instanceof Error ? e.message : String(e)))}
        >
          <Download size={14} aria-hidden /> {name}
        </button>
      ))}
      {error ? (
        <span className="rv-export-error" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}

/** One item on the bench, with its labels and the decision. */
function Bench({ project: p, asset, list }: { project: LiveProject; asset: LiveAsset; list: LiveAsset[] }) {
  const edits = useEdits(p, asset);
  const [selected, setSelected] = useState('');
  const [drawClass, setDrawClass] = useState(p.classes[0] ?? '');
  const colours = classColours(p);
  const index = list.findIndex((a) => a.id === asset.id);
  const route = routeOf(asset);
  const go = (a?: LiveAsset) => a && navigate({ id: 'project', projectId: p.id, tab: 'review', itemId: a.id });
  const decided = route === 'approved' || route === 'approvedByAi' || route === 'rejected';

  async function finish(action: 'approve' | 'reject') {
    const ok = await edits.decide(action);
    if (!ok) return;
    const next = list.slice(index + 1).find((a) => routeOf(a) === 'toReview') ?? list.find((a) => a.id !== asset.id && routeOf(a) === 'toReview');
    if (next) go(next);
  }

  // Keys: 1–9 class, A accept, R reject, Delete remove, Ctrl/Cmd Z undo, Shift+Ctrl/Cmd Z or Ctrl Y redo.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.matches('input, select, textarea') || edits.busy || edits.loading) return;
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        if (e.shiftKey) edits.redo();
        else edits.undo();
      } else if (mod && e.key.toLowerCase() === 'y') {
        e.preventDefault();
        edits.redo();
      } else if (!mod && /^[1-9]$/.test(e.key) && p.classes[+e.key - 1] && !document.getSelection()?.toString()) {
        const name = p.classes[+e.key - 1];
        setDrawClass(name);
        if (selected) edits.update(selected, { label: name, review_status: 'edited' });
        else if (p.kind === 'document') setDocLabel(edits, asset, name);
      } else if (!mod && selected && (e.key === 'a' || e.key === 'A')) {
        edits.update(selected, { review_status: 'approved' });
      } else if (!mod && selected && (e.key === 'r' || e.key === 'R')) {
        edits.update(selected, { review_status: 'rejected' });
      } else if (selected && (e.key === 'Delete' || e.key === 'Backspace')) {
        e.preventDefault();
        edits.change(edits.rows.filter((a) => a.id !== selected));
        setSelected('');
      } else if (e.key === 'Escape') {
        setSelected('');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const statusLine = edits.loading
    ? 'Loading labels…'
    : decided && !edits.dirty
      ? route === 'rejected'
        ? 'Rejected. It won’t be exported.'
        : route === 'approvedByAi'
          ? 'Approved by the AI. Change anything and approve it again to make it yours.'
          : 'Approved. Its accepted labels are ready to export.'
      : edits.remaining
        ? `${fmt(edits.remaining)} ${edits.remaining === 1 ? 'label needs' : 'labels need'} a decision`
        : edits.rows.length
          ? 'Every label decided'
          : p.kind === 'boxes'
            ? 'No boxes. Draw any the AI missed, or approve it as empty.'
            : 'No labels. Add any the AI missed, or approve it as empty.';

  return (
    <section className="rv-bench" aria-busy={!!edits.busy}>
      <header className="rv-bar">
        <span className="rv-pager">
          <button className="rv-icon" aria-label="Previous" disabled={index <= 0 || !!edits.busy} onClick={() => go(list[index - 1])}>
            <ArrowLeft size={16} />
          </button>
          <span className="mono">
            {String(index + 1).padStart(2, '0')} <span className="muted">/ {String(list.length).padStart(2, '0')}</span>
          </span>
          <button className="rv-icon" aria-label="Next" disabled={index >= list.length - 1 || !!edits.busy} onClick={() => go(list[index + 1])}>
            <ArrowRight size={16} />
          </button>
        </span>
        <span className="rv-name mono" title={asset.filename}>
          {asset.filename}
        </span>
        <RouteChip route={route} />
        <span className="spacer" />
        <span className={`rv-save${edits.dirty ? ' is-dirty' : ''}`} role="status">
          {edits.dirty ? 'Unsaved edits' : edits.loading ? '' : 'Saved'}
        </span>
        <button className="btn btn-ghost btn-sm" disabled={!edits.dirty || !!edits.busy} onClick={edits.save}>
          {edits.busy === 'save' ? 'Saving…' : 'Save draft'}
        </button>
      </header>

      {edits.loadError ? (
        <p className="error-note" role="alert">
          <CircleAlert size={15} aria-hidden /> Couldn’t load this item’s labels. {edits.loadError}{' '}
          <button className="btn btn-ghost btn-sm" onClick={edits.retry}>
            Try again
          </button>
        </p>
      ) : null}

      <div className="rv-body">
        <div className="rv-work">
          {p.modality === 'text' ? (
            <TextDoc project={p} asset={asset} edits={edits} colours={colours} selected={selected} onSelect={setSelected} />
          ) : (
            <ImageCanvas
              project={p}
              asset={asset}
              edits={edits}
              colours={colours}
              selected={selected}
              onSelect={setSelected}
              drawClass={drawClass}
              onDrawClass={setDrawClass}
            />
          )}
        </div>
        <LabelPanel project={p} edits={edits} colours={colours} selected={selected} onSelect={setSelected} />
      </div>

      <footer className="rv-foot">
        <div className="rv-foot-text">
          <b>{statusLine}</b>
          {edits.error ? (
            <span className="rv-foot-error" role="alert">
              {edits.error}
            </span>
          ) : edits.note ? (
            <span role="status">{edits.note}</span>
          ) : (
            <span>
              <kbd>1</kbd>–<kbd>9</kbd> class · <kbd>A</kbd> accept · <kbd>R</kbd> reject · <kbd>⌫</kbd> delete · <kbd>⌘Z</kbd> undo
            </span>
          )}
        </div>
        <div className="rv-foot-actions">
          <span className="rv-history">
            <button className="rv-icon" aria-label="Undo" title="Undo · Ctrl Z" disabled={!edits.canUndo || !!edits.busy} onClick={edits.undo}>
              <Undo2 size={16} />
            </button>
            <button className="rv-icon" aria-label="Redo" title="Redo · Ctrl Shift Z" disabled={!edits.canRedo || !!edits.busy} onClick={edits.redo}>
              <Redo2 size={16} />
            </button>
          </span>
          <button className="btn btn-fail btn-sm" disabled={!!edits.busy || edits.loading || route === 'rejected'} onClick={() => finish('reject')}>
            {edits.busy === 'reject' ? 'Rejecting…' : `Reject ${p.unit.replace(/s$/, '')}`}
          </button>
          <button className="btn btn-primary" disabled={!!edits.busy || edits.loading || !!edits.loadError || (route === 'approved' && !edits.dirty)} onClick={() => finish('approve')}>
            {edits.busy === 'approve' ? <Loader2 size={15} className="spin" aria-hidden /> : <Check size={15} aria-hidden />}
            {edits.busy === 'approve'
              ? 'Approving…'
              : edits.remaining
                ? `Accept ${fmt(edits.remaining)} and approve`
                : route === 'approved' && !edits.dirty
                  ? 'Approved'
                  : 'Approve and next'}
          </button>
        </div>
      </footer>
    </section>
  );
}

/* ---------- Labels ---------- */

function LabelPanel({
  project: p,
  edits,
  colours,
  selected,
  onSelect,
}: {
  project: LiveProject;
  edits: Edits;
  colours: Record<string, string>;
  selected: string;
  onSelect: (id: string) => void;
}) {
  const [filter, setFilter] = useState<'all' | 'pending' | 'low'>('all');
  const rows = edits.rows.filter((a) => a.geometry_type !== 'text_relation');
  const total = rows.length;
  const decided = total - edits.remaining;
  // Reading order for text, least confident first for boxes.
  const ordered =
    p.kind === 'spans'
      ? spansOf(rows).map((s) => s.annotation).concat(rows.filter((a) => a.geometry_type === 'text_classification'))
      : [...rows].sort((a, b) => (aiConfidence(a) ?? 2) - (aiConfidence(b) ?? 2));
  const shown = ordered.filter((a) =>
    filter === 'pending' ? decisionOf(a) === 'pending' : filter === 'low' ? (aiConfidence(a) ?? 1) < p.line : true,
  );
  const decide = (a: Annotation, d: 'approved' | 'rejected') => edits.update(a.id, { review_status: a.review_status === d ? 'pending' : d });
  const noun = p.kind === 'boxes' ? 'Boxes' : p.kind === 'spans' ? 'Entities' : 'Labels';

  return (
    <aside className="rv-side" aria-label={noun}>
      <div className="rv-side-head">
        <h2>
          {noun} <span className="muted">{fmt(total)}</span>
        </h2>
        <button
          className="rv-link"
          disabled={!edits.remaining || !!edits.busy}
          onClick={() => edits.change(edits.rows.map((a) => (decisionOf(a) === 'pending' ? { ...a, review_status: 'approved' } : a)))}
        >
          Accept remaining
        </button>
      </div>
      <div className="rv-progress" aria-label={`${decided} of ${total} decided`}>
        <span style={{ width: `${total ? (decided / total) * 100 : 0}%` }} />
      </div>
      <div className="rv-filters" role="group" aria-label="Show">
        {(
          [
            ['all', 'All'],
            ['pending', 'Undecided'],
            ['low', `Below ${p.line.toFixed(2)}`],
          ] as const
        ).map(([f, label]) => (
          <button key={f} aria-pressed={filter === f} onClick={() => setFilter(f)}>
            {label}
          </button>
        ))}
      </div>
      <ul className="rv-labels">
        {edits.loading ? (
          <li className="rv-empty">Loading…</li>
        ) : !shown.length ? (
          <li className="rv-empty">{total ? 'Nothing matches.' : p.kind === 'boxes' ? 'No boxes. Draw any the AI missed.' : 'No labels yet.'}</li>
        ) : (
          shown.map((a) => {
            const c = aiConfidence(a);
            const d = decisionOf(a);
            const original = typeof a.provenance?.original_ai_label === 'string' ? (a.provenance.original_ai_label as string) : (edits.savedLabels.get(a.id) ?? null);
            const relabelled = original && original !== a.label;
            const text = p.kind === 'spans' ? (a.geometry?.text ?? a.text_span?.text) : null;
            const open = selected === a.id;
            return (
              <li
                key={a.id}
                data-label-id={a.id}
                className={`rv-label is-${d}${open ? ' is-open' : ''}${c != null && c < p.line && d === 'pending' ? ' is-flag' : ''}`}
                style={colourStyle(colours[a.label] ?? OTHER_COLOUR)}
              >
                <button className="rv-label-main" aria-expanded={open} onClick={() => onSelect(open ? '' : a.id)}>
                  <i aria-hidden />
                  <span className="rv-label-name">
                    <b>
                      {relabelled ? (
                        <>
                          <s>{original}</s> {a.label}
                        </>
                      ) : (
                        a.label
                      )}
                    </b>
                    {text ? <span className="rv-label-text">“{text}”</span> : null}
                    <small>
                      {modelName(a)}
                      {c != null ? <span className={c < p.line ? 'is-low' : ''}> · {c.toFixed(2)}</span> : null}
                    </small>
                  </span>
                </button>
                <span className="rv-label-actions">
                  <button className="rv-act is-accept" aria-pressed={d === 'approved'} aria-label={`Accept ${a.label}`} title="Accept · A" onClick={() => decide(a, 'approved')}>
                    <Check size={15} />
                  </button>
                  <button className="rv-act is-edit" aria-pressed={d === 'edited'} aria-label={`Correct ${a.label}`} title="Correct" onClick={() => onSelect(a.id)}>
                    <Pencil size={14} />
                  </button>
                  <button className="rv-act is-reject" aria-pressed={d === 'rejected'} aria-label={`Reject ${a.label}`} title="Reject · R" onClick={() => decide(a, 'rejected')}>
                    <X size={15} />
                  </button>
                </span>
                {open ? (
                  <div className="rv-label-edit">
                    <label>
                      Class
                      <select
                        value={a.label}
                        onChange={(e) => edits.update(a.id, { label: e.target.value, review_status: 'edited' })}
                        autoFocus={d !== 'approved'}
                      >
                        {!p.classes.includes(a.label) ? <option value={a.label}>{a.label} (not a project class)</option> : null}
                        {p.classes.map((name, i) => (
                          <option key={name} value={name}>
                            {i < 9 ? `${i + 1}  ` : ''}
                            {name}
                          </option>
                        ))}
                      </select>
                    </label>
                    {a.geometry_type !== 'text_classification' ? (
                      <button
                        className="rv-delete"
                        onClick={() => {
                          edits.change(edits.rows.filter((r) => r.id !== a.id));
                          onSelect('');
                        }}
                      >
                        <Trash2 size={14} aria-hidden /> Delete
                      </button>
                    ) : null}
                    {p.kind === 'boxes' ? (
                      <p className="rv-geom mono">
                        x {a.x.toFixed(1)} · y {a.y.toFixed(1)} · w {a.w.toFixed(1)} · h {a.h.toFixed(1)} %
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </li>
            );
          })
        )}
      </ul>
    </aside>
  );
}
