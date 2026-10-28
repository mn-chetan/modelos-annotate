/*
 * New project controls: the colour picker, the class editor, the drop target, the staged
 * file list and the review rules.
 */
import { useEffect, useId, useLayoutEffect, useRef, useState, type DragEvent } from 'react';
import { AlertCircle, FileText, Film, FolderUp, Image as ImageIcon, Pencil, Plus, Upload, X } from 'lucide-react';
import { accepts, colourName, fileProblem, formatBytes, inkOn, palette, type LabelClass, type StagedFile } from './model';
import { filesFromDrop, filesFromInput, type Draft } from './useDraft';

/* ---------- Colour picker ---------- */

export function ColourPicker({
  value,
  onChange,
  label,
  usedBy,
}: {
  value: string;
  onChange: (hex: string) => void;
  /** What is being coloured, for the accessible name: "car". */
  label: string;
  /** Other classes on each colour, so a shared colour is a visible choice. */
  usedBy?: (hex: string) => string[];
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const id = useId();

  // Anchored to its swatch: follows it while the page scrolls, closes once it leaves view.
  const place = () => {
    if (!btn.current) return false;
    const r = btn.current.getBoundingClientRect();
    if (r.bottom < 0 || r.top > window.innerHeight) return false;
    const w = 248;
    const h = pop.current?.offsetHeight ?? 230;
    const left = Math.max(12, Math.min(r.left, window.innerWidth - w - 12));
    const below = r.bottom + 8;
    const top = below + h > window.innerHeight - 12 ? Math.max(12, r.top - h - 8) : below;
    setPos({ top, left });
    return true;
  };

  useLayoutEffect(() => {
    if (open) place();
    else setPos(null);
  }, [open]);

  // Focus the chosen colour once, when the picker first appears.
  const focused = useRef(false);
  useEffect(() => {
    if (!open) {
      focused.current = false;
      return;
    }
    if (!pos || focused.current || !pop.current) return;
    focused.current = true;
    const chosen = pop.current.querySelector<HTMLButtonElement>('[aria-pressed="true"]') ?? pop.current.querySelector<HTMLElement>('button, input');
    chosen?.focus({ preventScroll: true });
  }, [open, pos]);

  useEffect(() => {
    if (!open) return;
    const close = (refocus: boolean) => {
      setOpen(false);
      if (refocus) btn.current?.focus();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      e.stopPropagation();
      close(true);
    };
    const onDown = (e: PointerEvent) => {
      if (!pop.current?.contains(e.target as Node) && !btn.current?.contains(e.target as Node)) close(false);
    };
    const follow = () => {
      if (!place()) close(false);
    };
    document.addEventListener('keydown', onKey, true);
    document.addEventListener('pointerdown', onDown);
    window.addEventListener('scroll', follow, true);
    window.addEventListener('resize', follow);
    return () => {
      document.removeEventListener('keydown', onKey, true);
      document.removeEventListener('pointerdown', onDown);
      window.removeEventListener('scroll', follow, true);
      window.removeEventListener('resize', follow);
    };
  }, [open]);

  const pick = (hex: string, close = true) => {
    onChange(hex);
    if (close) {
      setOpen(false);
      btn.current?.focus();
    }
  };
  const custom = !palette.some((p) => p.hex.toLowerCase() === value.toLowerCase());

  return (
    <>
      <button
        ref={btn}
        type="button"
        className="np-swatch"
        style={{ background: value }}
        aria-label={`Colour for ${label}: ${colourName(value)}. Change colour`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen((o) => !o)}
      />
      {open && pos ? (
        <div ref={pop} id={id} className="np-pop" role="dialog" aria-label={`Colour for ${label}`} style={pos}>
          <div className="np-pop-grid">
            {palette.map((p) => {
              const others = usedBy?.(p.hex) ?? [];
              return (
                <button
                  key={p.hex}
                  type="button"
                  className="np-pop-sw"
                  style={{ background: p.hex, color: inkOn(p.hex) }}
                  aria-pressed={p.hex.toLowerCase() === value.toLowerCase()}
                  aria-label={`${p.name}${others.length ? `, also used by ${others.join(', ')}` : ''}`}
                  title={others.length ? `${p.name} · also ${others.join(', ')}` : p.name}
                  onClick={() => pick(p.hex)}
                >
                  {others.length ? <span className="np-pop-dot" aria-hidden /> : null}
                </button>
              );
            })}
          </div>
          <label className="np-pop-custom">
            <span className="np-pop-custom-sw" style={{ background: custom ? value : undefined }} aria-hidden />
            <span>
              Custom colour
              <small className="mono">{value.toUpperCase()}</small>
            </span>
            <input type="color" value={value.toLowerCase()} onChange={(e) => pick(e.target.value.toUpperCase(), false)} />
          </label>
          <p className="np-pop-note">A dot marks a colour another class already uses.</p>
        </div>
      ) : null}
    </>
  );
}

/* ---------- Class chip (how a class reads on the work) ---------- */

export function ClassChip({ c, k }: { c: Pick<LabelClass, 'name' | 'colour'>; k?: number }) {
  return (
    <span className="np-chip" style={{ ['--c' as string]: c.colour }}>
      <i aria-hidden />
      {c.name}
      {k !== undefined && k < 9 ? <kbd>{k + 1}</kbd> : null}
    </span>
  );
}

/* ---------- Class editor ---------- */

function ClassRow({
  c,
  index,
  draft,
}: {
  c: LabelClass;
  index: number;
  draft: Draft;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(c.name);
  const [err, setErr] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const editBtn = useRef<HTMLButtonElement>(null);
  const settled = useRef(false);
  const errId = useId();

  useEffect(() => {
    if (editing) {
      settled.current = false;
      input.current?.select();
    }
  }, [editing]);

  const commit = () => {
    if (settled.current) return;
    if (text.trim() === c.name) return cancel();
    const problem = draft.renameClass(c.id, text);
    if (problem) return setErr(problem);
    settled.current = true;
    setEditing(false);
    setErr(null);
    requestAnimationFrame(() => editBtn.current?.focus());
  };
  const cancel = () => {
    settled.current = true;
    setText(c.name);
    setErr(null);
    setEditing(false);
    requestAnimationFrame(() => editBtn.current?.focus());
  };
  const usedBy = (hex: string) =>
    draft.classes.filter((o) => o.id !== c.id && o.colour.toLowerCase() === hex.toLowerCase()).map((o) => o.name);

  return (
    <li className="np-class">
      <ColourPicker value={c.colour} label={c.name} usedBy={usedBy} onChange={(hex) => draft.recolourClass(c.id, hex)} />
      {editing ? (
        <span className="np-class-edit">
          <input
            ref={input}
            className={`np-input np-input-sm${err ? ' is-invalid' : ''}`}
            value={text}
            aria-label={`Rename ${c.name}`}
            aria-invalid={!!err}
            aria-describedby={err ? errId : undefined}
            maxLength={60}
            onChange={(e) => {
              setText(e.target.value);
              setErr(null);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                commit();
              }
              if (e.key === 'Escape') {
                e.stopPropagation();
                cancel();
              }
            }}
            onBlur={commit}
          />
          {err ? (
            <span id={errId} className="np-err" role="alert">
              {err}
            </span>
          ) : null}
        </span>
      ) : (
        <button
          ref={editBtn}
          type="button"
          className="np-class-name"
          aria-label={`${c.name}. Rename`}
          onClick={() => {
            setText(c.name);
            setEditing(true);
          }}
        >
          <span>{c.name}</span>
          <Pencil size={12} aria-hidden />
        </button>
      )}
      <span className="np-class-key mono" title="Keyboard shortcut while labelling">
        {index < 9 ? index + 1 : ''}
      </span>
      <button type="button" className="np-x" aria-label={`Remove ${c.name}`} onClick={() => draft.removeClass(c.id)}>
        <X size={14} />
      </button>
    </li>
  );
}

export function ClassEditor({ draft, invalid }: { draft: Draft; invalid?: string }) {
  const [text, setText] = useState('');
  const [colour, setColour] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [announce, setAnnounce] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const errId = useId();
  const nextColour = colour ?? draft.nextClassColour;

  const add = () => {
    const problem = draft.addClass(text, nextColour);
    if (problem) {
      setErr(problem);
      input.current?.focus();
      return;
    }
    setAnnounce(`Added ${text.trim()}`);
    setText('');
    setColour(null);
    setErr(null);
    input.current?.focus();
  };

  // Hide the undo offer after a while; it is a convenience, not a modal question.
  useEffect(() => {
    if (!draft.removed) return;
    const t = setTimeout(draft.dismissRemoved, 8000);
    return () => clearTimeout(t);
  }, [draft.removed, draft.dismissRemoved]);

  const shownError = err ?? invalid;

  return (
    <div className="np-classes">
      {draft.classes.length ? (
        <ul className="np-class-list" aria-label="Classes">
          {draft.classes.map((c, i) => (
            <ClassRow key={c.id} c={c} index={i} draft={draft} />
          ))}
        </ul>
      ) : (
        <p className="np-empty-line">No classes yet. Add the labels people and the model will choose from.</p>
      )}

      <div className="np-class-add">
        <ColourPicker
          value={nextColour}
          label="the new class"
          usedBy={(hex) => draft.classes.filter((o) => o.colour.toLowerCase() === hex.toLowerCase()).map((o) => o.name)}
          onChange={setColour}
        />
        <input
          ref={input}
          className={`np-input${shownError ? ' is-invalid' : ''}`}
          value={text}
          placeholder="Add a class, e.g. traffic light"
          aria-label="New class name"
          aria-invalid={!!shownError}
          aria-describedby={shownError ? errId : undefined}
          maxLength={60}
          onChange={(e) => {
            setText(e.target.value);
            setErr(null);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              add();
            }
          }}
        />
        <button type="button" className="btn btn-ghost btn-sm" onClick={add}>
          <Plus size={15} aria-hidden /> Add
        </button>
      </div>
      {shownError ? (
        <p id={errId} className="np-err">
          <AlertCircle size={13} aria-hidden /> {shownError}
        </p>
      ) : null}

      <div className="np-class-foot">
        {draft.removed ? (
          <span className="np-undo" role="status">
            Removed <b>{draft.removed.cls.name}</b>
            <button type="button" className="np-link" onClick={draft.undoRemove}>
              Undo
            </button>
          </span>
        ) : !draft.matchesSuggestion && draft.suggestion.length ? (
          <span className="muted">
            Suggested for {draft.task.toLowerCase()}: {draft.suggestion.join(', ')}.{' '}
            <button type="button" className="np-link" onClick={draft.useSuggested}>
              Use these instead
            </button>
          </span>
        ) : (
          <span className="muted">Numbers are the keyboard shortcuts annotators use. Click a name to rename it.</span>
        )}
      </div>
      <span className="np-sr" aria-live="polite">
        {announce}
      </span>
    </div>
  );
}

