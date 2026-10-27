import { useState } from 'react';
import { Check, ChevronLeft, ChevronRight, CircleCheck, Download, Pencil, X } from 'lucide-react';
import type { Project } from '../../showcase/content';
import { projectHref } from '../router';
import { PageHead, ProjectSpecimen, itemsFor, projectEyebrow } from './shared';

type Decision = 'accept' | 'edit' | 'reject';

export function EmptyState({ title, line, project }: { title: string; line: string; project: Project }) {
  return (
    <section className="card empty">
      <span className="empty-icon">
        <CircleCheck size={24} aria-hidden />
      </span>
      <h2>{title}</h2>
      <p>{line}</p>
      <div className="page-actions">
        <a className="btn btn-ghost" href={projectHref(project.id)}>
          Open overview
        </a>
        <a className="btn btn-primary" href={projectHref(project.id)}>
          <Download size={16} aria-hidden /> Export labels
        </a>
      </div>
    </section>
  );
}

export function ReviewPage({ project: p }: { project: Project }) {
  const items = [...itemsFor(p)].sort((a, b) => a.conf - b.conf).slice(0, 8);
  const [decisions, setDecisions] = useState<Partial<Record<string, Decision>>>({});
  const [index, setIndex] = useState(1);

  if (p.reviewPending === 0) {
    return (
      <div className="page">
        <PageHead eyebrow={projectEyebrow(p)} title="Review" />
        <EmptyState
          project={p}
          title="Nothing waiting for review"
          line={`All ${p.approved.toLocaleString('en-GB')} ${p.unit} have been reviewed and passed quality check. New work appears here as soon as AI drafts it.`}
        />
      </div>
    );
  }

  // Pressing the active decision again clears it.
  const decide = (id: string, d: Decision) =>
    setDecisions((s) => {
      const next = { ...s };
      if (next[id] === d) delete next[id];
      else next[id] = d;
      return next;
    });
  const done = Object.keys(decisions).length;

  return (
    <div className="page">
      <PageHead
        eyebrow={projectEyebrow(p)}
        title="Review"
        lede={`${p.reviewPending} ${p.unit} waiting, lowest confidence first. Accept what's right, correct what isn't.`}
      />
      <section className="card bench">
        <div className="bench-canvas">
          <ProjectSpecimen project={p} stage="review" />
        </div>
        <aside className="bench-side" aria-label="Labels on this item">
          <div className="bench-side-head">
            <h2>Labels</h2>
            <span className="mono muted" style={{ fontSize: 12 }}>
              {done}/{items.length} decided
            </span>
          </div>
          <ul className="labels">
            {items.map((it) => {
              const d = decisions[it.id];
              const showFix = it.fix && (d === 'edit' || d === undefined);
              return (
                <li key={it.id} className={it.fix && !d ? 'is-flag' : ''}>
                  <span className="label-name">
                    {p.view === 'tracking' ? <b className="mono">{it.id}</b> : null}
                    {showFix ? (
                      <>
                        <s>{it.label}</s> {it.fix}
                      </>
                    ) : (
                      <span style={{ textDecoration: d === 'reject' ? 'line-through' : undefined }}>{it.label}</span>
                    )}
                    <em>{it.conf.toFixed(2)}</em>
                  </span>
                  <span className="label-actions">
                    <button className="icon-btn is-accept" aria-pressed={d === 'accept'} aria-label={`Accept ${it.label}`} onClick={() => decide(it.id, 'accept')}>
                      <Check size={15} />
                    </button>
                    <button className="icon-btn is-edit" aria-pressed={d === 'edit'} aria-label={`Correct ${it.label}`} onClick={() => decide(it.id, 'edit')}>
                      <Pencil size={14} />
                    </button>
                    <button className="icon-btn is-reject" aria-pressed={d === 'reject'} aria-label={`Reject ${it.label}`} onClick={() => decide(it.id, 'reject')}>
                      <X size={15} />
                    </button>
                  </span>
                </li>
              );
            })}
          </ul>
          <div className="bench-foot">
            <span className="pager">
              <button className="icon-btn" aria-label="Previous item" onClick={() => setIndex((i) => Math.max(1, i - 1))}>
                <ChevronLeft size={15} />
              </button>
              {index} / {p.reviewPending}
              <button className="icon-btn" aria-label="Next item" onClick={() => setIndex((i) => Math.min(p.reviewPending, i + 1))}>
                <ChevronRight size={15} />
              </button>
            </span>
            <span className="spacer" />
            <button
              className="btn btn-primary btn-sm"
              onClick={() => {
                setDecisions({});
                setIndex((i) => Math.min(p.reviewPending, i + 1));
              }}
            >
              Submit and next
            </button>
          </div>
        </aside>
      </section>
    </div>
  );
}
