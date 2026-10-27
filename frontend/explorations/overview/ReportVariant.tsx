/*
 * Direction A · Report. Reading-first: the overview is the project's living report, written
 * as one dated document a lead can read in two minutes or forward as it stands. A
 * generated headline and standfirst lead, a ledger of three figures follows, then numbered
 * sections, and a dark block ends it with what to do next. Prints to PDF cleanly.
 */
import { ArrowRight, Download, Link2, Printer } from 'lucide-react';
import { projectHref } from '../../src/next/router';
import { projectEyebrow } from '../../src/next/pages/shared';
import { useShare } from './useShare';
import { buildOverview, fmt, hoursText, longDate, pctText, routeAt, statusText, ahtText, TODAY, type Overview } from './model';
import {
  Bands,
  Delta,
  Figure,
  Routing,
  RoutingKeys,
  StateBar,
  StateKeys,
  Throughput,
  ThroughputKeys,
  routingTable,
  stateTable,
  throughputTable,
  useThresholds,
} from './viz';
import { ClassTable, PeopleTable, Triage, actionHref } from './tables';
import type { Project } from '../../src/showcase/content';

const SECTIONS = [
  ['progress', 'Where the work stands'],
  ['routing', 'What people reviewed, and why'],
  ['quality', 'How good the labels are'],
  ['classes', 'Class by class'],
  ['people', 'The review team'],
  ['attention', 'Needs attention'],
] as const;

function headline(o: Overview) {
  if (o.done) return `All ${fmt(o.assets)} ${o.unit} approved and ready to export`;
  const lead = `${fmt(o.states.approved)} of ${fmt(o.assets)} ${o.unit} approved`;
  if (o.status === 'at risk') return `${lead}; at this pace the last ${fmt(o.remaining)} land after the due date`;
  return `${lead}; the last ${fmt(o.remaining)} clear by ${o.eta!.toLocaleDateString('en-GB', { weekday: 'long' })} at this pace`;
}

function standfirst(o: Overview) {
  const weakest = [...o.classes].sort((a, b) => a.keptRate - b.keptRate)[0];
  const share = Math.round((weakest.corrections / Math.max(1, o.corrections)) * 100);
  return `Reviewers kept ${pctText(o.kept, 1)} of the AI’s ${o.labelNoun} as drafted, and quality check passed ${pctText(o.qcPass, 1)} of what it sampled. “${weakest.name}” is where the model struggles most: it accounts for ${share}% of every correction.`;
}