/* ---------- Files: drop target, pickers, list ---------- */

function useDropTarget(onFiles: (f: { file: File; path: string }[]) => void) {
  const [over, setOver] = useState(false);
  const depth = useRef(0);
  const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer.types).includes('Files');
  return {
    over,
    props: {
      onDragEnter: (e: DragEvent) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        depth.current++;
        setOver(true);
      },
      onDragOver: (e: DragEvent) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
      },
      onDragLeave: () => {
        depth.current = Math.max(0, depth.current - 1);
        if (depth.current === 0) setOver(false);
      },
      onDrop: async (e: DragEvent) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        depth.current = 0;
        setOver(false);
        onFiles(await filesFromDrop(e.dataTransfer));
      },
    },
  };
}

function FilePickers({ draft }: { draft: Draft }) {
  const filesIn = useRef<HTMLInputElement>(null);
  const folderIn = useRef<HTMLInputElement>(null);
  useEffect(() => {
    folderIn.current?.setAttribute('webkitdirectory', '');
  }, []);
  const take = (el: HTMLInputElement) => {
    draft.addFiles(filesFromInput(el.files));
    el.value = '';
  };
  return (
    <span className="np-pickers">
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => filesIn.current?.click()}>
        <Upload size={15} aria-hidden /> Choose files
      </button>
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => folderIn.current?.click()}>
        <FolderUp size={15} aria-hidden /> Choose a folder
      </button>
      <input ref={filesIn} type="file" multiple hidden accept={accepts[draft.modality].join(',')} onChange={(e) => take(e.currentTarget)} />
      <input ref={folderIn} type="file" multiple hidden onChange={(e) => take(e.currentTarget)} />
    </span>
  );
}

