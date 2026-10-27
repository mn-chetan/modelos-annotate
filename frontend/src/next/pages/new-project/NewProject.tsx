/*
 * New project, written as a brief: the name is the document's title and each decision a
 * numbered section. The margin keeps what the choices mean, and the one action, in view.
 */
import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Check, Circle, FileText, Film, Image as ImageIcon, X } from 'lucide-react';
import { projects } from '../../../showcase/content';
import { navigate } from '../../router';
import { formatBytes, modalities, tasks } from './model';
import { AddedNote, ClassChip, ClassEditor, DropZone, FileList, FileSummary, Rules } from './controls';
import { useDraft, type Draft } from './useDraft';
import './new-project.css';

const icons = { image: ImageIcon, text: FileText, video: Film } as const;

/** The showcase has no API yet: say plainly what Create would do, and offer a sample like it. */
function Created({ draft, onClose }: { draft: Draft; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => ref.current?.focus(), []);
  const sample =
    projects.find((p) => p.modality === draft.modality && p.task === draft.task) ?? projects.find((p) => p.modality === draft.modality)!;
  const { ok, bytes } = draft.fileStats;
  return (
    <div className="np-created" role="status" tabIndex={-1} ref={ref}>
      <div>
        <p>
          <b>Showcase only: nothing was saved or uploaded.</b> With the live service this creates “{draft.name.trim()}” with{' '}
          {draft.classes.length} {draft.classes.length === 1 ? 'class' : 'classes'}
          {ok ? `, then uploads ${ok} ${ok === 1 ? 'file' : 'files'} (${formatBytes(bytes)})` : ''}.
        </p>
        <button type="button" className="np-link" onClick={() => navigate({ id: 'project', projectId: sample.id, tab: 'overview' })}>
          Open a sample {sample.task.toLowerCase()} project <ArrowRight size={13} aria-hidden />
        </button>
      </div>
      <button type="button" className="np-x" aria-label="Dismiss" onClick={onClose}>
        <X size={14} />
      </button>
    </div>
  );
}

