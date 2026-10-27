/*
 * Overview: how much of the work did the AI do on its own, and how much went to people?
 * Six scorecards follow the pipeline (total, annotated by AI, approved by AI, sent to human
 * review, approved, AI accuracy). Below them: where the approval line sits and whether the
 * AI's confidence can be trusted, AI accuracy by class, the mistakes reviewers fix, the
 * hardest items, and the reviewers.
 *
 * Deliberately left out: anything measured over time, quality-check results and handling
 * time. Items in quality check count as in review. Reports folded into this page.
 */
import { useEffect, useState } from 'react';
import { ArrowRight, Download, Link2 } from 'lucide-react';
import type { Project } from '../../../showcase/content';
import { projectHref } from '../../router';
import { projectEyebrow } from '../shared';
import { AI_LINE, buildOverview, fmt, pctText, routeAt } from './model';
import {
  AI_COLOR,
  APPROVED_COLOR,
  Calibration,
  Figure,
  HBars,
  Heatmap,
  Key,
  REVIEW_COLOR,
  Routing,
  SampleView,
  SeqKey,
  calibrationTable,
  routingTable,
  useLine,
} from './charts';
import { ClassTable, HardestItems, PeopleTable } from './tables';
import './overview.css';

const REST = 'var(--rule2)';
const FIX_COLORS = ['#2A57C0', '#D39B0A', '#1F8A5B', '#8D4AA6', '#D2432C'];

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
    <div className="ov-score">
      <p className="ov-score-label">{label}</p>
      <p className="ov-score-value">{value}</p>
      {share ? (
        <p className="ov-score-share">
          <b>{share}</b> {of}
        </p>
      ) : null}
      <span className="ov-score-meter" role="img" aria-label={segs.map((s) => `${s.label} ${fmt(s.value)}`).join(', ')}>
        {segs.map((s) => (s.value > 0 ? <span key={s.label} style={{ flexGrow: s.value / total, background: s.color }} /> : null))}
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
      ) : detail ? (
        <p className="ov-score-detail">{detail}</p>
      ) : null}
    </div>
  );
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
  return { share, note };
}

