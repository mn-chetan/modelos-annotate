/*
 * AI results: the run desk. Upload work, run the AI, and see where every item landed:
 * approved by the AI at or above the project's line, below it and waiting on a person, or
 * failed. The contact sheet shows each item with what the AI drew on it; the class summary
 * shows where the AI is least sure; the inspector opens one item with each label's model,
 * confidence and agreement.
 */
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { ArrowRight, CircleAlert, FileText, Image as ImageIcon, Loader2, Play, Search, Upload, X } from 'lucide-react';
import { api } from '../../../services/api';
import {
  getProjectAnnotations,
  isRunning,
  refreshAssets,
  refreshProjects,
  request,
  routeOf,
  useAssets,
  type Annotation,
  type LiveAsset,
  type LiveProject,
  type Route,
} from '../../store';
import { projectHref } from '../../router';
import { PageHead, fmt, projectEyebrow } from '../shared';
import { BoxOverlay } from '../BoxOverlay';
import { RouteChip, agreeingModels, aiConfidence, classColours, colourStyle, modelName, pct, OTHER_COLOUR } from '../annotation-ui';
import { analyseDocument, docLabel, spansOf, TextSnippet } from '../text/text-model';
import '../text/text.css';
import './ai.css';

type Batch = {
  id: string;
  status: string;
  total: number;
  completed: number;
  failed: number;
  error_summary?: string;
};

type Filter = 'all' | Route;

const FILTERS: [Filter, string][] = [
  ['all', 'All'],
  ['toReview', 'Below the line'],
  ['approvedByAi', 'Approved by AI'],
  ['approved', 'Approved'],
  ['failed', 'Failed'],
  ['notRun', 'Not drafted'],
];

const ACCEPT: Record<LiveProject['modality'], string> = {
  image: 'image/*,.zip',
  text: '.txt,.csv,.json,.tsv,.docx,.pdf',
  video: 'video/*,.zip',
};

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** The project's AI runs, polled quickly while one is going and slowly otherwise. */
function useBatches(projectId: string, enabled: boolean) {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [error, setError] = useState('');
  const poke = useRef<() => void>(() => {});
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      clearTimeout(timer);
      try {
        const rows = await request<Batch[]>(`/projects/${projectId}/batches`);
        if (!alive) return;
        setBatches(rows);
        setError('');
        const active = rows.some((b) => ['queued', 'running'].includes(b.status));
        if (active) await refreshAssets(projectId);
        if (alive) timer = setTimeout(tick, active ? 2500 : 15000);
      } catch (e) {
        if (!alive) return;
        setError(message(e));
        timer = setTimeout(tick, 6000);
      }
    };
    poke.current = tick;
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [projectId, enabled]);
  return { batches, error, poll: () => poke.current() };
}

