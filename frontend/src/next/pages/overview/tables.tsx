/*
 * The Overview's tables and the hardest-items list. Columns marked is-opt step back on
 * phones so the essential ones fit without scrolling.
 */
import type { Project } from '../../../showcase/content';
import { ItemVisual, itemsFor } from '../shared';
import { SampleView } from './charts';
import { fmt, pctText, type Overview } from './model';

function Meter({ value, warn = false }: { value: number; warn?: boolean }) {
  return (
    <span className={`ov-meter${warn ? ' is-warn' : ''}`} aria-hidden>
      <span style={{ width: `${Math.max(2, value * 100)}%` }} />
    </span>
  );
}

/** AI accuracy by class, with a real sample of each. */
export function ClassTable({ o }: { o: Overview }) {
  const avg = 1 - o.corrections / Math.max(1, o.labelsReviewed);
  const weak = (keptRate: number) => keptRate < avg - 0.04;
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
              {o.labelNoun[0].toUpperCase() + o.labelNoun.slice(1)}
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
            <tr key={c.name} className={weak(c.keptRate) ? 'is-flag' : undefined}>
              <th scope="row">
                <span className="ov-class">
                  <i style={{ background: c.color }} aria-hidden />
                  {c.name}
                </span>
              </th>
              <td className="ov-sample-cell is-opt">
                <SampleView sample={c.sample} />
              </td>
              <td className="num">{fmt(c.labels)}</td>
              <td className="num is-opt">{c.conf.toFixed(2)}</td>
              <td>
                <span className="ov-meter-row">
                  <Meter value={c.keptRate} warn={weak(c.keptRate)} />
                  <b className="num">{pctText(c.keptRate, 1)}</b>
                </span>
              </td>
              <td className="num is-opt">{fmt(c.corrections)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="ov-footnote">
        AI accuracy: the share of the AI’s {o.labelNoun} reviewers kept unchanged.
        {o.classes.some((c) => weak(c.keptRate)) ? ` Highlighted: more than four points below the project’s ${pctText(avg, 1)}.` : ''}
      </p>
    </div>
  );
}

/** Each reviewer: how many they reviewed, and how often they changed the AI. */
export function PeopleTable({ o }: { o: Overview }) {
  return (
    <div className="ov-table-wrap">
      <table className="ov-table">
        <thead>
          <tr>
            <th scope="col">Reviewer</th>
            <th scope="col">Reviewed</th>
            <th scope="col" className="num">
              Changed the AI’s annotation
            </th>
          </tr>
        </thead>
        <tbody>
          {o.people.map((p) => (
            <tr key={p.name}>
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
              <td className="num">{pctText(p.editRate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The items the AI found hardest, with the reviewer's correction where there was one. */
export function HardestItems({ project }: { project: Project }) {
  const items = itemsFor(project)
    .sort((a, b) => a.conf - b.conf)
    .slice(0, 6);
  return (
    <ul className="ov-hard">
      {items.map((it) => (
        <li key={it.id}>
          <ItemVisual item={it} />
          <p>
            <span className="mono">{it.conf.toFixed(2)}</span> AI: {it.label}
            {it.fix ? (
              <>
                <br />
                <b>Reviewer: {it.fix}</b>
              </>
            ) : null}
          </p>
        </li>
      ))}
    </ul>
  );
}
