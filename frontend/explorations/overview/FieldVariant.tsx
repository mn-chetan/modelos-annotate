/*
 * Direction B · Field. Work-first and explorable: the project is drawn as its material,
 * every item one square, coloured by where it stands. State filters, the flow from intake
 * to approval and the squares themselves all drive one inspector, so a lead can go from
 * "how much is left" to the item that explains it without leaving the page.
 */
import { useState } from 'react';
import { ArrowRight, Download, Link2, X } from 'lucide-react';
import { projectHref, type ProjectTab } from '../../src/next/router';
import { projectEyebrow } from '../../src/next/pages/shared';
import type { Project } from '../../src/showcase/content';
import { useShare } from './useShare';
import {
  SENT_BACK,
  STATE_COLOR,
  STATE_NAME,
  STATE_ORDER,
  ahtText,
  buildOverview,
  fmt,
  hoursText,
  itemId,
  longDate,
  pctText,
  routeAt,
  statusText,
  type ItemState,
  type Overview,
} from './model';
import {
  Bands,
  Field,
  Figure,
  Flow,
  Routing,
  RoutingKeys,
  SampleView,
  Throughput,
  ThroughputKeys,
  flowModel,
  flowTable,
  metaLine,
  routingTable,
  throughputTable,
  useThresholds,
} from './viz';
import { ClassTable, PeopleTable, Triage } from './tables';
import { Activity } from './Activity';

type Sel = { kind: 'state'; state: ItemState | 'back' } | { kind: 'node'; id: string } | { kind: 'item'; i: number } | null;

function Cta({ o, tab, children }: { o: Overview; tab: ProjectTab; children: string }) {
  return (
    <a className="btn btn-ghost btn-sm" href={projectHref(o.project.id, tab)}>
      {children} <ArrowRight size={14} aria-hidden />
    </a>
  );
}

