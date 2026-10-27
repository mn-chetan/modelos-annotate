/*
 * The Overview's tables, carrying the old dashboards' wider columns: per-class volume,
 * confidence, kept-as-drafted and trend with a real sample; reviewers with time per item,
 * edit rate, QC pass and the rubber-stamping safeguard; and the triage queues.
 */
import { AlertTriangle, ArrowRight, Gauge, GitCompareArrows, Sparkles } from 'lucide-react';
import { projectHref } from '../../src/next/router';
import { Delta, SampleView } from './viz';
import { ahtText, fmt, pctText, type Overview } from './model';

function Meter({ value, tone = 'ink' }: { value: number; tone?: 'ink' | 'pass' | 'warn' }) {
  return (
    <span className={`ov-meter is-${tone}`} aria-hidden>
      <span style={{ width: `${Math.max(2, value * 100)}%` }} />
    </span>
  );
}

export function ClassTable({
  o,
  samples = true,
  compact = false,
  lean = false,
  trend = true,
}: {
  o: Overview;
  samples?: boolean;
  compact?: boolean;
  lean?: boolean;
  /** Week-on-week change; off where the page leaves time out. */
  trend?: boolean;
}) {
  if (lean) samples = false;
  const avg = 1 - o.corrections / Math.max(1, o.labelsReviewed);
  return (
    <div className="ov-table-wrap">
      <table className={`ov-table ov-classes${compact ? ' is-compact' : ''}`}>
        <thead>
          <tr>
            <th scope="col">Class</th>
            {samples ? (
              <th scope="col" className="is-opt">
                Sample
              </th>
            ) : null}
            <th scope="col" className="num">
              {o.labelNoun[0].toUpperCase() + o.labelNoun.slice(1)}
            </th>
            {lean ? null : (
              <th scope="col" className="num is-opt">
                AI confidence
              </th>
            )}
            <th scope="col">AI accuracy</th>
            {lean ? null : (
              <th scope="col" className="num is-opt">
                Corrections
              </th>
            )}
            {trend ? (
              <th scope="col" className="num">
                Week on week
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {o.classes.map((c) => {
            const weak = c.keptRate < avg - 0.04;
            return (
              <tr key={c.name} className={weak ? 'is-flag' : undefined}>
                <th scope="row">
                  <span className="ov-class">
                    <i style={{ background: c.color }} aria-hidden />
                    {c.name}
                  </span>
                </th>
                {samples ? (
                  <td className="ov-sample-cell is-opt">
                    <SampleView sample={c.sample} />
                  </td>
                ) : null}
                <td className="num">{fmt(c.labels)}</td>
                {lean ? null : <td className="num is-opt">{c.conf.toFixed(2)}</td>}
                <td>
                  <span className="ov-meter-row">
                    <Meter value={c.keptRate} tone={weak ? 'warn' : 'ink'} />
                    <b className="num">{pctText(c.keptRate, 1)}</b>
                    {weak && !compact ? <span className="ov-flag-mark">Needs a guideline look</span> : null}
                  </span>
                </td>
                {lean ? null : <td className="num is-opt">{fmt(c.corrections)}</td>}
                {trend ? (
                  <td className="num">
                    <Delta value={c.trend} />
                  </td>
                ) : null}
              </tr>
            );
          })}
        </tbody>
      </table>
      {compact && o.classes.some((c) => c.keptRate < avg - 0.04) ? (
        <p className="ov-footnote">AI accuracy: the share of the AI’s {o.labelNoun} reviewers kept unchanged. Highlighted: more than four points below the project’s {pctText(avg, 1)}.</p>
      ) : null}
    </div>
  );
}

/** `lean` keeps only volume and edits: no QC results, no time measures, no safeguard flags. */
export function PeopleTable({ o, compact = false, lean = false }: { o: Overview; compact?: boolean; lean?: boolean }) {
  return (
    <div className="ov-table-wrap">
      <table className={`ov-table ov-people${compact ? ' is-compact' : ''}`}>
        <thead>
          <tr>
            <th scope="col">Reviewer</th>
            <th scope="col">{lean ? 'Reviewed' : 'Done of assigned'}</th>
            {lean ? null : (
              <th scope="col" className="num">
                Time per {o.unitOne}
              </th>
            )}
            <th scope="col" className="num">
              {lean ? 'Changed the AI’s annotation' : 'Edits the AI on'}
            </th>
            {lean ? null : (
              <>
                <th scope="col" className="num">
                  QC pass
                </th>
                <th scope="col">Safeguards</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {o.people.map((p) => (
            <tr key={p.name} className={p.flags.length && !lean ? 'is-flag' : undefined}>
              <th scope="row">
                <span className="ov-person">
                  <span className="ov-av" aria-hidden>
                    {p.initials}
                  </span>
                  {p.name}
                </span>
              </th>
              <td>
                <span className="ov-meter-row">
                  <Meter value={p.assigned ? p.done / p.assigned : 1} />
                  <span className="num">
                    {fmt(p.done)}
                    <span className="muted"> / {fmt(p.assigned)}</span>
                  </span>
                </span>
              </td>
              {lean ? null : <td className="num">{ahtText(p.ahtSec)}</td>}
              <td className="num">{pctText(p.editRate)}</td>
              {lean ? null : <td className="num">{pctText(p.qcPass, 1)}</td>}
              {lean ? null : (
              <td>
                {p.flags.length ? (
                  p.flags.map((f) => (
                    <span key={f} className="chip is-review ov-flag-chip">
                      <AlertTriangle size={12} aria-hidden />
                      {f === 'fast' ? 'Fast, few edits' : 'Below QC bar'}
                    </span>
                  ))
                ) : (
                  <span className="muted">None</span>
                )}
              </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {lean ? null : (
      <p className="ov-footnote">
        Fast, few edits: under half the team’s median time with edits on under 40% of the usual share, a sign of approving without checking. Below QC bar: under
        93% pass.
      </p>
      )}
    </div>
  );
}

export function Triage({ o, layout = 'list' }: { o: Overview; layout?: 'list' | 'row' }) {
  const items = [
    {
      icon: GitCompareArrows,
      n: o.triage.disputed,
      title: 'Disputed',
      line: `Reviewer and QC disagree on the label or its extent.`,
      tab: 'quality' as const,
      cta: 'Resolve',
    },
    {
      icon: Gauge,
      n: o.triage.fast,
      title: 'Approved fast, no edits',
      line: `Submitted well under the usual time without a change. Worth a second look.`,
      tab: 'quality' as const,
      cta: 'Audit',
    },
    {
      icon: Sparkles,
      n: o.triage.edge,
      title: 'Edge cases for retraining',
      line: `Drafted below 0.70 confidence and corrected by people: the model’s best lessons.`,
      tab: 'ai' as const,
      cta: 'Collect',
    },
  ];
  return (
    <ul className={`ov-triage is-${layout}`}>
      {items.map(({ icon: Icon, n, title, line, tab, cta }) => (
        <li key={title} className={n ? undefined : 'is-zero'}>
          <Icon size={16} strokeWidth={1.7} aria-hidden />
          <div>
            <p className="ov-triage-head">
              <b>{fmt(n)}</b> {title}
            </p>
            <p className="ov-triage-line">{line}</p>
          </div>
          {n ? (
            <a className="ov-link" href={projectHref(o.project.id, tab)}>
              {cta} <ArrowRight size={13} aria-hidden />
            </a>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function actionHref(o: Overview, tab: Overview['actions'][number]['tab']) {
  return projectHref(o.project.id, tab);
}
