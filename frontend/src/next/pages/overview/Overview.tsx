/*
 * Overview: how much of the work did the AI do on its own, and how much went to people?
 * Six scorecards follow the pipeline (total, annotated by AI, approved by AI, sent to human
 * review, approved, AI accuracy). Below them: where the approval line sits and whether the
 * AI's confidence can be trusted, AI accuracy by class, the mistakes reviewers fix, the
 * hardest items, and the reviewers.
 *
 * Deliberately left out: anything measured over time, quality-check results and handling
 * time. Every figure is computed from the project's saved items and labels; a figure without
 * enough evidence keeps its place and says what it is waiting for.
 */
import { useEffect, useState, type ReactNode } from 'react';
import { ArrowRight, Download, Link2, Loader2 } from 'lucide-react';
import { exportLabels, getProjectAnnotations, useAssets, type Annotation, type ExportFormat, type LiveProject } from '../../store';
import { projectHref } from '../../router';
import { projectEyebrow } from '../shared';
import { buildOverview, fmt, pctText, routeAt, type Overview } from './model';
import {
  AI_COLOR,
  APPROVED_COLOR,
  Calibration,
  Figure,
  HBars,
  Key,
  REVIEW_COLOR,
  Routing,
  SampleView,
  calibrationTable,
  routingTable,
  useLine,
} from './charts';
import { ClassTable, HardestItems } from './tables';
import './overview.css';

const REST = 'var(--rule2)';
/** A named remainder: visible enough to key with a dot, quieter than any series colour. */
const NOT_YET = '#B9B2A3';
const FAILED = '#8C909A';
const FIX_COLORS = ['#2A57C0', '#D39B0A', '#1F8A5B', '#8D4AA6', '#D2432C'];

type Seg = { value: number; color: string; label: string; key?: string };

/**
 * A scorecard: what it counts, the number, its share of the whole, and a bar. When the bar
 * splits into named parts (segments with a `key`), each part gets a dot and its number
 * underneath, so the split reads without a sentence.
 */
