/*
 * New project, written as a brief: the name is the document's title and each decision a
 * numbered section. The margin keeps what the choices mean, and the one action, in view.
 */
import { useRef, useState } from 'react';
import { Check, Circle, FileText, Film, Image as ImageIcon } from 'lucide-react';
import { api } from '../../../services/api';
import { request, refreshProjects } from '../../store';
import { navigate } from '../../router';
import { formatBytes, modalities, tasks } from './model';
import { AddedNote, ClassChip, ClassEditor, DropZone, FileList, FileSummary, Rules } from './controls';
import { useDraft } from './useDraft';
import './new-project.css';

const icons = { image: ImageIcon, text: FileText, video: Film } as const;

/** The tasks the annotation service can run today, and what each is called there. */
const TARGETS: Record<string, { modality: 'image' | 'text'; task: string }> = {
  'Object detection': { modality: 'image', task: 'object_detection' },
  'Named entities': { modality: 'text', task: 'ENTITY_EXTRACTION' },
  Sentiment: { modality: 'text', task: 'SENTIMENT_ANALYSIS' },
  Classification: { modality: 'text', task: 'TEXT_CLASSIFICATION' },
};

export function NewProjectPage() {
  const d = useDraft();
  const nameRef = useRef<HTMLInputElement>(null);
  const classesRef = useRef<HTMLDivElement>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const uploaded = useRef(new Set<string>());
  const unit = modalities.find((m) => m.key === d.modality)!.unit;

  const target = TARGETS[d.task];
  const supported = d.modality !== 'video' && !!target;

  const create = async () => {
    if (busy || !target) return;
    if (!d.ready) {
      d.setShowProblems(true);
      if (d.problems.name) nameRef.current?.focus();
      else classesRef.current?.querySelector<HTMLInputElement>('.np-class-add input')?.focus();
      return;
    }
    setBusy(true);
    setError('');
    try {
      let id = createdId;
      if (!id) {
        const project = await request<{ id: string }>('/projects', {
          method: 'POST',
          body: JSON.stringify({
            name: d.name.trim(),
            goal: d.description,
            modality: target.modality,
            task_type: target.task,
            labels: d.classes.map((c) => c.name),
            label_ontology: d.classes.map((c) => ({ id: c.id, name: c.name, color: c.colour })),
            confidence_threshold: d.threshold,
            ...(target.modality === 'text' ? { sentiment_analysis_level: 'document', classification_analysis_level: 'document' } : {}),
            quality_policy: {
              confidence_threshold: d.threshold,
              auto_approve_threshold: d.threshold,
              // The share of reviewed work audited. (qc_sample_rate is the service's separate 2–5% spot check.)
              sample_rate: d.sample / 100,
            },
          }),
        });
        id = project.id;
        setCreatedId(id);
      }
      // One file at a time, remembering what landed, so a retry never uploads a file twice.
      for (const f of d.files) {
        if (uploaded.current.has(f.id)) continue;
        await api.uploadAssets(id, [f.file]);
        uploaded.current.add(f.id);
      }
      await refreshProjects();
      navigate({ id: 'project', projectId: id, tab: d.files.length ? 'ai' : 'overview' });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      await refreshProjects();
    } finally {
      setBusy(false);
    }
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
          <fieldset className="npa-fields" disabled={busy || !!createdId}>
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
        </fieldset>
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
                  At <b className="mono">{d.threshold.toFixed(2)}</b> or higher, the AI approves; below it goes to a person
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
            {!supported ? (
              <p className="npa-unsupported">
                {d.modality === 'video' ? 'Video' : d.task} projects can’t be created in this build. Image object detection, entities, sentiment and classification can.
              </p>
            ) : null}
            <button type="button" disabled={busy || !supported || !!d.fileStats.bad} className="btn btn-accent npa-create" onClick={create}>
              {busy ? (createdId ? 'Uploading…' : 'Creating…') : createdId ? 'Retry remaining uploads' : 'Create project'}
            </button>
            {error ? (
              <p className="npa-error" role="alert">
                {createdId ? 'The project is saved, but some files didn’t upload. ' : ''}
                {error}
              </p>
            ) : null}
            {createdId ? (
              <button type="button" className="btn btn-ghost npa-create" onClick={() => navigate({ id: 'project', projectId: createdId, tab: 'ai' })}>
                Open the saved project
              </button>
            ) : null}
          </div>
        </aside>
      </div>
    </div>
  );
}