export default function ReportVariant({ project }: { project: Project }) {
  const o = buildOverview(project);
  const t = useThresholds();
  const r = routeAt(o, t.lo, t.hi);
  const base = routeAt(o, 0.7, 0.95);
  const { share, note } = useShare();
  const week = Math.ceil(((TODAY.getTime() - new Date(2026, 0, 1).getTime()) / 86_400_000 + 4) / 7);
  const keptDelta = (o.weekly.kept[7] - o.weekly.kept[6]) * 100;
  const qcDelta = (o.weekly.qcPass[7] - o.weekly.qcPass[6]) * 100;

  return (
    <div className="ova">
      <header className="ova-bar">
        <div>
          <p className="page-eyebrow">{projectEyebrow(project)}</p>
          <h1 className="ova-bar-title">{project.name}</h1>
        </div>
        <div className="page-actions">
          <button className="btn btn-ghost btn-sm" onClick={share}>
            <Link2 size={15} aria-hidden /> Copy link
          </button>
          <button className="btn btn-ghost btn-sm" onClick={() => window.print()}>
            <Printer size={15} aria-hidden /> Download PDF
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

      <div className="ova-layout">
        <article className="ova-sheet" aria-label="Project report">
          <div className="ova-mast">
            <span>ModelOS Annotate · Project report · Week {week}</span>
            <span>{TODAY.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })} · sample data</span>
          </div>

          <p className={`ova-kicker is-${o.status.replace(' ', '-')}`}>
            {statusText[o.status]}
            {o.done ? '' : ` · due ${longDate(o.due)}`}
          </p>
          <h2 className="ova-headline">{headline(o)}</h2>
          <p className="ova-standfirst">{standfirst(o)}</p>

          <dl className="ova-meta">
            <div>
              <dt>Data</dt>
              <dd>
                {fmt(o.assets)} {o.unit}, {fmt(o.labels)} {o.labelNoun}
              </dd>
            </div>
            <div>
              <dt>Team</dt>
              <dd>
                {o.team} reviewers · {ahtText(o.ahtSec)} per {o.unitOne}
              </dd>
            </div>
            <div>
              <dt>Routing</dt>
              <dd>
                Auto-accept at 0.95 · audit below 0.70
              </dd>
            </div>
          </dl>

          <div className="ova-ledger">
            <div className="ova-fig is-hero">
              <span className="ova-fig-n">
                {Math.round((o.states.approved / o.assets) * 100)}
                <small>%</small>
              </span>
              <span className="ova-fig-l">
                of {o.unit} approved. {o.done ? 'Nothing left to review.' : `${fmt(o.remaining)} still in flight.`}
              </span>
            </div>
            <div className="ova-fig">
              <span className="ova-fig-n">
                {(o.kept * 100).toFixed(1)}
                <small>%</small>
              </span>
              <span className="ova-fig-l">
                of AI {o.labelNoun} kept as drafted. <Delta value={keptDelta} /> on last week.
              </span>
            </div>
            <div className="ova-fig">
              <span className="ova-fig-n">
                {(o.qcPass * 100).toFixed(1)}
                <small>%</small>
              </span>
              <span className="ova-fig-l">
                passed quality check. <Delta value={qcDelta} /> on last week.
              </span>
            </div>
          </div>

          <section className="ova-sec" id="ova-progress" aria-labelledby="ova-h-progress">
            <h3 className="ova-h" id="ova-h-progress">
              <span>1</span>Where the work stands
            </h3>
            <p className="ova-p">
              {o.done
                ? `Every ${o.unitOne} has passed through review and quality check.`
                : `${fmt(o.states.review)} ${o.unit} wait for a reviewer${o.sentBack ? `, ${fmt(o.sentBack)} of them sent back by QC` : ''}, and ${fmt(o.states.qc)} are in quality check. ${
                    o.states.queued ? `${fmt(o.states.queued)} have not been drafted by the AI yet. ` : ''
                  }The team has approved ${fmt(Math.round(o.perWorkingDay))} a working day this week against a plan of ${fmt(o.planned)}.`}
            </p>
            <Figure title="Every item, by state" table={stateTable(o)} legend={<StateKeys o={o} />}>
              <StateBar o={o} height={18} />
            </Figure>
            <Figure title={`${o.unit[0].toUpperCase() + o.unit.slice(1)} approved per day`} sub="Last four weeks · today so far is hatched" legend={<ThroughputKeys />} table={throughputTable(o)}>
              <Throughput o={o} />
            </Figure>
          </section>

          <section className="ova-sec" id="ova-routing" aria-labelledby="ova-h-routing">
            <h3 className="ova-h" id="ova-h-routing">
              <span>2</span>What people reviewed, and why
            </h3>
            <p className="ova-p">
              The AI scores every {o.unitOne}. At 0.95 and above it is accepted, with a 5% spot check in QC; below that a person reviews it, and below 0.70 an auditor
              checks the reviewer too. That sent {pctText(base.share)} of the work to people and saved about {hoursText(o.hoursSaved)} of review. Drag the lines to
              see what a different policy would cost.
            </p>
            <Figure title={`${o.unit[0].toUpperCase() + o.unit.slice(1)} by AI confidence`} sub="Lowest-scoring label in each item" legend={<RoutingKeys />} table={routingTable(o, t.lo, t.hi)}>
              <Routing o={o} t={t} />
            </Figure>
            <div className="ova-readout" aria-live="polite">
              <div>
                <b>{pctText(r.share)}</b>
                <span>sent to people</span>
                <Delta value={(r.share - base.share) * 100} better="down" />
              </div>
              <div>
                <b>{hoursText(r.hours)}</b>
                <span>of reviewer time</span>
              </div>
              <div>
                <b>≈ {fmt(r.missed)}</b>
                <span>AI errors accepted unseen</span>
                <Delta value={r.missed - base.missed} unit="" better="down" digits={0} />
              </div>
            </div>
            <p className="ova-note">Estimates assume the model’s confidence is calibrated: a label scored 0.96 is wrong about 4% of the time.</p>
          </section>

          <section className="ova-sec" id="ova-quality" aria-labelledby="ova-h-quality">
            <h3 className="ova-h" id="ova-h-quality">
              <span>3</span>How good the labels are
            </h3>
            <div className="ova-quality">
              <Figure title={o.bandsTitle} sub={`${fmt(o.qcChecked)} ${o.unit} checked by an auditor`}>
                <Bands o={o} />
              </Figure>
              <dl className="ova-facts">
                {o.fit ? (
                  <div>
                    <dt>{o.fit.name}</dt>
                    <dd>{o.fit.value}</dd>
                  </div>
                ) : null}
                <div>
                  <dt>Reviewer agreement</dt>
                  <dd>{pctText(o.agreement)}</dd>
                </div>
                <div>
                  <dt>Sent back by QC</dt>
                  <dd>{fmt(o.qcFailed)}</dd>
                </div>
                <div>
                  <dt>Errors found after approval</dt>
                  <dd>{pctText(o.leakage, 1)}</dd>
                </div>
              </dl>
            </div>
          </section>

          <section className="ova-sec" id="ova-classes" aria-labelledby="ova-h-classes">
            <h3 className="ova-h" id="ova-h-classes">
              <span>4</span>Class by class
            </h3>
            <ClassTable o={o} compact />
          </section>

          <section className="ova-sec" id="ova-people" aria-labelledby="ova-h-people">
            <h3 className="ova-h" id="ova-h-people">
              <span>5</span>The review team
            </h3>
            <PeopleTable o={o} compact />
          </section>

          <section className="ova-sec" id="ova-attention" aria-labelledby="ova-h-attention">
            <h3 className="ova-h" id="ova-h-attention">
              <span>6</span>Needs attention
            </h3>
            <Triage o={o} layout="row" />
          </section>

          <section className="ova-next" aria-label="What to do next">
            <p className="ova-next-kicker">What to do next</p>
            <ol>
              {o.actions.map((a, i) => (
                <li key={a.title}>
                  <span className="ova-next-n">{i + 1}</span>
                  <div>
                    <p className="ova-next-title">{a.title}</p>
                    <p className="ova-next-why">{a.why}</p>
                  </div>
                  <a href={actionHref(o, a.tab)}>
                    {a.cta} <ArrowRight size={14} aria-hidden />
                  </a>
                </li>
              ))}
            </ol>
          </section>

          <footer className="ova-foot">
            <span>Generated {TODAY.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}, 12:56 · ModelOS Annotate</span>
            <span>Sample data; projects and people are illustrative</span>
          </footer>
        </article>

        <nav className="ova-toc" aria-label="In this report">
          <p>In this report</p>
          <ol>
            {SECTIONS.map(([id, label], i) => (
              <li key={id}>
                {/* Buttons, not #anchors: the app's router owns the hash. */}
                <button type="button" onClick={() => document.getElementById(`ova-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
                  <span>{i + 1}</span>
                  {label}
                </button>
              </li>
            ))}
          </ol>
          <div className="ova-toc-status">
            <span className={`ova-dot is-${o.status.replace(' ', '-')}`} aria-hidden />
            <div>
              <b>{statusText[o.status]}</b>
              <small>{o.done ? 'Ready to export' : `Clears ${longDate(o.eta ?? o.due)} · due ${longDate(o.due)}`}</small>
            </div>
          </div>
        </nav>
      </div>
    </div>
  );
}