function acceptLine(draft: Draft) {
  return `${accepts[draft.modality].map((e) => e.slice(1).toUpperCase()).join(', ')} · up to 24 MB each`;
}

export function DropZone({ draft }: { draft: Draft }) {
  const { over, props } = useDropTarget(draft.addFiles);
  return (
    <div className={`np-drop${over ? ' is-over' : ''}`} {...props}>
      <Upload size={20} aria-hidden className="np-drop-icon" />
      <p className="np-drop-title">Drop {draft.modality === 'image' ? 'images' : draft.modality === 'text' ? 'documents' : 'clips'} or a folder here</p>
      <p className="np-drop-sub">{acceptLine(draft)}</p>
      <FilePickers draft={draft} />
    </div>
  );
}

const kindIcon = { image: ImageIcon, text: FileText, video: Film } as const;

export function FileSummary({ draft }: { draft: Draft }) {
  const { ok, bad, bytes } = draft.fileStats;
  if (!draft.files.length) return null;
  return (
    <div className="np-files-head">
      <p>
        <b>{ok.toLocaleString('en-GB')}</b> {ok === 1 ? 'file' : 'files'} ready · {formatBytes(bytes)}
        {bad ? (
          <span className="np-files-bad">
            {' '}
            · {bad} won’t upload
            <button type="button" className="np-link" onClick={draft.removeUnsupported}>
              Remove {bad === 1 ? 'it' : 'them'}
            </button>
          </span>
        ) : null}
      </p>
      <button type="button" className="np-link" onClick={draft.clearFiles}>
        Clear all
      </button>
    </div>
  );
}

