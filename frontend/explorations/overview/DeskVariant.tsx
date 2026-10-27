/*
 * Direction C · Desk. The overview answers one question first: how much of the work did
 * the AI do on its own, and how much went to people? Six scorecards follow the pipeline
 * (total, annotated by AI, approved by AI, sent to human review, approved, AI accuracy),
 * and the AI approval threshold shows where the split is set.
 *
 * Deliberately left out: anything measured over time (rates, trends, forecasts),
 * quality-check results and handling time. Items in QC count as "with reviewers".
 */
import { ArrowRight, Download, Link2 } from 'lucide-react';
import { projectHref } from '../../src/next/router';
import { projectEyebrow } from '../../src/next/pages/shared';
import type { Project } from '../../src/showcase/content';
import { useShare } from './useShare';
import { STATE_COLOR, buildOverview, fmt, pctText, routeAt, type Overview } from './model';
import { AI_COLOR, Figure, Routing, RoutingKeys, routingTable, useThresholds } from './viz';
import { ClassTable, PeopleTable } from './tables';

/** Fold QC into the reviewers' share and drop QC send-backs, so no QC state shows. */
const withoutQc = (o: Overview): Overview => ({
  ...o,
  states: { ...o.states, review: o.states.review + o.states.qc, qc: 0 },
  sentBack: 0,
});

type Seg = { value: number; color: string; label: string; key?: string };

/**
 * A scorecard: what it counts, the number, its share of the whole, a bar, and one line of
 * detail. When the bar splits into named parts (segments with a `key`), the detail line
 * becomes a key, one dot and number per part, so the split reads without a sentence.
 */
function Score({ label, value, share, of, segs, detail }: { label: string; value: string; share?: string; of?: string; segs: Seg[]; detail?: string }) {
  const total = segs.reduce((s, x) => s + x.value, 0) || 1;
  const keyed = segs.filter((s) => s.key && s.value > 0);
  return (
    <div className="ovc-score">
      <p className="ovc-score-label">{label}</p>
      <p className="ovc-score-value">{value}</p>
      {share ? (
        <p className="ovc-score-share">
          <b>{share}</b> {of}
        </p>
      ) : null}
      <span className="ovc-score-meter" role="img" aria-label={segs.map((s) => `${s.label} ${fmt(s.value)}`).join(', ')}>
        {segs.map((s) =>
          s.value > 0 ? <span key={s.label} style={{ flexGrow: s.value / total, background: s.color }} /> : null,
        )}
      </span>
      {keyed.length > 1 ? (
        <ul className="ovc-score-keys">
          {keyed.map((s) => (
            <li key={s.label}>
              <i style={{ background: s.color }} aria-hidden />
              <b>{fmt(s.value)}</b> {s.key}
            </li>
          ))}
        </ul>
      ) : detail ? (
        <p className="ovc-score-detail">{detail}</p>
      ) : null}
    </div>
  );
}

