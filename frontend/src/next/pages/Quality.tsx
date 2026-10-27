import { useState } from 'react';
import type { Project } from '../../showcase/content';
import { PageHead, ItemVisual, itemsFor, projectEyebrow, type Item } from './shared';
import { EmptyState } from './Review';

type Verdict = 'pending' | 'pass' | 'fail';
const verdictChip: Record<Verdict, [string, string]> = {
  pending: ['is-queued', 'Waiting'],
  pass: ['is-pass', 'Approved'],
  fail: ['is-fail', 'Sent back'],
};
const reviewers = ['M. Lee', 'S. Okafor', 'D. Costa', 'P. Nair', 'A. Rao', 'M. Lee'];

export function QualityPage({ project: p }: { project: Project }) {
  const items = itemsFor(p)
    .sort((a, b) => Number(Boolean(b.fix)) - Number(Boolean(a.fix)))
    .slice(0, 6);
  const [verdicts, setVerdicts] = useState<Record<string, Verdict>>(() =>
    Object.fromEntries(items.map((it, i) => [it.id, i === 2 ? 'pass' : 'pending'])),
  );
  const [selectedId, setSelectedId] = useState(items[0]?.id);

  if (p.qcPending === 0) {
    return (
      <div className="page">
        <PageHead eyebrow={projectEyebrow(p)} title="Quality check" />
        <EmptyState project={p} title="No samples waiting for QC" line="Every sampled item has been audited. New samples arrive here as reviewers submit work." />
      </div>
    );
  }

  const sel = items.find((it) => it.id === selectedId) ?? items[0];
  const reviewed = (it: Item) => it.fix ?? it.label;
  const setVerdict = (v: Verdict) => setVerdicts((s) => ({ ...s, [sel.id]: v }));

  return (
    <div className="page">
      <PageHead
        eyebrow={projectEyebrow(p)}
        title="Quality check"
        lede={`${p.qcPending} sampled ${p.unit} waiting for an independent check. Approve the reviewer's call, or send it back.`}
      />
      <div className="split split-even">
        <section className="card table-wrap" aria-label="Sampled items">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Item</th>
                <th scope="col">Reviewer</th>
                <th scope="col">Change</th>
                <th scope="col">Verdict</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it, i) => {
                const [cls, text] = verdictChip[verdicts[it.id]];
                return (
                  <tr
                    key={it.id}
                    className="row-link"
                    aria-selected={it.id === sel.id}
                    onClick={() => setSelectedId(it.id)}
                    style={it.id === sel.id ? { background: 'var(--hover)' } : undefined}
                  >
                    <td>
                      <button className="mono" style={{ border: 0, background: 'none', padding: 0, cursor: 'pointer', fontWeight: 600 }} onClick={() => setSelectedId(it.id)}>
                        {it.id}
                      </button>
                    </td>
                    <td>{reviewers[i]}</td>
                    <td>{it.fix ? <span>Corrected</span> : <span className="muted">Accepted</span>}</td>
                    <td>
                      <span className={`chip ${cls}`}>{text}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>

        <section className="card card-pad" aria-label={`Item ${sel.id}`}>
          <h2 className="h-section">Item {sel.id}</h2>
          <div className="compare">
            <div className="compare-col">
              <h3>AI draft</h3>
              <ItemVisual item={sel} masked={false} />
              <span className="compare-verdict">
                {sel.label} <span className="mono muted" style={{ fontWeight: 400 }}>{sel.conf.toFixed(2)}</span>
              </span>
            </div>
            <div className="compare-col">
              <h3>Reviewer</h3>
              <ItemVisual item={sel} masked={p.view === 'pii'} />
              <span className="compare-verdict">{reviewed(sel)}</span>
            </div>
            <div className="compare-col">
              <h3>QC</h3>
              <ItemVisual item={sel} masked={p.view === 'pii'} />
              <span className={`chip ${verdictChip[verdicts[sel.id]][0]}`} style={{ justifySelf: 'start' }}>
                {verdictChip[verdicts[sel.id]][1]}
              </span>
            </div>
          </div>
          <div className="page-actions" style={{ marginTop: 20 }}>
            <button className="btn btn-pass btn-sm" onClick={() => setVerdict('pass')}>
              Approve
            </button>
            <button className="btn btn-fail btn-sm" onClick={() => setVerdict('fail')}>
              Send back
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
