/*
 * B · Steps. One question at a time, asked in plain words, with the answers so far kept
 * in an index beside it. The last step reads back the whole project before creating it.
 * Axis: progressive focus over overview.
 */
import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, FileText, Film, Image as ImageIcon } from 'lucide-react';
import { images } from '../../src/showcase/content';
import { formatBytes, modalities, tasks } from './model';
import { AddedNote, ClassChip, ClassEditor, CreatedNote, DropZone, FileList, FileSummary, Rules } from './parts';
import { useDraft, type Draft } from './useDraft';

const icons = { image: ImageIcon, text: FileText, video: Film } as const;

type StepKey = 'name' | 'data' | 'files' | 'classes' | 'check';
const STEPS: { key: StepKey; title: string }[] = [
  { key: 'name', title: 'Name' },
  { key: 'data', title: 'Data' },
  { key: 'files', title: 'Files' },
  { key: 'classes', title: 'Classes' },
  { key: 'check', title: 'Check and create' },
];

function answer(key: StepKey, d: Draft) {
  switch (key) {
    case 'name':
      return d.name.trim() || null;
    case 'data':
      return `${modalities.find((m) => m.key === d.modality)!.title} · ${d.task}`;
    case 'files':
      return d.fileStats.ok ? `${d.fileStats.ok.toLocaleString('en-GB')} ready · ${formatBytes(d.fileStats.bytes)}` : null;
    case 'classes':
      return d.classes.length ? (
        <span className="npb-dots">
          {d.classes.slice(0, 8).map((c) => (
            <i key={c.id} style={{ background: c.colour }} />
          ))}
          {d.classes.length} {d.classes.length === 1 ? 'class' : 'classes'}
        </span>
      ) : null;
    default:
      return null;
  }
}

function TypeArt({ k }: { k: 'image' | 'text' | 'video' }) {
  if (k === 'text')
    return (
      <span className="npb-art is-text" aria-hidden>
        <span>
          <mark style={{ ['--c' as string]: '#2A78D6' }}>Anika Rao</mark> runs operations at{' '}
          <mark style={{ ['--c' as string]: '#EB6834' }}>Halden Freight</mark>
        </span>
      </span>
    );
  return (
    <span className={`npb-art is-${k}`} aria-hidden>
      <img src={k === 'image' ? images.street : images.buses} alt="" />
      {k === 'video' ? <span className="npb-sprockets" /> : <span className="npb-art-box" />}
    </span>
  );
}

