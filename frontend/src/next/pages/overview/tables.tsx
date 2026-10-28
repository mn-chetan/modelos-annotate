/*
 * The Overview's tables and the hardest-items list. Columns marked is-opt step back on
 * phones so the essential ones fit without scrolling.
 */
import { SampleView } from './charts';
import { fmt, pctText, type Overview } from './model';

function Meter({ value, warn = false }: { value: number; warn?: boolean }) {
  return (
    <span className={`ov-meter${warn ? ' is-warn' : ''}`} aria-hidden>
      <span style={{ width: `${Math.max(2, value * 100)}%` }} />
    </span>
  );
}

const ROUTE_NAMES: Record<string, string> = {
  approvedByAi: 'Approved by AI',
  approved: 'Approved by reviewer',
  rejected: 'Rejected',
  toReview: 'In review',
  failed: 'AI failed',
  notRun: 'Not drafted',
};

/** AI accuracy by class, with a real sample of each. */
export function ClassTable({ o }: { o: Overview }) {
  const avg = o.kept ?? 1;
  const weak = (c: Overview['classes'][number]) => c.keptRate != null && c.reviewed >= 3 && c.keptRate < avg - 0.04;
  const noun = o.labelNoun[0].toUpperCase() + o.labelNoun.slice(1);
  return (
    <div className="ov-table-wrap">
      <table className="ov-table">
        <thead>
          <tr>
            <th scope="col">Class</th>
            <th scope="col" className="is-opt">
              Sample
            </th>
            <th scope="col" className="num">
              {noun}
            </th>
            <th scope="col" className="num is-opt">
              AI confidence
            </th>
            <th scope="col">AI accuracy</th>
            <th scope="col" className="num is-opt">
              Corrections
            </th>
          </tr>
        </thead>
        <tbody>
          {o.classes.map((c) => (
            <tr key={c.name} className={weak(c) ? 'is-flag' : undefined}>
              <th scope="row">
                <span className="ov-class">
                  <i style={{ background: c.color }} aria-hidden />
                  {c.name}
                </span>
              </th>
              <td className="ov-sample-cell is-opt">{c.sample ? <SampleView sample={c.sample} /> : <span className="muted">—</span>}</td>
              <td className="num">{fmt(c.labels)}</td>
              <td className="num is-opt">{c.conf == null ? <span className="muted">—</span> : c.conf.toFixed(2)}</td>
              <td>
                {c.keptRate == null ? (
                  <span className="muted">Not reviewed yet</span>
                ) : (
                  <span className="ov-meter-row">
                    <Meter value={c.keptRate} warn={weak(c)} />
                    <b className="num">{pctText(c.keptRate, 1)}</b>
                    <span className="muted num">of {fmt(c.reviewed)}</span>
                  </span>
                )}
              </td>
              <td className="num is-opt">{fmt(c.corrections)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="ov-footnote">
        AI accuracy: the share of the AI’s {o.labelNoun} reviewers kept unchanged, out of those they decided on.
        {o.classes.some(weak) && o.kept != null ? ` Highlighted: more than four points below the project’s ${pctText(o.kept, 1)}.` : ''}
      </p>
    </div>
  );
}

/** The items the AI found hardest, with the reviewer's correction where there was one. */
export function HardestItems({ o }: { o: Overview }) {
  return (
    <ul className="ov-hard">
      {o.hardest.map((it) => (
        <li key={it.id}>
          {it.sample ? <SampleView sample={it.sample} /> : <span className="ov-hard-blank" aria-hidden />}
          <p>
            <span className="mono">{it.conf.toFixed(2)}</span> AI: {it.label}
            {it.fix ? (
              <>
                <br />
                <b>Reviewer: {it.fix}</b>
              </>
            ) : null}
            <br />
            <span className="ov-hard-meta" title={it.name}>
              {it.name} · {ROUTE_NAMES[it.route] ?? it.route}
            </span>
          </p>
        </li>
      ))}
    </ul>
  );
}
