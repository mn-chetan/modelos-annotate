/*
 * One draft, three presentations. Every direction drives the same state so the
 * comparison is about layout and flow, not behaviour.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  classNameProblem,
  classesFrom,
  extOf,
  fileProblem,
  inferModality,
  newId,
  nextColour,
  suggestedClasses,
  tasks,
  type LabelClass,
  type Modality,
  type StagedFile,
} from './model';

const PREVIEWABLE = ['.avif', '.bmp', '.jpeg', '.jpg', '.png', '.webp'];

/* ---------- Reading dropped folders ---------- */

function readAll(dir: FileSystemDirectoryEntry): Promise<FileSystemEntry[]> {
  const reader = dir.createReader();
  const out: FileSystemEntry[] = [];
  return new Promise((resolve, reject) => {
    const next = () =>
      reader.readEntries((batch) => {
        if (batch.length === 0) resolve(out);
        else {
          out.push(...batch);
          next();
        }
      }, reject);
    next();
  });
}

async function walk(entry: FileSystemEntry): Promise<{ file: File; path: string }[]> {
  if (entry.name.startsWith('.')) return [];
  if (entry.isFile) {
    const file = await new Promise<File>((res, rej) => (entry as FileSystemFileEntry).file(res, rej));
    return [{ file, path: entry.fullPath.replace(/^\//, '') }];
  }
  const children = await readAll(entry as FileSystemDirectoryEntry);
  return (await Promise.all(children.map(walk))).flat();
}

/** Files from a drop, descending into folders where the browser allows it. */
export async function filesFromDrop(dt: DataTransfer): Promise<{ file: File; path: string }[]> {
  const entries = Array.from(dt.items)
    .filter((i) => i.kind === 'file')
    .map((i) => i.webkitGetAsEntry?.())
    .filter((e): e is FileSystemEntry => !!e);
  if (entries.length) return (await Promise.all(entries.map(walk))).flat();
  return Array.from(dt.files).map((file) => ({ file, path: file.name }));
}

export function filesFromInput(list: FileList | null): { file: File; path: string }[] {
  return Array.from(list ?? [])
    .filter((f) => !f.name.startsWith('.'))
    .map((file) => ({ file, path: file.webkitRelativePath || file.name }));
}

/* ---------- The draft ---------- */

export type Problems = { name?: string; classes?: string };

export function useDraft() {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [modality, setModalityState] = useState<Modality>('image');
  const [modalityChosen, setModalityChosen] = useState(false);
  const [task, setTaskState] = useState(tasks.image[0]);
  const [classes, setClasses] = useState<LabelClass[]>(() => classesFrom(suggestedClasses[tasks.image[0]]));
  const [classesEdited, setClassesEdited] = useState(false);
  const [removed, setRemoved] = useState<{ cls: LabelClass; index: number } | null>(null);
  const [files, setFiles] = useState<StagedFile[]>([]);
  const [lastAdd, setLastAdd] = useState<{ added: number; skipped: number } | null>(null);
  const [threshold, setThreshold] = useState(0.7);
  const [sample, setSample] = useState(10);
  const [showProblems, setShowProblems] = useState(false);

  /* Tasks and suggested classes. Edited classes are never overwritten silently. */
  const applyTask = useCallback(
    (t: string) => {
      setTaskState(t);
      if (!classesEdited) setClasses(classesFrom(suggestedClasses[t] ?? []));
    },
    [classesEdited],
  );
  const setTask = applyTask;
  const setModality = useCallback(
    (m: Modality) => {
      setModalityState(m);
      setModalityChosen(true);
      if (!tasks[m].includes(task)) applyTask(tasks[m][0]);
    },
    [task, applyTask],
  );
  const useSuggested = () => {
    setClasses(classesFrom(suggestedClasses[task] ?? []));
    setClassesEdited(false);
    setRemoved(null);
  };
  const suggestion = suggestedClasses[task] ?? [];
  const matchesSuggestion =
    suggestion.length === classes.length && suggestion.every((s, i) => classes[i]?.name === s);

  /* Classes */
  const addClass = (raw: string, colour?: string): string | null => {
    const problem = classNameProblem(raw, classes);
    if (problem) return problem;
    setClasses((cs) => [...cs, { id: newId('c'), name: raw.trim(), colour: colour ?? nextColour(cs) }]);
    setClassesEdited(true);
    setRemoved(null);
    return null;
  };
  const renameClass = (id: string, raw: string): string | null => {
    const problem = classNameProblem(raw, classes, id);
    if (problem) return problem;
    setClasses((cs) => cs.map((c) => (c.id === id ? { ...c, name: raw.trim() } : c)));
    setClassesEdited(true);
    return null;
  };
  const recolourClass = (id: string, colour: string) => {
    setClasses((cs) => cs.map((c) => (c.id === id ? { ...c, colour } : c)));
    setClassesEdited(true);
  };
  const removeClass = (id: string) => {
    const index = classes.findIndex((c) => c.id === id);
    if (index < 0) return;
    setRemoved({ cls: classes[index], index });
    setClasses((cs) => cs.filter((c) => c.id !== id));
    setClassesEdited(true);
  };
  const undoRemove = () => {
    if (!removed) return;
    setClasses((cs) => {
      const next = [...cs];
      next.splice(Math.min(removed.index, next.length), 0, removed.cls);
      return next;
    });
    setRemoved(null);
  };
  const nextClassColour = nextColour(classes);

  /* Files */
  const thumbs = useRef(new Set<string>());
  const addFiles = (incoming: { file: File; path: string }[]) => {
    if (!incoming.length) return;
    const have = new Set(files.map((f) => `${f.path}|${f.file.size}|${f.file.lastModified}`));
    const fresh: StagedFile[] = [];
    let skipped = 0;
    for (const { file, path } of incoming) {
      const key = `${path}|${file.size}|${file.lastModified}`;
      if (have.has(key)) {
        skipped++;
        continue;
      }
      have.add(key);
      let thumb: string | undefined;
      if (PREVIEWABLE.includes(extOf(file.name)) && file.size > 0) {
        thumb = URL.createObjectURL(file);
        thumbs.current.add(thumb);
      }
      fresh.push({ id: newId('f'), file, path, thumb });
    }
    setFiles((fs) => [...fs, ...fresh]);
    setLastAdd({ added: fresh.length, skipped });
    // The first drop decides the data type unless someone already picked one.
    if (!modalityChosen && !files.length) {
      const guess = inferModality(fresh.map((f) => f.file));
      if (guess && guess !== modality) {
        setModalityState(guess);
        if (!tasks[guess].includes(task)) applyTask(tasks[guess][0]);
      }
    }
  };
  const release = (f: StagedFile) => {
    if (f.thumb) {
      URL.revokeObjectURL(f.thumb);
      thumbs.current.delete(f.thumb);
    }
  };
  const removeFile = (id: string) => {
    const f = files.find((x) => x.id === id);
    if (f) release(f);
    setFiles((fs) => fs.filter((x) => x.id !== id));
    setLastAdd(null);
  };
  const removeUnsupported = () => {
    const bad = files.filter((f) => fileProblem(f.file, modality));
    bad.forEach(release);
    setFiles((fs) => fs.filter((f) => !fileProblem(f.file, modality)));
    setLastAdd(null);
  };
  const clearFiles = () => {
    files.forEach(release);
    setFiles([]);
    setLastAdd(null);
  };
  useEffect(() => {
    const set = thumbs.current;
    return () => set.forEach((u) => URL.revokeObjectURL(u));
  }, []);

  const fileStats = useMemo(() => {
    let ok = 0;
    let bad = 0;
    let bytes = 0;
    for (const f of files) {
      if (fileProblem(f.file, modality)) bad++;
      else {
        ok++;
        bytes += f.file.size;
      }
    }
    return { ok, bad, bytes };
  }, [files, modality]);

  /* Readiness */
  const problems: Problems = {};
  if (!name.trim()) problems.name = 'Give the project a name.';
  if (classes.length === 0) problems.classes = 'Add at least one class.';
  const ready = !problems.name && !problems.classes;

  return {
    name,
    setName,
    description,
    setDescription,
    modality,
    setModality,
    task,
    setTask,
    classes,
    addClass,
    renameClass,
    recolourClass,
    removeClass,
    removed,
    undoRemove,
    dismissRemoved: () => setRemoved(null),
    nextClassColour,
    suggestion,
    matchesSuggestion,
    useSuggested,
    files,
    addFiles,
    removeFile,
    removeUnsupported,
    clearFiles,
    lastAdd,
    fileStats,
    threshold,
    setThreshold,
    sample,
    setSample,
    problems,
    ready,
    showProblems,
    setShowProblems,
  };
}

export type Draft = ReturnType<typeof useDraft>;
