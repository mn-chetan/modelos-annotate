/*
 * One item's labels while a person reviews them: the working copy, what was last saved,
 * undo and redo, and the two writes (save the labels, then approve or reject the item).
 * Saving never approves; approving saves first when there are unsaved edits.
 */
import { useEffect, useRef, useState } from 'react';
import { getAnnotations, refreshAssets, refreshProjects, request, type Annotation, type LiveAsset, type LiveProject } from '../../store';
import { setNavigationGuard } from '../../router';

const copy = (rows: Annotation[]) => rows.map((a) => ({ ...a, provenance: { ...a.provenance }, geometry: a.geometry ? { ...a.geometry } : a.geometry }));
const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

export const DECIDED = new Set(['approved', 'edited', 'rejected']);

export function useEdits(project: LiveProject, asset: LiveAsset | undefined) {
  const [rows, setRows] = useState<Annotation[]>([]);
  const [saved, setSaved] = useState('[]');
  const [past, setPast] = useState<Annotation[][]>([]);
  const [future, setFuture] = useState<Annotation[][]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState<'save' | 'approve' | 'reject' | null>(null);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const dirty = JSON.stringify(rows) !== saved;
  /** Each label's class as last saved, so a relabel shows what it was before it is saved. */
  const savedLabels = new Map((JSON.parse(saved) as Annotation[]).map((a) => [a.id, a.label]));
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setLoadError('');
    setError('');
    setNote('');
    setRows([]);
    setSaved('[]');
    setPast([]);
    setFuture([]);
    if (!asset) {
      setLoading(false);
      return;
    }
    getAnnotations(asset.id)
      .then((a) => {
        if (!alive) return;
        setRows(a);
        setSaved(JSON.stringify(a));
        setLoading(false);
      })
      .catch((e) => {
        if (!alive) return;
        setLoadError(message(e));
        setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [asset?.id, attempt]);

  // Leaving with unsaved edits asks first, inside the app and when closing the tab.
  useEffect(() => {
    setNavigationGuard(() => !dirtyRef.current || window.confirm('Discard your unsaved label edits?'));
    const before = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', before);
    return () => {
      setNavigationGuard(null);
      window.removeEventListener('beforeunload', before);
    };
  }, []);

  /** Record a change as one undo step. */
  function change(next: Annotation[]) {
    setPast((h) => [...h, copy(rows)]);
    setFuture([]);
    setRows(next);
    setNote('');
  }

  function update(id: string, patch: Partial<Annotation>) {
    change(rows.map((a) => (a.id === id ? { ...a, ...patch } : a)));
  }

  /** Start a drag: one undo step for the whole gesture; `live` then updates without new steps. */
  function begin() {
    setPast((h) => [...h, copy(rows)]);
    setFuture([]);
  }

  function live(fn: (rows: Annotation[]) => Annotation[]) {
    setRows(fn);
  }

  function undo() {
    if (!past.length || busy) return;
    setFuture((h) => [copy(rows), ...h]);
    setRows(past[past.length - 1]);
    setPast((h) => h.slice(0, -1));
  }

  function redo() {
    if (!future.length || busy) return;
    setPast((h) => [...h, copy(rows)]);
    setRows(future[0]);
    setFuture((h) => h.slice(1));
  }

  async function persist(next: Annotation[]) {
    await request(`/assets/${asset!.id}/annotations/batch`, { method: 'PUT', body: JSON.stringify({ annotations: copy(next) }) });
    const fresh = await getAnnotations(asset!.id);
    setRows(fresh);
    setSaved(JSON.stringify(fresh));
    setPast([]);
    setFuture([]);
  }

  async function save() {
    if (!asset || busy) return false;
    setBusy('save');
    setError('');
    try {
      await persist(rows);
      await refreshAssets(project.id);
      setNote('Saved. The item stays in review until you approve it.');
      return true;
    } catch (e) {
      setError(`Save failed; your edits are still here. ${message(e)}`);
      return false;
    } finally {
      setBusy(null);
    }
  }

  /**
   * Approve or reject the item. Approving accepts any label still undecided (the button says
   * so first) and saves before the decision, so one action finishes the item.
   */
  async function decide(action: 'approve' | 'reject') {
    if (!asset || busy) return false;
    setBusy(action);
    setError('');
    try {
      const next = action === 'approve' ? rows.map((a) => (DECIDED.has(a.review_status ?? '') ? a : { ...a, review_status: 'approved' })) : rows;
      if (JSON.stringify(next) !== saved) await persist(next);
      await request(`/assets/${asset.id}/review`, { method: 'POST', body: JSON.stringify({ action, reviewer_id: 'reviewer' }) });
      await refreshAssets(project.id);
      refreshProjects();
      return true;
    } catch (e) {
      setError(`${action === 'approve' ? 'Approval' : 'Rejection'} didn’t go through. ${message(e)}`);
      return false;
    } finally {
      setBusy(null);
    }
  }

  const remaining = rows.filter((a) => !DECIDED.has(a.review_status ?? '')).length;

  return {
    rows,
    dirty,
    loading,
    loadError,
    retry: () => setAttempt((n) => n + 1),
    busy,
    error,
    note,
    canUndo: past.length > 0,
    canRedo: future.length > 0,
    remaining,
    savedLabels,
    change,
    update,
    begin,
    live,
    undo,
    redo,
    save,
    decide,
  };
}

export type Edits = ReturnType<typeof useEdits>;