/** Labels for every item, grouped by item, reloaded when any item changes. */
function useLabelsByItem(assets: LiveAsset[] | undefined) {
  const [byItem, setByItem] = useState<Map<string, Annotation[]> | null>(null);
  const key = assets?.map((a) => `${a.id}:${a.updated_at ?? ''}:${a.status}:${a.review_status}`).join('|');
  useEffect(() => {
    if (!assets) return;
    let alive = true;
    getProjectAnnotations(assets.filter((a) => (a.annotation_count ?? 0) > 0 || a.ai_completed_at || a.text_analysis))
      .then((rows) => {
        if (!alive) return;
        const map = new Map<string, Annotation[]>();
        for (const r of rows) map.set(r.asset_id, [...(map.get(r.asset_id) ?? []), r]);
        setByItem(map);
      })
      .catch(() => alive && setByItem(new Map()));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return byItem;
}

/** Size an image so it fits a frame of the given ratio whole, keeping its boxes aligned. */
function fitIn(a: LiveAsset, frame: number): CSSProperties {
  const r = a.width && a.height ? a.width / a.height : frame;
  return r >= frame ? { width: '100%', aspectRatio: `${r}` } : { height: '100%', width: 'auto', aspectRatio: `${r}` };
}

const weakestOf = (rows: Annotation[]) => {
  const confs = rows.map(aiConfidence).filter((c): c is number => c != null);
  return confs.length ? Math.min(...confs) : null;
};

export function AiResultsPage({ project: p }: { project: LiveProject }) {
  const assets = useAssets(p.id);
  const byItem = useLabelsByItem(assets);
  const isText = p.modality === 'text';
  const { batches, error: pollError, poll } = useBatches(p.id, !isText);
  const [filter, setFilter] = useState<Filter>('all');
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const [activity, setActivity] = useState<'upload' | 'run' | null>(null);
  const [progress, setProgress] = useState<{ done: number; total: number; failed: number } | null>(null);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const colours = classColours(p);

  const latest = batches[0];
  const batchActive = !!latest && ['queued', 'running'].includes(latest.status);
  const running = batchActive || activity === 'run' || !!assets?.some(isRunning);
  const routes = useMemo(() => new Map((assets ?? []).map((a) => [a.id, routeOf(a)])), [assets]);
  const counts = (r: Filter) => (r === 'all' ? (assets?.length ?? 0) : [...routes.values()].filter((x) => x === r).length);
  const runnable = (assets ?? []).filter((a) => ['notRun', 'failed'].includes(routes.get(a.id)!) && !isRunning(a));

  const visible = (assets ?? [])
    .filter((a) => filter === 'all' || routes.get(a.id) === filter)
    .filter((a) => a.filename.toLowerCase().includes(query.trim().toLowerCase()))
    .sort((a, b) => {
      // Below-the-line work first, weakest first, so the sheet reads like the review queue.
      const order: Route[] = ['toReview', 'failed', 'notRun', 'approvedByAi', 'approved', 'rejected'];
      const d = order.indexOf(routes.get(a.id)!) - order.indexOf(routes.get(b.id)!);
      if (d) return d;
      return (weakestOf(byItem?.get(a.id) ?? []) ?? 2) - (weakestOf(byItem?.get(b.id) ?? []) ?? 2);
    });

  async function upload(files: File[]) {
    if (!files.length) return;
    setActivity('upload');
    setError('');
    let done = 0;
    try {
      for (const f of files) {
        await api.uploadAssets(p.id, [f]);
        done++;
        setNote(`Uploaded ${done} of ${files.length}`);
      }
      setNote(`Uploaded ${fmt(done)} ${done === 1 ? 'file' : 'files'}.`);
    } catch (e) {
      setError(`Upload stopped after ${done} of ${files.length}. Files already uploaded are saved. ${message(e)}`);
    } finally {
      await refreshAssets(p.id);
      await refreshProjects();
      setActivity(null);
    }
  }

  async function runImages() {
    await api.triggerAiAnnotation(p.id);
    poll();
    await refreshAssets(p.id);
  }

  /** Text runs one document at a time, two in flight, from this page. */
  async function runText() {
    const queue = [...runnable];
    const tally = { done: 0, total: queue.length, failed: 0 };
    setProgress({ ...tally });
    const worker = async () => {
      for (let a = queue.shift(); a; a = queue.shift()) {
        try {
          await analyseDocument(p, a);
        } catch {
          tally.failed++;
        }
        tally.done++;
        setProgress({ ...tally });
      }
    };
    await Promise.all([worker(), worker()]);
    await refreshAssets(p.id);
    await refreshProjects();
    if (tally.failed) setError(`${tally.failed} of ${tally.total} documents failed. They stay in the Failed filter; run again to retry them.`);
  }

  async function run() {
    setActivity('run');
    setError('');
    setNote('');
    try {
      if (isText) await runText();
      else await runImages();
    } catch (e) {
      setError(`The run didn’t start. ${message(e)}`);
    } finally {
      setActivity(null);
      setProgress(null);
    }
  }

  const below = counts('toReview');
  const lede = !assets
    ? 'Loading…'
    : !assets.length
      ? `Upload ${p.unit}, then let the AI draft every label. Anything it is less than ${p.line.toFixed(2)} sure of goes to a person.`
      : running
        ? `The AI is drafting. ${p.unit[0].toUpperCase() + p.unit.slice(1)} appear here as each one finishes.`
        : `${fmt(counts('approvedByAi'))} approved by the AI at ${p.line.toFixed(2)} or higher; ${fmt(below)} below the line and waiting on a person.`;

  const selected = assets?.find((a) => a.id === open);

  return (
    <div className="page ai-page">
      <PageHead
        eyebrow={projectEyebrow(p)}
        title="AI results"
        lede={lede}
        actions={
          <>
            <label className={`btn btn-ghost${activity || running ? ' is-disabled' : ''}`}>
              {activity === 'upload' ? <Loader2 size={15} className="spin" aria-hidden /> : <Upload size={15} aria-hidden />}
              {activity === 'upload' ? 'Uploading…' : `Upload ${p.unit}`}
              <input
                className="sr-only"
                type="file"
                multiple
                accept={ACCEPT[p.modality]}
                disabled={!!activity || running}
                onChange={(e) => {
                  const files = Array.from(e.target.files ?? []);
                  e.target.value = '';
                  upload(files);
                }}
              />
            </label>
            {runnable.length || running ? (
              <button className="btn btn-accent" disabled={running || !!activity} onClick={run}>
                {running ? <Loader2 size={15} className="spin" aria-hidden /> : <Play size={14} aria-hidden />}
                {running ? 'AI running…' : `Run AI on ${fmt(runnable.length)}`}
              </button>
            ) : null}
            {below > 0 ? (
              <a className="btn btn-primary" href={projectHref(p.id, 'review')}>
                Review {fmt(below)} below the line <ArrowRight size={15} aria-hidden />
              </a>
            ) : null}
          </>
        }
      />

      {error || pollError ? (
        <p role="alert" className="error-note">
          <CircleAlert size={16} aria-hidden /> {error || `Couldn’t check the AI run: ${pollError}`}
        </p>
      ) : null}
      {note && !error ? (
        <p role="status" className="ai-note">
          {note}
        </p>
      ) : null}

      <RunStrip project={p} batch={latest} active={batchActive} textProgress={progress} />

      {!assets ? (
        <p className="page-status" role="status">
          <Loader2 size={16} className="spin" aria-hidden /> Loading {p.unit}…
        </p>
      ) : !assets.length ? (
        <section className="ai-empty">
          {isText ? <FileText size={26} aria-hidden /> : <ImageIcon size={26} aria-hidden />}
          <h2>Your {p.unit} start here</h2>
          <p>
            Upload a few {p.unit}, then run the AI to draft the first pass. You’ll see each one land on one side of the {p.line.toFixed(2)} line or the
            other.
          </p>
        </section>
      ) : (
        <>
          <div className="toolbar ai-toolbar">
            <div className="seg ai-filters" role="group" aria-label="Filter by where items landed">
              {FILTERS.filter(([f]) => f === 'all' || counts(f) > 0 || f === 'toReview').map(([f, label]) => (
                <button key={f} aria-pressed={filter === f} onClick={() => setFilter(f)}>
                  {f === 'toReview' ? <i className="ai-dot is-review" aria-hidden /> : f === 'approvedByAi' ? <i className="ai-dot is-ai" aria-hidden /> : null}
                  {label} <span className="ai-count">{fmt(counts(f))}</span>
                </button>
              ))}
            </div>
            <span className="spacer" />
            <span className="search" role="search">
              <Search size={15} aria-hidden />
              <input aria-label={`Find ${p.unit}`} placeholder={`Find ${p.unit.replace(/s$/, '')} by name`} value={query} onChange={(e) => setQuery(e.target.value)} />
            </span>
          </div>

          <div className="ai-desk">
            <section aria-label={`${p.unit} and what the AI drew`}>
              {visible.length ? (
                <ul className={`ai-sheet${isText ? ' is-text' : ''}`}>
                  {visible.map((a) => (
                    <SheetItem key={a.id} project={p} asset={a} labels={byItem?.get(a.id)} route={routes.get(a.id)!} colours={colours} onOpen={() => setOpen(a.id)} />
                  ))}
                </ul>
              ) : (
                <p className="ai-none">Nothing matches. Try another filter or name.</p>
              )}
            </section>
            <ClassSummary project={p} byItem={byItem} colours={colours} />
          </div>
        </>
      )}

      {selected ? <Inspector project={p} asset={selected} labels={byItem?.get(selected.id) ?? []} route={routes.get(selected.id)!} colours={colours} onClose={() => setOpen(null)} /> : null}
    </div>
  );
}

/** The latest run: progress while it goes, what went wrong if anything did, and the models used. */
function RunStrip({ project: p, batch, active, textProgress }: { project: LiveProject; batch?: Batch; active: boolean; textProgress: { done: number; total: number; failed: number } | null }) {
  const pipeline = p.modality === 'text' ? 'Gemini drafts every label, with a confidence for each' : 'Each image: Florence-2 describes the scene, YOLO26 and Grounding DINO find objects, and matching boxes are merged';
  if (textProgress) {
    return (
      <div className="ai-run is-active" role="status">
        <Loader2 size={16} className="spin" aria-hidden />
        <div>
          <b>
            Drafting {fmt(textProgress.done)} of {fmt(textProgress.total)} documents
          </b>
          <span>{pipeline}. Keep this page open until it finishes.</span>
        </div>
        <progress value={textProgress.done} max={Math.max(1, textProgress.total)} />
      </div>
    );
  }
  if (batch && active) {
    const finished = batch.completed + batch.failed;
    return (
      <div className="ai-run is-active" role="status">
        <Loader2 size={16} className="spin" aria-hidden />
        <div>
          <b>
            Drafting {fmt(finished)} of {fmt(batch.total)} {p.unit}
            {batch.failed ? ` · ${fmt(batch.failed)} failed` : ''}
          </b>
          <span>{pipeline}. The run continues if you leave this page.</span>
        </div>
        <progress value={finished} max={Math.max(1, batch.total)} />
      </div>
    );
  }
  return (
    <div className="ai-run">
      <span className="ai-run-note">{pipeline}.</span>
      {batch?.error_summary ? (
        <details className="ai-run-error">
          <summary>
            <CircleAlert size={14} aria-hidden /> The last run had problems
          </summary>
          <p>{batch.error_summary}</p>
        </details>
      ) : null}
    </div>
  );
}

function SheetItem({
  project: p,
  asset: a,
  labels,
  route,
  colours,
  onOpen,
}: {
  project: LiveProject;
  asset: LiveAsset;
  labels?: Annotation[];
  route: Route;
  colours: Record<string, string>;
  onOpen: () => void;
}) {
  const rows = labels ?? [];
  const weakest = weakestOf(rows);
  const live = rows.filter((r) => r.review_status !== 'rejected');
  const flagged = route === 'toReview';
  const [broken, setBroken] = useState(false);
  return (
    <li className={`ai-item${flagged ? ' is-flag' : ''}`}>
      <button className="ai-item-btn" onClick={onOpen} aria-label={`Open ${a.filename}`}>
        {p.modality === 'text' ? (
          <TextSnippet project={p} asset={a} labels={rows} colours={colours} />
        ) : (
          <span className="ai-thumb">
            {broken ? (
              <span className="ai-thumb-missing">Image unavailable</span>
            ) : (
              <span className="image-boxes" style={fitIn(a, 4 / 3)}>
                <img src={api.getAssetPreviewUrl(a.id)} alt="" loading="lazy" onError={() => setBroken(true)} />
                {labels ? <BoxOverlay annotations={rows} colours={colours} quiet aria-hidden /> : null}
              </span>
            )}
          </span>
        )}
        <span className="ai-cap">
          <span className="ai-cap-name mono" title={a.filename}>
            {a.filename}
          </span>
          <span className="ai-cap-row">
            <RouteChip route={route} running={isRunning(a)} />
            <span className="ai-cap-meta">
              {route === 'failed'
                ? 'See why'
                : route === 'notRun'
                  ? '—'
                  : p.kind === 'document'
                    ? (docLabel(rows)?.label ?? 'No label')
                    : `${fmt(live.length)} ${p.kind === 'spans' ? 'entities' : 'boxes'}`}
              {weakest != null ? (
                <>
                  {' · '}
                  <span className={weakest < p.line && flagged ? 'is-low' : ''}>lowest {weakest.toFixed(2)}</span>
                </>
              ) : null}
            </span>
          </span>
        </span>
      </button>
    </li>
  );
}

/** Per class: how many labels, how sure the AI was on average, and how many fell below the line. */
function ClassSummary({ project: p, byItem, colours }: { project: LiveProject; byItem: Map<string, Annotation[]> | null; colours: Record<string, string> }) {
  const all = byItem ? [...byItem.values()].flat().filter((a) => a.review_status !== 'rejected' && a.geometry_type !== 'text_relation') : [];
  const rows = p.classList.map((c) => {
    const mine = all.filter((a) => a.label === c.name);
    const confs = mine.map(aiConfidence).filter((x): x is number => x != null);
    return {
      ...c,
      n: mine.length,
      mean: confs.length ? confs.reduce((s, x) => s + x, 0) / confs.length : null,
      low: confs.filter((x) => x < p.line).length,
    };
  });
  const strays = all.filter((a) => !p.classes.includes(a.label)).length;
  const weakest = Math.min(...rows.filter((r) => r.mean != null && r.n >= 3).map((r) => r.mean!));
  return (
    <aside className="ai-classes" aria-label="By class">
      <h2 className="ai-side-title">By class</h2>
      {!byItem ? (
        <p className="muted">Loading labels…</p>
      ) : (
        <table className="ai-class-table">
          <thead>
            <tr>
              <th scope="col">Class</th>
              <th scope="col" className="num">
                Labels
              </th>
              <th scope="col" className="num">
                Mean
              </th>
              <th scope="col" className="num">
                Below {p.line.toFixed(2)}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} className={r.mean === weakest ? 'is-flag' : undefined}>
                <th scope="row">
                  <span className="ai-class" style={colourStyle(colours[r.name])}>
                    <i aria-hidden />
                    {r.name}
                  </span>
                </th>
                <td className="num">{fmt(r.n)}</td>
                <td className="num">{r.mean == null ? <span className="muted">—</span> : r.mean.toFixed(2)}</td>
                <td className="num">{r.low ? <span className="ai-low">{fmt(r.low)}</span> : <span className="muted">0</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {strays ? <p className="ai-foot">{fmt(strays)} labels use names outside this project’s classes, from an earlier run.</p> : null}
      {Number.isFinite(weakest) ? <p className="ai-foot">Highlighted: the class the AI is least sure of on average.</p> : null}
    </aside>
  );
}

/** One item, opened: the image or document with every label, its model, confidence and agreement. */
function Inspector({
  project: p,
  asset: a,
  labels,
  route,
  colours,
  onClose,
}: {
  project: LiveProject;
  asset: LiveAsset;
  labels: Annotation[];
  route: Route;
  colours: Record<string, string>;
  onClose: () => void;
}) {
  const [focus, setFocus] = useState('');
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const key = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [onClose]);
  const rows = [...labels].sort((x, y) => (aiConfidence(x) ?? 2) - (aiConfidence(y) ?? 2));
  const doc = p.kind === 'document' ? docLabel(labels) : null;
  return (
    <div className="ai-inspector" role="dialog" aria-modal="true" aria-label={a.filename}>
      <div className="ai-scrim" onClick={onClose} />
      <div className="ai-panel">
        <header className="ai-panel-head">
          <div>
            <p className="page-eyebrow">{p.unit.replace(/s$/, '')}</p>
            <h2 className="mono" title={a.filename}>
              {a.filename}
            </h2>
          </div>
          <RouteChip route={route} running={isRunning(a)} />
          <button ref={closeRef} className="ai-x" aria-label="Close" onClick={onClose}>
            <X size={17} />
          </button>
        </header>

        {a.inference_error ? (
          <p className="error-note" role="alert">
            <CircleAlert size={15} aria-hidden /> {a.inference_error}
          </p>
        ) : null}

        {p.modality === 'text' ? (
          <div className="ai-doc">
            <TextSnippet project={p} asset={a} labels={labels} colours={colours} full focus={focus} />
          </div>
        ) : (
          <div className="ai-stage">
            <span className="image-boxes">
              <img src={api.getAssetImageUrl(a.id)} alt={a.filename} />
              <BoxOverlay annotations={labels} colours={colours} hovered={focus} onHover={setFocus} />
            </span>
          </div>
        )}

        {a.caption ? (
          <p className="ai-caption">
            <span>AI scene note</span> {a.caption}
          </p>
        ) : null}

        {doc ? (
          <p className="ai-doclabel">
            <span>AI label</span> <b>{doc.label}</b> {aiConfidence(doc) != null ? <span className="mono">{pct(aiConfidence(doc)!)}</span> : null}
          </p>
        ) : null}

        <h3 className="ai-side-title">
          {p.kind === 'boxes' ? 'Boxes' : p.kind === 'spans' ? 'Entities' : 'Labels'}, least confident first <span className="muted">{fmt(rows.length)}</span>
        </h3>
        {rows.length ? (
          <ul className="ai-labels">
            {rows.map((r) => {
              const c = aiConfidence(r);
              const agree = agreeingModels(r);
              const text = p.kind === 'spans' ? spansOf([r])[0]?.text : null;
              return (
                <li
                  key={r.id}
                  className={`${c != null && c < p.line ? 'is-low' : ''}${r.review_status === 'rejected' ? ' is-rejected' : ''}${focus === r.id ? ' is-focus' : ''}`}
                  style={colourStyle(colours[r.label] ?? OTHER_COLOUR)}
                  onMouseEnter={() => setFocus(r.id)}
                  onMouseLeave={() => setFocus('')}
                >
                  <i aria-hidden />
                  <span className="ai-label-name">
                    <b>{r.label}</b>
                    {text ? <span className="ai-label-text">“{text}”</span> : null}
                    <small>{agree.length > 1 ? `${agree.join(' + ')} agree` : modelName(r)}</small>
                  </span>
                  <span className="ai-label-conf mono">{c == null ? 'Person' : c.toFixed(2)}</span>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="muted">{route === 'notRun' ? 'Not drafted yet.' : 'The AI found nothing here. A person still has to confirm an empty result.'}</p>
        )}

        <footer className="ai-panel-foot">
          <a className="btn btn-primary" href={projectHref(p.id, 'review', a.id)}>
            {route === 'toReview' ? 'Review this ' : 'Open in review: '}
            {p.unit.replace(/s$/, '')} <ArrowRight size={15} aria-hidden />
          </a>
        </footer>
      </div>
    </div>
  );
}