export function OverviewPage({ project }: { project: Project }) {
  const o = buildOverview(project);
  const t = useLine();
  const { share, note } = useShare();
  const r = routeAt(o, t.line);
  const reviewedSoFar = o.toPeople - o.inReview;
  const lineText = t.line.toFixed(3).replace(/0$/, '');

  return (
    <div className="ov">
      <header className="ov-head">
        <div>
          <p className="page-eyebrow">{projectEyebrow(project)}</p>
          <h1 className="page-title">{project.name}</h1>
          <p className="page-lede">
            {o.done
              ? `All ${fmt(o.assets)} ${o.unit} approved and ready to export.`
              : `${fmt(o.approved)} of ${fmt(o.assets)} ${o.unit} approved: ${fmt(o.approvedAuto)} by AI, ${fmt(o.approvedHuman)} by reviewers.`}
          </p>
        </div>
        <div className="page-actions">
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
          share={pctText(o.drafted / o.assets)}
          of={`of ${o.unit}`}
          segs={[
            { value: o.drafted, color: AI_COLOR, label: 'Annotated by AI' },
            { value: o.queued, color: REST, label: 'Not annotated yet' },
          ]}
          detail={o.queued ? `${fmt(o.queued)} not annotated yet` : `Every ${o.unitOne} has an AI annotation`}
        />
        <Score
          label="Approved by AI"
          value={fmt(o.autoAccepted)}
          share={pctText(o.autoAccepted / Math.max(1, o.drafted))}
          of="of AI annotations"
          segs={[
            { value: o.autoAccepted, color: AI_COLOR, label: 'Approved by AI' },
            { value: o.toPeople, color: REST, label: 'Sent to human review' },
          ]}
          detail={`AI confidence ${AI_LINE} or higher, so no review`}
        />
        <Score
          label="Sent to human review"
          value={fmt(o.toPeople)}
          share={pctText(o.toPeople / Math.max(1, o.drafted))}
          of="of AI annotations"
          segs={[
            { value: reviewedSoFar, color: APPROVED_COLOR, label: 'Approved by reviewers', key: 'approved' },
            { value: o.inReview, color: REVIEW_COLOR, label: 'In human review', key: 'in review' },
          ]}
          detail={`All ${fmt(reviewedSoFar)} approved`}
        />
        <Score
          label="Approved"
          value={fmt(o.approved)}
          share={pctText(o.approved / o.assets)}
          of={`of ${o.unit}`}
          segs={[
            { value: o.approvedAuto, color: AI_COLOR, label: 'Approved by AI', key: 'by AI' },
            { value: o.approvedHuman, color: APPROVED_COLOR, label: 'Approved by reviewers', key: 'by reviewers' },
            { value: o.remaining, color: REST, label: 'Not approved yet' },
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

      <section className="ov-row is-1-1">
        <Figure
          title="AI approval threshold"
          sub={`At ${lineText}, the AI approves ${pctText(1 - r.share)} and sends ${pctText(r.share)} to human review · about ${fmt(r.missed)} AI mistakes would be approved unseen`}
          legend={
            <>
              <Key color={AI_COLOR}>Approved by AI</Key>
              <Key color={REVIEW_COLOR}>Sent to human review</Key>
            </>
          }
          table={routingTable(o, t.line)}
        >
          <Routing o={o} t={t} />
        </Figure>
        <Figure
          title="Can we trust the AI’s confidence?"
          sub="When the AI says it is 90% sure, is it right nine times in ten? Bars below the line mean it is overconfident."
          legend={
            <>
              <Key color={AI_COLOR}>Approved by AI</Key>
              <Key color={REVIEW_COLOR}>Sent to human review</Key>
              <Key color="var(--ink)" kind="line">
                Perfectly calibrated
              </Key>
            </>
          }
          table={calibrationTable(o)}
        >
          <Calibration o={o} line={t.line} />
        </Figure>
      </section>

      <section className="ov-row is-1">
        <Figure title="AI accuracy by class" sub="Where the AI is right, and where reviewers correct it">
          <ClassTable o={o} />
        </Figure>
      </section>

      <section className="ov-row is-1-1">
        <Figure title="Most common mix-ups" sub="What the AI called it, and what reviewers changed it to. Watch for these first.">
          <HBars
            labelW={210}
            rows={o.mixups.map((m) => ({
              key: `${m.from} → ${m.to}`,
              value: m.n,
              color: '#2F52B4',
              note: `AI said ${m.from}; reviewers changed it to ${m.to}`,
              label: (
                <span className="ov-pair">
                  {o.classes[m.toIndex].sample.kind === 'crop' ? <SampleView sample={o.classes[m.toIndex].sample} /> : null}
                  <span>
                    {m.from} <span className="muted">→</span> {m.to}
                  </span>
                </span>
              ),
            }))}
          />
        </Figure>
        <Figure title="What kind of fixes reviewers make" sub={`${fmt(o.corrections)} corrections, by kind`}>
          <HBars
            labelW={170}
            rows={o.fixes.map((f, i) => ({
              key: f.name,
              value: f.n,
              color: FIX_COLORS[i % FIX_COLORS.length],
              note: `${pctText(f.n / Math.max(1, o.corrections))} of corrections`,
              label: <span>{f.name}</span>,
            }))}
          />
        </Figure>
      </section>

      <section className="ov-row is-1">
        <Figure title="Hardest items" sub="The items the AI was least sure of, with the reviewer’s correction where there was one">
          <HardestItems project={project} />
        </Figure>
      </section>

      <section className="ov-row is-1-1">
        <Figure title="Reviewers" sub="How many each reviewed, and how often they changed the AI’s annotation">
          <PeopleTable o={o} />
        </Figure>
        <Figure title="Who corrects which classes" sub="How often each reviewer changes the AI, class by class" legend={<SeqKey low="Changes less" high="Changes more" />}>
          <Heatmap
            rows={o.people.map((p) => p.name)}
            cols={o.classes.map((c) => c.name)}
            values={o.byReviewer}
            rowTitle="Reviewer"
            colTitle="Class"
            describe={(ri, ci, v) => `${o.people[ri].name} changes the AI’s ${o.classes[ci].name} on ${pctText(v)}`}
          />
        </Figure>
      </section>

      <p className="ov-sample-note">Sample data. Figures are illustrative and agree with the rest of the app.</p>
    </div>
  );
}