export function NewProjectPage() {
  const d = useDraft();
  const nameRef = useRef<HTMLInputElement>(null);
  const classesRef = useRef<HTMLDivElement>(null);
  const [created, setCreated] = useState(false);
  const unit = modalities.find((m) => m.key === d.modality)!.unit;

  const create = () => {
    if (!d.ready) {
      d.setShowProblems(true);
      if (d.problems.name) nameRef.current?.focus();
      else classesRef.current?.querySelector<HTMLInputElement>('.np-class-add input')?.focus();
      return;
    }
    setCreated(true);
  };

  const checks = [
    { ok: !!d.name.trim(), text: d.name.trim() ? 'Named' : 'Needs a name' },
    { ok: d.classes.length > 0, text: d.classes.length ? `${d.classes.length} ${d.classes.length === 1 ? 'class' : 'classes'}` : 'Needs a class' },
    {
      ok: d.fileStats.ok > 0,
      optional: true,
      text: d.fileStats.ok ? `${d.fileStats.ok} ${d.fileStats.ok === 1 ? 'file' : 'files'} ready` : 'No files yet, you can add them later',
    },
  ];

  return (
    <div className="page npa">
      <p className="page-eyebrow">Workspace · New project</p>
      <div className="npa-desk">
        <article className="npa-sheet" aria-label="Project brief">
          <header className="npa-title">
            <label className="np-sr" htmlFor="npa-name">
              Project name
            </label>
            <input
              id="npa-name"
              ref={nameRef}
              className={`npa-name${d.showProblems && d.problems.name ? ' is-invalid' : ''}`}
              placeholder="Untitled project"
              value={d.name}
              maxLength={80}
              aria-invalid={d.showProblems && !!d.problems.name}
              aria-describedby={d.showProblems && d.problems.name ? 'npa-name-err' : undefined}
              onChange={(e) => d.setName(e.target.value)}
            />
            {d.showProblems && d.problems.name ? (
              <p id="npa-name-err" className="np-err">
                {d.problems.name}
              </p>
            ) : null}
            <label className="np-sr" htmlFor="npa-desc">
              Purpose
            </label>
            <textarea
              id="npa-desc"
              className="npa-desc"
              rows={1}
              placeholder="What is this project for? One line helps reviewers make the right call."
              value={d.description}
              maxLength={240}
              onChange={(e) => d.setDescription(e.target.value)}
            />
          </header>

          <section className="npa-sec" aria-labelledby="npa-s1">
            <div className="npa-margin">
              <span className="mono">01</span>
              <h2 id="npa-s1">Data</h2>
              <p>What the items are, and what to label on them.</p>
            </div>
            <div className="npa-body">
              <div className="npa-types" role="group" aria-label="Data type">
                {modalities.map(({ key, title, line }) => {
                  const Icon = icons[key];
                  return (
                    <button key={key} type="button" className="npa-type" aria-pressed={d.modality === key} onClick={() => d.setModality(key)}>
                      <Icon size={18} strokeWidth={1.7} aria-hidden />
                      <span>
                        <b>{title}</b>
                        <small>{line}</small>
                      </span>
                    </button>
                  );
                })}
              </div>
              <div className="npa-tasks" role="group" aria-label="Task">
                <span className="npa-k">Task</span>
                {tasks[d.modality].map((t) => (
                  <button key={t} type="button" className="pill-btn" aria-pressed={d.task === t} onClick={() => d.setTask(t)}>
                    {t}
                  </button>
                ))}
              </div>
            </div>
          </section>

          <section className="npa-sec" aria-labelledby="npa-s2">
            <div className="npa-margin">
              <span className="mono">02</span>
              <h2 id="npa-s2">Files</h2>
              <p>They upload once the project is created. You can add more later.</p>
            </div>
            <div className="npa-body">
              <DropZone draft={d} />
              <FileSummary draft={d} />
              <FileList draft={d} />
              <AddedNote draft={d} />
            </div>
          </section>

          <section className="npa-sec" aria-labelledby="npa-s3">
            <div className="npa-margin">
              <span className="mono">03</span>
              <h2 id="npa-s3">Classes</h2>
              <p>The labels people and the model choose from. Colours are how they’ll appear on the work.</p>
            </div>
            <div className="npa-body" ref={classesRef}>
              <ClassEditor draft={d} invalid={d.showProblems ? d.problems.classes : undefined} />
            </div>
          </section>

          <section className="npa-sec" aria-labelledby="npa-s4">
            <div className="npa-margin">
              <span className="mono">04</span>
              <h2 id="npa-s4">Review rules</h2>
              <p>Where people step in, and how much of their work is audited.</p>
            </div>
            <div className="npa-body">
              <Rules draft={d} />
            </div>
          </section>
        </article>

        <aside className="npa-aside" aria-label="Summary">
          <div className="npa-aside-in">
            <p className="npa-k">At a glance</p>
            <p className={`npa-glance-name${d.name.trim() ? '' : ' is-empty'}`}>{d.name.trim() || 'Untitled project'}</p>
            <p className="npa-glance-meta">
              {modalities.find((m) => m.key === d.modality)!.title} · {d.task}
            </p>
            <div className="npa-legend">
              {d.classes.map((c) => (
                <ClassChip key={c.id} c={c} />
              ))}
            </div>

            <ol className="npa-flow">
              <li>
                <span>
                  {d.fileStats.ok ? (
                    <>
                      <b>{d.fileStats.ok.toLocaleString('en-GB')}</b> {unit} upload ({formatBytes(d.fileStats.bytes)})
                    </>
                  ) : (
                    <>You add {unit}</>
                  )}
                </span>
              </li>
              <li>
                <span>AI drafts {d.task.toLowerCase()} labels</span>
              </li>
              <li>
                <span>
                  Below <b className="mono">{d.threshold.toFixed(2)}</b> goes to a person
                </span>
              </li>
              <li>
                <span>
                  <b className="mono">{d.sample}%</b> of reviewed work is audited
                </span>
              </li>
              <li>
                <span>Approved labels export</span>
              </li>
            </ol>

            <ul className="npa-checks" aria-label="Before you create">
              {checks.map((c) => (
                <li key={c.text} className={c.ok ? 'is-ok' : c.optional ? 'is-opt' : d.showProblems ? 'is-bad' : ''}>
                  {c.ok ? <Check size={14} aria-hidden /> : <Circle size={12} aria-hidden />}
                  {c.text}
                </li>
              ))}
            </ul>
            <button type="button" className="btn btn-accent npa-create" onClick={create}>
              Create project
            </button>
            {created ? <Created draft={d} onClose={() => setCreated(false)} /> : null}
          </div>
        </aside>
      </div>
    </div>
  );
}