export default function DeskVariant({ project }: { project: Project }) {
  const o = withoutQc(buildOverview(project));
  const t = useThresholds(0.4, 0.95);
  const { share, note } = useShare();
  const r = routeAt(o, t.lo, t.hi);
  const withReviewers = o.states.review;
  const reviewedSoFar = o.toPeople - withReviewers;
  const rest = 'var(--rule2)';

  return (
    <div className="ovc">
      <header className="ovc-head">
        <div>
          <p className="page-eyebrow">{projectEyebrow(project)}</p>
          <h1 className="page-title">{project.name}</h1>
          <p className="page-lede">
            {o.done
              ? `All ${fmt(o.assets)} ${o.unit} approved and ready to export.`
              : `${fmt(o.states.approved)} of ${fmt(o.assets)} ${o.unit} approved: ${fmt(o.approvedAuto)} by AI, ${fmt(o.approvedHuman)} by reviewers.`}
          </p>
        </div>
        <div className="ovc-controls">
          <button className="btn btn-ghost btn-sm" onClick={share}>
            <Link2 size={15} aria-hidden /> Share
          </button>
          <button className="btn btn-ghost btn-sm" onClick={() => window.print()}>
            <Download size={15} aria-hidden /> Report PDF
          </button>
          {o.done ? (
            <button className="btn btn-primary btn-sm">
              <Download size={15} aria-hidden /> Export labels
            </button>
          ) : (
            <a className="btn btn-primary btn-sm" href={projectHref(project.id, 'review')}>
              Open review <ArrowRight size={15} aria-hidden />
            </a>
          )}
        </div>
        {note}
      </header>

      <section className="ovc-scores" aria-label="Scorecards">
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
          share={pctText(o.drafted / o.assets)}
          of={`of ${o.unit}`}
          segs={[
            { value: o.drafted, color: AI_COLOR, label: 'Annotated by AI' },
            { value: o.states.queued, color: rest, label: 'Not annotated yet' },
          ]}
          detail={o.states.queued ? `${fmt(o.states.queued)} not annotated yet` : `Every ${o.unitOne} has an AI annotation`}
        />
        <Score
          label="Approved by AI"
          value={fmt(o.autoAccepted)}
          share={pctText(o.autoAccepted / Math.max(1, o.drafted))}
          of="of AI annotations"
          segs={[
            { value: o.autoAccepted, color: AI_COLOR, label: 'Approved by AI' },
            { value: o.toPeople, color: rest, label: 'Sent to human review' },
          ]}
          detail="AI confidence 0.95 or higher, so no review"
        />
        <Score
          label="Sent to human review"
          value={fmt(o.toPeople)}
          share={pctText(o.toPeople / Math.max(1, o.drafted))}
          of="of AI annotations"
          segs={[
            { value: reviewedSoFar, color: STATE_COLOR.approved, label: 'Approved by reviewers', key: 'approved' },
            { value: withReviewers, color: STATE_COLOR.review, label: 'In human review', key: 'in review' },
          ]}
          detail={`All ${fmt(reviewedSoFar)} approved`}
        />
        <Score
          label="Approved"
          value={fmt(o.states.approved)}
          share={pctText(o.states.approved / o.assets)}
          of={`of ${o.unit}`}
          segs={[
            { value: o.approvedAuto, color: AI_COLOR, label: 'Approved by AI', key: 'by AI' },
            { value: o.approvedHuman, color: STATE_COLOR.approved, label: 'Approved by reviewers', key: 'by reviewers' },
            { value: o.remaining, color: rest, label: 'Not approved yet' },
          ]}
        />
        <Score
          label="AI accuracy"
          value={pctText(o.kept, 1)}
          share={fmt(o.labelsReviewed)}
          of={`${o.labelNoun} reviewed`}
          segs={[
            { value: o.labelsReviewed - o.corrections, color: 'var(--ink2)', label: 'Kept unchanged', key: 'kept' },
            { value: o.corrections, color: '#B9B2A3', label: 'Corrected by reviewers', key: 'corrected' },
          ]}
        />
      </section>

      <section className="ovc-grid is-1-1">
        <Figure
          title="AI approval threshold"
          sub={`At ${t.hi.toFixed(3).replace(/0$/, '')}, the AI approves ${pctText(1 - r.share)} and sends ${pctText(r.share)} to human review · about ${fmt(r.missed)} AI mistakes would be approved unseen`}
          legend={<RoutingKeys single />}
          table={routingTable(o, t.lo, t.hi)}
        >
          <Routing o={o} t={t} />
        </Figure>
        <Figure title="Reviewers" sub="How many each reviewed, and how often they changed the AI’s annotation">
          <PeopleTable o={o} compact lean />
        </Figure>
      </section>

      <section className="ovc-grid is-1">
        <Figure title="AI accuracy by class" sub="Where the AI is right, and where reviewers correct it">
          <ClassTable o={o} compact trend={false} />
        </Figure>
      </section>

      <p className="ov-sample-note">Sample data. Figures are illustrative and agree with the rest of the app.</p>
    </div>
  );
}