export default function StepsVariant() {
  const d = useDraft();
  const [step, setStep] = useState(0);
  const [reached, setReached] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const first = useRef(true);
  const key = STEPS[step].key;
  const unit = modalities.find((m) => m.key === d.modality)!.unit;

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (key === 'name') nameRef.current?.focus();
    else heading.current?.focus();
  }, [step, key]);

  const go = (i: number) => {
    setError(null);
    setStep(i);
    setReached((r) => Math.max(r, i));
  };
  const problemAt = (k: StepKey) => (k === 'name' ? d.problems.name : k === 'classes' ? d.problems.classes : undefined);
  const next = () => {
    const p = problemAt(key);
    if (p) {
      setError(p);
      if (key === 'name') nameRef.current?.focus();
      return;
    }
    if (key === 'check') {
      const bad = STEPS.findIndex((s) => problemAt(s.key));
      if (bad >= 0) return go(bad);
      setCreated(true);
      return;
    }
    go(step + 1);
  };

  const continueLabel =
    key === 'check' ? 'Create project' : key === 'files' && !d.fileStats.ok ? 'Continue without files' : 'Continue';

  return (
    <div className="page npb">
      <nav className="npb-index" aria-label="New project steps">
        <p className="page-eyebrow">New project</p>
        <ol>
          {STEPS.map((s, i) => {
            const a = answer(s.key, d);
            const can = i <= reached;
            return (
              <li key={s.key} className={`${i === step ? 'is-on' : ''}${i < step || (can && a) ? ' is-done' : ''}`}>
                <button type="button" disabled={!can} aria-current={i === step ? 'step' : undefined} onClick={() => go(i)}>
                  <span className="npb-n mono">{i < step && !problemAt(s.key) ? <Check size={12} /> : i + 1}</span>
                  <span className="npb-t">
                    {s.title}
                    {a && i !== step ? <small>{a}</small> : null}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
        <p className="npb-progress mono" aria-hidden>
          Step {step + 1} of {STEPS.length}
        </p>
      </nav>

      <div className="npb-stage">
        <form
          key={key}
          className="npb-step"
          onSubmit={(e) => {
            e.preventDefault();
            next();
          }}
        >
          {key === 'name' ? (
            <>
              <h1 ref={heading} tabIndex={-1} className="npb-q">
                What should we call this project?
              </h1>
              <p className="npb-hint">Something your team will recognise in the project list.</p>
              <input
                ref={nameRef}
                autoFocus
                className={`npb-big${error ? ' is-invalid' : ''}`}
                placeholder="e.g. Urban traffic detection"
                aria-label="Project name"
                aria-invalid={!!error}
                aria-describedby={error ? 'npb-err' : undefined}
                value={d.name}
                maxLength={80}
                onChange={(e) => {
                  d.setName(e.target.value);
                  setError(null);
                }}
              />
              {error ? (
                <p id="npb-err" className="np-err">
                  {error}
                </p>
              ) : null}
              <label className="npb-label" htmlFor="npb-desc">
                Purpose <span className="muted">(optional)</span>
              </label>
              <textarea
                id="npb-desc"
                className="np-input npb-desc"
                rows={2}
                placeholder="What is it for? One line helps reviewers make the right call."
                value={d.description}
                maxLength={240}
                onChange={(e) => d.setDescription(e.target.value)}
              />
            </>
          ) : null}

          {key === 'data' ? (
            <>
              <h1 ref={heading} tabIndex={-1} className="npb-q">
                What are you labelling?
              </h1>
              <div className="npb-types" role="group" aria-label="Data type">
                {modalities.map(({ key: k, title, line }) => {
                  const Icon = icons[k];
                  return (
                    <button key={k} type="button" className="npb-type" aria-pressed={d.modality === k} onClick={() => d.setModality(k)}>
                      <TypeArt k={k} />
                      <span className="npb-type-t">
                        <Icon size={16} aria-hidden /> <b>{title}</b>
                      </span>
                      <small>{line}</small>
                    </button>
                  );
                })}
              </div>
              <h2 className="npb-sub">And what should be marked on {d.modality === 'text' ? 'them' : 'it'}?</h2>
              <div className="pills" role="group" aria-label="Task">
                {tasks[d.modality].map((t) => (
                  <button key={t} type="button" className="pill-btn" aria-pressed={d.task === t} onClick={() => d.setTask(t)}>
                    {t}
                  </button>
                ))}
              </div>
            </>
          ) : null}

          {key === 'files' ? (
            <>
              <h1 ref={heading} tabIndex={-1} className="npb-q">
                Add the {unit}.
              </h1>
              <p className="npb-hint">They upload when the project is created. You can also add them later from the project.</p>
              <DropZone draft={d} className="npb-drop" />
              <FileSummary draft={d} />
              <FileList draft={d} layout={d.modality === 'image' ? 'grid' : 'rows'} />
              <AddedNote draft={d} />
            </>
          ) : null}

          {key === 'classes' ? (
            <>
              <h1 ref={heading} tabIndex={-1} className="npb-q">
                Which labels can people choose?
              </h1>
              <p className="npb-hint">Pick a colour that stands out on your {unit}. It’s how each class appears to annotators.</p>
              <ClassEditor draft={d} density="roomy" invalid={error ?? undefined} />
            </>
          ) : null}

          {key === 'check' ? (
            <>
              <h1 ref={heading} tabIndex={-1} className="npb-q">
                How closely should people check?
              </h1>
              <Rules draft={d} />
              <dl className="npb-review">
                <div>
                  <dt>Name</dt>
                  <dd>
                    {d.name.trim() || <span className="np-err">Missing</span>}
                    {d.description.trim() ? <small>{d.description.trim()}</small> : null}
                  </dd>
                  <button type="button" className="np-link" onClick={() => go(0)}>
                    Edit
                  </button>
                </div>
                <div>
                  <dt>Data</dt>
                  <dd>{answer('data', d)}</dd>
                  <button type="button" className="np-link" onClick={() => go(1)}>
                    Edit
                  </button>
                </div>
                <div>
                  <dt>Files</dt>
                  <dd>{answer('files', d) ?? <span className="muted">None yet: add them from the project later</span>}</dd>
                  <button type="button" className="np-link" onClick={() => go(2)}>
                    Edit
                  </button>
                </div>
                <div>
                  <dt>Classes</dt>
                  <dd className="npb-review-classes">
                    {d.classes.length ? d.classes.map((c, i) => <ClassChip key={c.id} c={c} k={i} />) : <span className="np-err">Missing</span>}
                  </dd>
                  <button type="button" className="np-link" onClick={() => go(3)}>
                    Edit
                  </button>
                </div>
              </dl>
              {created ? <CreatedNote draft={d} onClose={() => setCreated(false)} /> : null}
            </>
          ) : null}

          <div className="npb-bar">
            {step > 0 ? (
              <button type="button" className="btn btn-ghost" onClick={() => go(step - 1)}>
                <ArrowLeft size={15} aria-hidden /> Back
              </button>
            ) : (
              <span />
            )}
            <span className="npb-bar-step mono">
              {step + 1} / {STEPS.length}
            </span>
            <button type="submit" className={`btn ${key === 'check' ? 'btn-accent' : 'btn-primary'}`}>
              {continueLabel} {key === 'check' ? null : <ArrowRight size={15} aria-hidden />}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