const PAGE = 48;

export function FileList({ draft }: { draft: Draft }) {
  const [limit, setLimit] = useState(PAGE);
  if (!draft.files.length) return null;
  // Problems first, so nothing that won't upload hides below the fold.
  const sorted = [...draft.files].sort(
    (a, b) => Number(!!fileProblem(b.file, draft.modality)) - Number(!!fileProblem(a.file, draft.modality)),
  );
  const shown = sorted.slice(0, limit);
  const Icon = kindIcon[draft.modality];
  return (
    <div className="np-files">
      <ul className="np-file-rows" aria-label="Files to upload">
        {shown.map((f) => (
          <FileItem key={f.id} f={f} draft={draft} Icon={Icon} />
        ))}
      </ul>
      {sorted.length > limit ? (
        <button type="button" className="np-link np-more" onClick={() => setLimit((l) => l + PAGE * 4)}>
          Show {Math.min(PAGE * 4, sorted.length - limit)} more of {sorted.length - limit}
        </button>
      ) : null}
    </div>
  );
}

function FileItem({ f, draft, Icon }: { f: StagedFile; draft: Draft; Icon: typeof ImageIcon }) {
  const problem = fileProblem(f.file, draft.modality);
  const [broken, setBroken] = useState(false);
  const thumb = f.thumb && !problem && !broken ? <img src={f.thumb} alt="" loading="lazy" onError={() => setBroken(true)} /> : null;
  return (
    <li className={`np-file${problem ? ' is-bad' : ''}`}>
      <span className="np-file-ic">{thumb ?? <Icon size={16} aria-hidden />}</span>
      <span className="np-file-name" title={f.path}>
        {f.path}
      </span>
      {problem ? <span className="np-file-why">{problem}</span> : <span className="np-file-size mono">{formatBytes(f.file.size)}</span>}
      <button type="button" className="np-x" aria-label={`Remove ${f.path}`} onClick={() => draft.removeFile(f.id)}>
        <X size={14} />
      </button>
    </li>
  );
}

export function AddedNote({ draft }: { draft: Draft }) {
  const a = draft.lastAdd;
  return (
    <p className="np-sr" aria-live="polite">
      {a ? `Added ${a.added} ${a.added === 1 ? 'file' : 'files'}${a.skipped ? `; ${a.skipped} already added` : ''}.` : ''}
    </p>
  );
}

/* ---------- Range rules ---------- */

export function Rules({ draft }: { draft: Draft }) {
  return (
    <div className="np-rules">
      <div className="np-rule">
        <label htmlFor="np-thr">
          Send to review below
          <small>The AI approves an item when every label is at or above this; anything less goes to a person first.</small>
        </label>
        <span className="np-rule-ctl">
          <input id="np-thr" type="range" min={0.5} max={0.95} step={0.05} value={draft.threshold} onChange={(e) => draft.setThreshold(Number(e.target.value))} />
          <output htmlFor="np-thr" className="mono">
            {draft.threshold.toFixed(2)}
          </output>
        </span>
      </div>
      <div className="np-rule">
        <label htmlFor="np-smp">
          Quality check sample
          <small>Share of reviewed work audited before export. Saved with the project; the quality check isn’t connected to live projects yet.</small>
        </label>
        <span className="np-rule-ctl">
          <input id="np-smp" type="range" min={5} max={50} step={5} value={draft.sample} onChange={(e) => draft.setSample(Number(e.target.value))} />
          <output htmlFor="np-smp" className="mono">
            {draft.sample}%
          </output>
        </span>
      </div>
    </div>
  );
}