function Score({ label, value, share, of, segs }: { label: string; value: string; share?: string; of?: string; segs: Seg[] }) {
  const total = segs.reduce((s, x) => s + x.value, 0);
  const keyed = segs.filter((s) => s.key);
  return (
    <div className="ov-score">
      <p className="ov-score-label">{label}</p>
      <p className="ov-score-value">{value}</p>
      {share ? (
        <p className="ov-score-share">
          <b>{share}</b> {of}
        </p>
      ) : null}
      <span className="ov-score-meter" role="img" aria-label={segs.map((s) => `${s.label} ${fmt(s.value)}`).join(', ')}>
        {total > 0 ? segs.map((s) => (s.value > 0 ? <span key={s.label} style={{ flexGrow: s.value / total, background: s.color }} /> : null)) : null}
      </span>
      {keyed.length > 1 ? (
        <ul className="ov-score-keys">
          {keyed.map((s) => (
            <li key={s.label}>
              <i style={{ background: s.color }} aria-hidden />
              <b>{fmt(s.value)}</b> {s.key}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** A figure's place, held open until there is evidence to draw. */
function Waiting({ children }: { children: ReactNode }) {
  return <p className="ov-wait">{children}</p>;
}

/** Copy the page link, with a short confirmation announced to screen readers. */
function useShare() {
  const [msg, setMsg] = useState('');
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(''), 2400);
    return () => clearTimeout(t);
  }, [msg]);
  const share = async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      setMsg('Link copied');
    } catch {
      setMsg('Copy the address bar to share this page');
    }
  };
  const note = (
    <span className={`ov-toast${msg ? ' is-on' : ''}`} role="status" aria-live="polite">
      {msg}
    </span>
  );
  return { share, note, say: setMsg };
}

const EXPORTS: Record<LiveProject['kind'], [ExportFormat, string][]> = {
  boxes: [
    ['coco', 'COCO JSON'],
    ['yolo', 'YOLO'],
  ],
  spans: [
    ['json', 'JSON'],
    ['csv', 'CSV'],
  ],
  document: [
    ['json', 'JSON'],
    ['csv', 'CSV'],
  ],
};

/** All of a project's labels, loaded once its items are known and reloaded when they change. */
function useLabels(assets: ReturnType<typeof useAssets>) {
  const [labels, setLabels] = useState<Annotation[] | null>(null);
  const [error, setError] = useState('');
  const key = assets?.map((a) => `${a.id}:${a.updated_at ?? ''}:${a.review_status}`).join('|');
  useEffect(() => {
    if (!assets) return;
    let alive = true;
    getProjectAnnotations(assets)
      .then((rows) => alive && setLabels(rows))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
    // The key captures every change that matters; the array identity changes on each refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return { labels, error };
}

export function OverviewPage({ project }: { project: LiveProject }) {
  const assets = useAssets(project.id);
  const { labels, error } = useLabels(assets);

  if (!assets || !labels) {
    return (
      <div className="ov">
        <OverviewHead project={project} lede={error ? '' : 'Reading the project’s items and labels…'} />
        {error ? (
          <p className="error-note" role="alert">
            Couldn’t load this project’s labels. {error}
          </p>
        ) : (
          <p className="page-status" role="status">
            <Loader2 size={16} className="spin" aria-hidden /> Loading
          </p>
        )}
      </div>
    );
  }
  return <OverviewBody o={buildOverview(project, assets, labels)} />;
}

function OverviewHead({ project, lede, actions }: { project: LiveProject; lede: ReactNode; actions?: ReactNode }) {
  return (
    <header className="ov-head">
      <div>
        <p className="page-eyebrow">{projectEyebrow(project)}</p>
        <h1 className="page-title">{project.name}</h1>
        {lede ? <p className="page-lede">{lede}</p> : null}
      </div>
      {actions}
    </header>
  );
}

function OverviewBody({ o }: { o: Overview }) {
  const project = o.project;
  const t = useLine(o.line);
  const { share, note, say } = useShare();
  const r = routeAt(o, t.line);
  const lineText = t.line.toFixed(3).replace(/0$/, '');
  const reviewedSoFar = o.approvedHuman + o.rejected;
  const hasConfidence = o.bins.some((b) => b.n > 0);
  const calibrated = o.calibration.reduce((s, b) => s + b.items, 0);

  const download = async (format: ExportFormat) => {
    try {
      await exportLabels(project.id, format);
    } catch (e) {
      say(`Export failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const lede = !o.assets
    ? `No ${o.unit} yet. Upload some, then let the AI draft the first pass.`
    : o.done
      ? `All ${fmt(o.assets)} ${o.unit} approved and ready to export.`
      : `${fmt(o.approved)} of ${fmt(o.assets)} ${o.unit} approved: ${fmt(o.approvedAuto)} by AI, ${fmt(o.approvedHuman)} by reviewers.`;

  const primary = !o.assets || o.queued > 0 ? (
    <a className="btn btn-primary btn-sm" href={projectHref(project.id, 'ai')}>
      {o.assets ? 'Run AI' : 'Upload and run AI'} <ArrowRight size={15} aria-hidden />
    </a>
  ) : o.inReview > 0 ? (
    <a className="btn btn-primary btn-sm" href={projectHref(project.id, 'review')}>
      Open review <ArrowRight size={15} aria-hidden />
    </a>
  ) : null;

  return (
    <div className="ov">
      <OverviewHead
        project={project}
        lede={lede}
        actions={
          <div className="page-actions">
            <button className="btn btn-ghost btn-sm" onClick={share}>
              <Link2 size={15} aria-hidden /> Share
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => window.print()}>
              <Download size={15} aria-hidden /> Report PDF
            </button>
            {primary}
            {note}
          </div>
        }
      />

      <section className="ov-scores" aria-label="Scorecards">
        <Score
          label={`Total ${o.unit}`}
          value={fmt(o.assets)}
          share={fmt(o.labels)}
          of={o.labelNoun}
          segs={[{ value: o.assets, color: 'var(--ink)', label: `Total ${o.unit}` }]}
        />
        <Score
          label="Annotated by AI"
          value={fmt(o.drafted)}
          share={o.assets ? pctText(o.drafted / o.assets) : undefined}
          of={`of ${o.unit}`}
          segs={[
            { value: o.drafted, color: AI_COLOR, label: 'Annotated by AI', key: 'annotated' },
            { value: o.queued, color: NOT_YET, label: 'Not annotated yet', key: 'not yet' },
            ...(o.failed ? [{ value: o.failed, color: FAILED, label: 'AI failed', key: 'failed' }] : []),
          ]}
        />
        <Score
          label="Approved by AI"
          value={fmt(o.autoAccepted)}
          share={o.drafted ? pctText(o.autoAccepted / o.drafted) : undefined}
          of="of AI annotations"
          segs={[
            { value: o.autoAccepted, color: AI_COLOR, label: 'Approved by AI', key: `at ${o.line} or higher` },
            { value: o.toPeople, color: REVIEW_COLOR, label: 'Sent to human review', key: `below ${o.line}` },
          ]}
        />
        <Score
          label="Sent to human review"
          value={fmt(o.toPeople)}
          share={o.drafted ? pctText(o.toPeople / o.drafted) : undefined}
          of="of AI annotations"
          segs={[
            { value: reviewedSoFar, color: APPROVED_COLOR, label: 'Decided by reviewers', key: 'decided' },
            { value: o.inReview, color: REVIEW_COLOR, label: 'In human review', key: 'in review' },
          ]}
        />
        <Score
          label="Approved"
          value={fmt(o.approved)}
          share={o.assets ? pctText(o.approved / o.assets) : undefined}
          of={`of ${o.unit}`}
          segs={[
            { value: o.approvedAuto, color: AI_COLOR, label: 'Approved by AI', key: 'by AI' },
            { value: o.approvedHuman, color: APPROVED_COLOR, label: 'Approved by reviewers', key: 'by reviewers' },
            { value: o.remaining, color: REST, label: 'Not approved yet' },
          ]}
        />
        <Score
          label="AI accuracy"
          value={o.kept == null ? '—' : pctText(o.kept, 1)}
          share={fmt(o.labelsReviewed)}
          of={`${o.labelNoun} reviewed`}
          segs={[
            { value: o.labelsReviewed - o.corrections, color: 'var(--ink2)', label: 'Kept unchanged', key: 'kept' },
            { value: o.corrections, color: NOT_YET, label: 'Corrected by reviewers', key: 'corrected' },
          ]}
        />
      </section>

      <section className="ov-row is-1-1">
        <Figure
          title="AI approval threshold"
          sub={
            hasConfidence
              ? `At ${lineText}, the AI approves ${pctText(1 - r.share)} and sends ${pctText(r.share)} to human review` +
                (r.checked ? ` · reviewers corrected ${fmt(r.wrong)} of the ${fmt(r.checked)} above it they checked` : '')
              : `The project approves by AI at ${o.line}. Each ${o.unit.replace(/s$/, '')} is placed by its least confident label.`
          }
          legend={
            hasConfidence ? (
              <>
                <Key color={AI_COLOR}>Approved by AI</Key>
                <Key color={REVIEW_COLOR}>Sent to human review</Key>
              </>
            ) : null
          }
          table={hasConfidence ? routingTable(o, t.line) : undefined}
        >
          {hasConfidence ? <Routing o={o} t={t} /> : <Waiting>Waiting for the AI’s first drafts. Run AI to place each {o.unit.replace(/s$/, '')} on this line.</Waiting>}
        </Figure>
        <Figure
          title="Can we trust the AI’s confidence?"
          sub={
            calibrated
              ? `When the AI says it is 90% sure, is it right nine times in ten? From ${fmt(calibrated)} reviewed ${o.labelNoun}; faint bars rest on fewer than five.`
              : 'When the AI says it is 90% sure, is it right nine times in ten?'
          }
          legend={
            calibrated ? (
              <>
                <Key color={AI_COLOR}>Approved by AI</Key>
                <Key color={REVIEW_COLOR}>Sent to human review</Key>
                <Key color="var(--ink)" kind="line">
                  Perfectly calibrated
                </Key>
              </>
            ) : null
          }
          table={calibrated ? calibrationTable(o) : undefined}
        >
          {calibrated ? (
            <Calibration o={o} line={t.line} />
          ) : (
            <Waiting>Needs reviewed {o.labelNoun}. Each one a reviewer keeps or corrects shows whether the AI’s confidence holds.</Waiting>
          )}
        </Figure>
      </section>

      <section className="ov-row is-1">
        <Figure title="AI accuracy by class" sub="Where the AI is right, and where reviewers correct it">
          {o.classes.length ? <ClassTable o={o} /> : <Waiting>This project has no classes yet.</Waiting>}
        </Figure>
      </section>

      <section className="ov-row is-1-1">
        <Figure title="Most common mix-ups" sub="What the AI called it, and what reviewers changed it to. Watch for these first.">
          {o.mixups.length ? (
            <HBars
              labelW={210}
              rows={o.mixups.map((m) => {
                const sample = o.classes[m.toIndex]?.sample;
                return {
                  key: `${m.from} → ${m.to}`,
                  value: m.n,
                  color: '#2F52B4',
                  note: `AI said ${m.from}; reviewers changed it to ${m.to}`,
                  label: (
                    <span className="ov-pair">
                      {sample?.kind === 'crop' ? <SampleView sample={sample} /> : null}
                      <span>
                        {m.from} <span className="muted">→</span> {m.to}
                      </span>
                    </span>
                  ),
                };
              })}
            />
          ) : (
            <Waiting>No class changes yet. When a reviewer relabels one of the AI’s {o.labelNoun}, the pair appears here.</Waiting>
          )}
        </Figure>
        <Figure title="What kind of fixes reviewers make" sub={o.fixes.length ? `${fmt(o.fixes.reduce((s, f) => s + f.n, 0))} fixes, by kind` : 'Corrections, by kind'}>
          {o.fixes.length ? (
            <HBars
              labelW={170}
              rows={o.fixes.map((f, i) => ({
                key: f.name,
                value: f.n,
                color: FIX_COLORS[i % FIX_COLORS.length],
                note: `${f.name}: ${fmt(f.n)}`,
                label: <span>{f.name}</span>,
              }))}
            />
          ) : (
            <Waiting>No fixes saved yet. Relabelled, reshaped, added and rejected {o.labelNoun} are counted here.</Waiting>
          )}
        </Figure>
      </section>

      <section className="ov-row is-1">
        <Figure title="Hardest items" sub="The items the AI was least sure of, with the reviewer’s correction where there was one">
          {o.hardest.length ? <HardestItems o={o} /> : <Waiting>Waiting for the AI’s first drafts.</Waiting>}
        </Figure>
      </section>

      <section className="ov-row is-1-1">
        <Figure title="Reviewers" sub="How many each reviewed, and how often they changed the AI’s annotation">
          <Waiting>
            This workspace has no sign-in yet, so decisions aren’t filed under a reviewer’s name. So far {fmt(reviewedSoFar)}{' '}
            {reviewedSoFar === 1 ? `${o.unit.replace(/s$/, '')} has` : `${o.unit} have`} been decided by reviewers.
          </Waiting>
        </Figure>
        <Figure title="Export" sub={`Approved ${o.unit} only; rejected ${o.labelNoun} are left out`}>
          <div className="ov-export">
            <p>
              <b className="num">{fmt(o.approved)}</b> of {fmt(o.assets)} {o.unit} approved
            </p>
            <div className="page-actions">
              {EXPORTS[project.kind].map(([format, name]) => (
                <button key={format} className="btn btn-ghost btn-sm" disabled={!o.approved} onClick={() => download(format)}>
                  <Download size={14} aria-hidden /> {name}
                </button>
              ))}
            </div>
          </div>
        </Figure>
      </section>

      <p className="ov-sample-note">Computed from the project’s saved items and labels. Quality-check results aren’t included.</p>
    </div>
  );
}
