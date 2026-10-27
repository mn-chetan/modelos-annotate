import { ArrowRight, Check, Download } from 'lucide-react';
import type { Project } from '../../showcase/content';
import { projectHref, type ProjectTab } from '../router';
import { PageHead, ProjectSpecimen, fmt, projectEyebrow } from './shared';

type StepState = 'is-done' | 'is-active' | 'is-idle';

export function OverviewPage({ project: p }: { project: Project }) {
  const queued = p.assets - p.aiDone;
  const steps: { name: string; num: number; note: string; state: StepState; tab?: ProjectTab }[] = [
    { name: 'Intake', num: p.assets, note: `${p.unit} in the project`, state: 'is-done' },
    {
      name: 'AI pre-annotation',
      num: p.aiDone,
      note: queued ? `${fmt(queued)} still queued` : 'all drafted',
      state: queued ? 'is-active' : 'is-done',
      tab: 'ai',
    },
    { name: 'Human review', num: p.reviewPending, note: 'waiting for a person', state: p.reviewPending ? 'is-active' : 'is-done', tab: 'review' },
    { name: 'Quality check', num: p.qcPending, note: 'sampled for audit', state: p.qcPending ? 'is-active' : 'is-done', tab: 'quality' },
    { name: 'Export', num: p.approved, note: 'approved and ready', state: 'is-idle', tab: 'reports' },
  ];
  const caughtUp = p.reviewPending === 0 && p.qcPending === 0;

  return (
    <div className="page">
      <PageHead
        eyebrow={projectEyebrow(p)}
        title={p.name}
        lede={`${fmt(p.assets)} ${p.unit} · led by ${p.lead} · updated ${p.updated}`}
        actions={
          caughtUp ? (
            <a className="btn btn-primary" href={projectHref(p.id, 'reports')}>
              <Download size={16} aria-hidden /> Export labels
            </a>
          ) : (
            <a className="btn btn-primary" href={projectHref(p.id, 'review')}>
              Open review <ArrowRight size={16} aria-hidden />
            </a>
          )
        }
      />

      <section className="card card-pad" aria-label="Pipeline">
        <div className="pipe">
          {steps.map((s) => {
            const body = (
              <>
                <span className="pipe-name">
                  {s.state === 'is-done' ? <Check size={14} aria-hidden /> : null}
                  {s.name}
                </span>
                <span className="pipe-num">{fmt(s.num)}</span>
                <span className="pipe-note">{s.note}</span>
              </>
            );
            return s.tab ? (
              <a key={s.name} className={`pipe-step ${s.state}`} href={projectHref(p.id, s.tab)}>
                {body}
              </a>
            ) : (
              <div key={s.name} className={`pipe-step ${s.state}`}>
                {body}
              </div>
            );
          })}
        </div>
      </section>

      <div className="split">
        <section className="card card-pad">
          <h2 className="h-section">{caughtUp ? 'All caught up' : 'Next up'}</h2>
          <div style={{ display: 'grid', gap: 16 }}>
            <ProjectSpecimen project={p} stage={caughtUp ? 'qc' : 'review'} />
            {caughtUp ? (
              <p style={{ margin: 0, color: 'var(--ink2)' }}>
                Every {p.unit.replace(/s$/, '')} has been reviewed and passed quality check. The labels are ready to export.
              </p>
            ) : (
              <div className="toolbar">
                <p style={{ margin: 0, color: 'var(--ink2)' }}>
                  <b>{p.reviewPending}</b> {p.unit} are waiting for review, lowest confidence first.
                </p>
                <span className="spacer" />
                <a className="btn btn-ghost btn-sm" href={projectHref(p.id, 'review')}>
                  Start reviewing
                </a>
              </div>
            )}
          </div>
        </section>

        <section className="card card-pad">
          <h2 className="h-section">Recent activity</h2>
          <ul className="activity">
            <li>
              <span className="chip is-pass">QC</span>
              <span>Approved a sample of 24 {p.unit}</span>
              <time>12 min</time>
            </li>
            <li>
              <span className="chip is-review">Review</span>
              <span>Corrected 7 labels, rejected 1</span>
              <time>40 min</time>
            </li>
            <li>
              <span className="chip is-ai">AI</span>
              <span>Drafted labels for 120 new {p.unit}</span>
              <time>2 h</time>
            </li>
            <li>
              <span className="chip is-fail">QC</span>
              <span>Sent 3 {p.unit} back for rework</span>
              <time>5 h</time>
            </li>
            <li>
              <span className="chip is-neutral">Team</span>
              <span>Added classes to the guidelines</span>
              <time>Yesterday</time>
            </li>
          </ul>
        </section>
      </div>
    </div>
  );
}