function Inspector({ o, sel, clear }: { o: Overview; sel: Sel; clear: () => void }) {
  const head = (kicker: string, n: number | string, line: string, swatch?: string, hollow?: boolean) => (
    <>
      <p className="ovb-insp-kicker">
        {swatch || hollow ? <i className={hollow ? 'is-hollow' : ''} style={swatch ? { background: swatch } : undefined} aria-hidden /> : null}
        {kicker}
      </p>
      <p className="ovb-insp-n">{typeof n === 'number' ? fmt(n) : n}</p>
      <p className="ovb-insp-line">{line}</p>
    </>
  );
  const facts = (rows: [string, string][]) => (
    <dl className="ovb-facts">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );

  let body;
  if (!sel) {
    body = (
      <>
        {head('The whole project', `${Math.round((o.states.approved / o.assets) * 100)}%`, `${fmt(o.states.approved)} of ${fmt(o.assets)} ${o.unit} approved`)}
        <p className={`ovb-status is-${o.status.replace(' ', '-')}`}>
          {statusText[o.status]}
          <span>{o.done ? ' · ready to export' : ` · clears ${longDate(o.eta ?? o.due)}, due ${longDate(o.due)}`}</span>
        </p>
        {facts([
          ['Kept as drafted', pctText(o.kept, 1)],
          ['QC pass rate', pctText(o.qcPass, 1)],
          ['Sent to people', pctText(o.toPeople / Math.max(1, o.drafted))],
          ['Review time saved', hoursText(o.hoursSaved)],
        ])}
        <p className="ovb-hint">Pick a state, a step in the flow or any square to look closer.</p>
      </>
    );
  } else if (sel.kind === 'item') {
    const f = o.field[sel.i];
    const cls = o.classes[sel.i % o.classes.length];
    const state = f.back ? 'Sent back by QC' : STATE_NAME[f.state];
    body = (
      <>
        {head(state, itemId(o, sel.i), f.state === 'queued' ? 'Uploaded; the AI has not drafted it yet.' : `Lowest AI confidence ${f.conf.toFixed(2)} · ${cls.name}`, f.back ? SENT_BACK : STATE_COLOR[f.state], f.state === 'queued')}
        {f.state !== 'queued' ? (
          <div className="ovb-insp-sample">
            <SampleView sample={cls.sample} size="md" />
            <span className="ovb-insp-cap">Sample from this class</span>
          </div>
        ) : null}
        {f.state === 'review' ? <Cta o={o} tab="review">Review it</Cta> : f.state === 'qc' ? <Cta o={o} tab="quality">Check it</Cta> : f.state === 'approved' ? <Cta o={o} tab="ai">See its labels</Cta> : null}
      </>
    );
  } else {
    const key = sel.kind === 'state' ? sel.state : sel.id;
    switch (key) {
      case 'approved':
        body = (
          <>
            {head('Approved', o.states.approved, `${pctText(o.states.approved / o.assets)} of the project, with a full review trail`, STATE_COLOR.approved)}
            {facts([
              ['Accepted automatically', fmt(o.approvedAuto)],
              ['Approved by a reviewer', fmt(o.approvedHuman)],
              ['Errors found later', pctText(o.leakage, 1)],
            ])}
            <button className="btn btn-ghost btn-sm">
              <Download size={14} aria-hidden /> Export approved
            </button>
          </>
        );
        break;
      case 'qc':
        body = (
          <>
            {head('In quality check', o.states.qc, 'Sampled for an independent audit', STATE_COLOR.qc)}
            {facts([
              ['Pass rate so far', pctText(o.qcPass, 1)],
              ['Checked to date', fmt(o.qcChecked)],
              ['Sent back to date', fmt(o.qcFailed)],
            ])}
            <Cta o={o} tab="quality">
              Open quality check
            </Cta>
          </>
        );
        break;
      case 'review':
        body = (
          <>
            {head('Waiting for review', o.states.review, 'Lowest confidence first', STATE_COLOR.review)}
            {facts([
              ['Sent back by QC', fmt(o.sentBack)],
              ['Time to clear', hoursText((o.states.review * o.ahtSec) / 3600)],
              ['Reviewers on it', String(o.team)],
            ])}
            <Cta o={o} tab="review">
              Open review
            </Cta>
          </>
        );
        break;
      case 'back':
        body = (
          <>
            {head('Sent back by QC', o.sentBack, 'Failed an audit and returned to a reviewer', SENT_BACK)}
            {facts([
              ['Pass rate', pctText(o.qcPass, 1)],
              ['Most corrected class', [...o.classes].sort((a, b) => a.keptRate - b.keptRate)[0].name],
            ])}
            <Cta o={o} tab="review">
              Open review
            </Cta>
          </>
        );
        break;
      case 'queued':
      case 'q1':
      case 'q2':
      case 'q3':
        body = (
          <>{head('Waiting for AI', o.states.queued, 'Uploaded, not drafted yet. Drafts arrive in batches.', undefined, true)}</>
        );
        break;
      case 'auto': {
        body = (
          <>
            {head('Accepted automatically', o.autoAccepted, `AI confidence 0.95 or higher · ${pctText(o.autoAccepted / Math.max(1, o.drafted))} of drafts`)}
            {facts([
              ['Spot-checked in QC', '5%'],
              ['Review time saved', hoursText(o.hoursSaved)],
              ['Est. errors let through', `≈ ${fmt(routeAt(o, 0.7, 0.95).missed)}`],
            ])}
            <Cta o={o} tab="ai">
              See AI results
            </Cta>
          </>
        );
        break;
      }
      case 'people':
        body = (
          <>
            {head('Sent to people', o.toPeople, `Below 0.95 confidence · ${pctText(o.toPeople / Math.max(1, o.drafted))} of drafts`)}
            {facts([
              ['Also audited (below 0.70)', fmt(o.audited)],
              ['Reviewer time so far', hoursText(o.reviewHours)],
              ['Time per item', ahtText(o.ahtSec)],
            ])}
            <Cta o={o} tab="review">
              Open review
            </Cta>
          </>
        );
        break;
      default: {
        const nd = flowModel(o).nodes.find((n) => n.id === key);
        body = <>{head(nd?.label ?? '', nd?.n ?? 0, key === 'in' ? `${fmt(o.labels)} ${o.labelNoun} across the project` : 'Every item gets an AI draft with a confidence score')}</>;
      }
    }
  }

  return (
    <aside className="ovb-insp" aria-label="Inspector" aria-live="polite">
      {sel ? (
        <button className="ovb-insp-close" onClick={clear} aria-label="Back to the whole project">
          <X size={15} aria-hidden /> Whole project
        </button>
      ) : null}
      {body}
    </aside>
  );
}

