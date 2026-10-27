/*
 * C · Workbench. Start from the data; set up beside a live preview of what annotators
 * will see. Classes, colours and gaps show up on real work as they change. Axis: the
 * consequence is visible while deciding, rather than summarised after.
 */
import { useRef, useState } from 'react';
import { FileText, Film, Image as ImageIcon, Upload } from 'lucide-react';
import { modalities, tasks } from './model';
import { AddedNote, ClassEditor, CreatedNote, FileList, FilePickers, FileSummary, Rules, acceptLine, useDropTarget } from './parts';
import { Preview } from './Preview';
import { useDraft } from './useDraft';

const icons = { image: ImageIcon, text: FileText, video: Film } as const;
// Touch screens can't drag files in, so they get the pickers without the drop promise.
const touch = typeof matchMedia !== 'undefined' && matchMedia('(pointer: coarse)').matches;

export default function WorkbenchVariant() {
  const d = useDraft();
  const [hover, setHover] = useState<string | null>(null);
  const [created, setCreated] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);
  const classesRef = useRef<HTMLDivElement>(null);
  const drop = useDropTarget(d.addFiles);
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

  const status = !d.name.trim()
    ? 'Name the project to create it'
    : !d.classes.length
      ? 'Add at least one class'
      : d.fileStats.ok
        ? `${d.fileStats.ok.toLocaleString('en-GB')} ${unit} will upload`
        : 'Files can be added later';

  return (
    <div className={`page page-wide npc${drop.over ? ' is-over' : ''}`} {...drop.props}>
      <header className="npc-head">
        <div className="npc-name-wrap">
          <p className="page-eyebrow">Workspace · New project</p>
          <label className="np-sr" htmlFor="npc-name">
            Project name
          </label>
          <input
            id="npc-name"
            ref={nameRef}
            className={`npc-name${d.showProblems && d.problems.name ? ' is-invalid' : ''}`}
            placeholder="Name this project"
            value={d.name}
            maxLength={80}
            aria-invalid={d.showProblems && !!d.problems.name}
            aria-describedby="npc-status"
            onChange={(e) => d.setName(e.target.value)}
          />
          <label className="np-sr" htmlFor="npc-desc">
            Purpose
          </label>
          <input
            id="npc-desc"
            className="npc-desc"
            placeholder="Add a one-line purpose (optional)"
            value={d.description}
            maxLength={240}
            onChange={(e) => d.setDescription(e.target.value)}
          />
        </div>
        <div className="npc-act">
          <p id="npc-status" className={`npc-status${d.showProblems && !d.ready ? ' is-bad' : ''}`}>
            {status}
          </p>
          <button type="button" className="btn btn-accent" onClick={create}>
            Create project
          </button>
        </div>
      </header>
      {created ? <CreatedNote draft={d} onClose={() => setCreated(false)} /> : null}

      <div className="npc-bench">
        <div className="npc-setup">
          <section className="npc-sec" aria-labelledby="npc-s1">
            <h2 id="npc-s1" className="npc-h">
              Data
            </h2>
            <div className={`npc-drop${d.files.length ? ' has-files' : ''}`}>
              <Upload size={18} aria-hidden />
              <div>
                <p className="npc-drop-t">{touch
                    ? d.files.length
                      ? 'Add more files'
                      : `Add the ${unit} to label`
                    : d.files.length
                      ? 'Drop more anywhere on this page'
                      : 'Drop files or a folder anywhere on this page'}</p>
                <p className="np-drop-sub">{acceptLine(d)}</p>
              </div>
              <FilePickers draft={d} primary={!d.files.length} />
            </div>
            <FileSummary draft={d} />
            <div className="npc-files">
              <FileList draft={d} />
            </div>
            <AddedNote draft={d} />

            <div className="npc-row">
              <span className="npc-k" id="npc-type">
                Type
              </span>
              <div className="seg" role="group" aria-labelledby="npc-type">
                {modalities.map(({ key, title }) => {
                  const Icon = icons[key];
                  return (
                    <button key={key} type="button" aria-pressed={d.modality === key} onClick={() => d.setModality(key)}>
                      <Icon size={14} aria-hidden /> {title}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="npc-row">
              <span className="npc-k" id="npc-task">
                Task
              </span>
              <div className="pills" role="group" aria-labelledby="npc-task">
                {tasks[d.modality].map((t) => (
                  <button key={t} type="button" className="pill-btn" aria-pressed={d.task === t} onClick={() => d.setTask(t)}>
                    {t}
                  </button>
                ))}
              </div>
            </div>
          </section>

          <section className="npc-sec" aria-labelledby="npc-s2" ref={classesRef}>
            <h2 id="npc-s2" className="npc-h">
              Classes <span className="muted">{d.classes.length}</span>
            </h2>
            <ClassEditor draft={d} density="compact" onHover={setHover} invalid={d.showProblems ? d.problems.classes : undefined} />
          </section>

          <section className="npc-sec" aria-labelledby="npc-s3">
            <h2 id="npc-s3" className="npc-h">
              Review rules
            </h2>
            <Rules draft={d} />
          </section>
        </div>

        <section className="npc-stage" aria-label="Preview of what annotators will see">
          <p className="npc-stage-k">What annotators will see</p>
          <Preview draft={d} hover={hover} />
        </section>
      </div>

      <div className="npc-mbar">
        <span className={d.showProblems && !d.ready ? 'is-bad' : ''}>{status}</span>
        <button type="button" className="btn btn-accent btn-sm" onClick={create}>
          Create project
        </button>
      </div>

      {drop.over ? (
        <div className="npc-overlay" aria-hidden>
          <p>
            <Upload size={22} /> Drop to add to this project
          </p>
        </div>
      ) : null}
    </div>
  );
}