export default function FieldVariant({ project }: { project: Project }) {
  const o = buildOverview(project);
  const t = useThresholds();
  const [sel, setSel] = useState<Sel>(null);
  const { share, note } = useShare();

  const highlight: ItemState | 'back' | null =
    sel?.kind === 'state' ? sel.state : sel?.kind === 'node' ? (flowModel(o).nodes.find((n) => n.id === sel.id)?.state ?? null) : null;
  const flowSel = sel?.kind === 'node' ? sel.id : sel?.kind === 'state' ? ({ approved: 'approved', qc: 'qc', review: 'review', queued: 'q3', back: 'review' } as const)[sel.state] : null;
  const filters: (ItemState | 'back')[] = [...STATE_ORDER.filter((s) => o.states[s] > 0), ...(o.sentBack ? (['back'] as const) : [])];

  return (
    <div className="ovb">
      <header className="ovb-head">
        <div>
          <p className="page-eyebrow">{projectEyebrow(project)}</p>
          <h1 className="page-title">{project.name}</h1>
          <p className="page-lede">{metaLine(o)}</p>
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

      <section className="ovb-hero" aria-label="Every item in the project">
        <div className="ovb-field">
          <div className="ovb-field-head">
            <h2 className="ovb-h">
              Every {o.unitOne}, one square{o.unitPerSquare > 1 ? <small> · each square is {o.unitPerSquare} {o.unit}</small> : null}
            </h2>
            <div className="ovb-filters" role="group" aria-label="Show state">
              {filters.map((s) => {
                const on = highlight === s;
                const n = s === 'back' ? o.sentBack : o.states[s];
                return (
                  <button key={s} aria-pressed={on} onClick={() => setSel(on ? null : { kind: 'state', state: s })}>
                    <i className={s === 'queued' ? 'is-hollow' : ''} style={s === 'queued' ? undefined : { background: s === 'back' ? SENT_BACK : STATE_COLOR[s] }} aria-hidden />
                    {s === 'back' ? 'Sent back' : STATE_NAME[s]}
                    <b>{fmt(n)}</b>
                  </button>
                );
              })}
            </div>
          </div>
          <Field o={o} cell={11} highlight={highlight} onPick={(i) => setSel({ kind: 'item', i })} maxHeight={420} />
          <p className="ovb-field-foot">Oldest uploads first, reading left to right. Newer batches are still moving through review.</p>
        </div>
        <Inspector o={o} sel={sel} clear={() => setSel(null)} />
      </section>

      <section className="ovb-sec" aria-labelledby="ovb-h-flow">
        <Figure title={<span id="ovb-h-flow">How work flows</span>} sub="From upload to approval. Pick a step to focus it." table={flowTable(o)} className="ovb-flow">
          <Flow o={o} selected={flowSel} onSelect={(id) => setSel(id ? { kind: 'node', id } : null)} />
        </Figure>
      </section>

      <section className="ovb-trio" aria-label="Pace, routing and quality">
        <Figure title="Approved per day" sub="Last two weeks · today so far is hatched" legend={<ThroughputKeys />} table={throughputTable(o, 14)}>
          <Throughput o={o} span={14} height={200} />
        </Figure>
        <Figure title="Routing by AI confidence" sub={`${pctText(routeAt(o, t.lo, t.hi).share)} to people · ${hoursText(routeAt(o, t.lo, t.hi).hours)} of review`} legend={<RoutingKeys />} table={routingTable(o, t.lo, t.hi)}>
          <Routing o={o} t={t} height={200} />
        </Figure>
        <Figure title={o.bandsTitle} sub={`${fmt(o.qcChecked)} audited · agreement ${pctText(o.agreement)}${o.fit ? ` · ${o.fit.name} ${o.fit.value}` : ''}`}>
          <Bands o={o} />
          <dl className="ovb-facts is-row">
            <div>
              <dt>QC pass</dt>
              <dd>{pctText(o.qcPass, 1)}</dd>
            </div>
            <div>
              <dt>Kept as drafted</dt>
              <dd>{pctText(o.kept, 1)}</dd>
            </div>
            <div>
              <dt>Found later</dt>
              <dd>{pctText(o.leakage, 1)}</dd>
            </div>
          </dl>
        </Figure>
      </section>

      <section className="ovb-sec" aria-labelledby="ovb-h-classes">
        <h2 className="ovb-h" id="ovb-h-classes">
          Class by class
        </h2>
        <ClassTable o={o} />
      </section>

      <section className="ovb-split">
        <div>
          <h2 className="ovb-h">The review team</h2>
          <PeopleTable o={o} compact />
        </div>
        <div>
          <h2 className="ovb-h">Needs attention</h2>
          <Triage o={o} />
          <h2 className="ovb-h ovb-h-gap">Recent activity</h2>
          <Activity o={o} />
        </div>
      </section>
      <p className="ov-sample-note">Sample data. Figures are illustrative and agree with the rest of the app.</p>
    </div>
  );
}
