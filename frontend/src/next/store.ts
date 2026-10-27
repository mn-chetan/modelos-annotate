import { useEffect, useSyncExternalStore } from 'react';
import { api, resolveApiBase, type ProjectResponse, type AssetResponse, type AnnotationResponse } from '../services/api';
import type { Project } from '../showcase/content';

export type LiveProject = Project & { raw: ProjectResponse };
export type LiveAsset = AssetResponse & { caption?: string; inference_error?: string; ai_completed_at?: string };
export type Annotation = AnnotationResponse & { review_status?: string; version?: number };
const approved = new Set(['approved', 'final_approved', 'human_approved', 'human_modified_approved', 'auto_approved']);
export const isApproved = (status: string) => approved.has(status?.toLowerCase());
export const isDrafted = (a: LiveAsset) => !!a.ai_completed_at || (a.status === 'ready' && a.annotation_count! > 0) || a.status === 'annotated';
export const needsReview = (a: LiveAsset) => (isDrafted(a) || a.annotation_count! > 0) && a.status !== 'failed' && !isApproved(a.review_status) && !['human_rejected', 'rejected', 'flagged'].includes(a.review_status);
function mapProject(raw: ProjectResponse, assets?: LiveAsset[]): LiveProject {
  const modality = raw.modality === 'video' ? 'video' : ['text','document'].includes(raw.modality!) ? 'text' : 'image';
  return { raw, id: raw.id, name: raw.name, modality, task: raw.task_type === 'object_detection' ? 'Object detection' : raw.task_type || 'Annotation',
    view: 'detection', unit: modality === 'image' ? 'images' : modality === 'video' ? 'clips' : 'documents',
    assets: assets?.length ?? raw.asset_count ?? 0,
    aiDone: assets ? assets.filter(isDrafted).length : raw.annotated_count ?? 0,
    reviewPending: assets ? assets.filter(needsReview).length : raw.pending_review_count ?? 0,
    qcPending: 0, approved: assets ? assets.filter(a => isApproved(a.review_status)).length : raw.approved_count ?? 0,
    classes: raw.labels || raw.label_ontology?.map(c => c.name || '').filter(Boolean) || [],
    lead: raw.assigned_team || '—', updated: raw.updated_at ? new Date(raw.updated_at).toLocaleString() : '—' };
}
type State = { projects: LiveProject[]; assets: Record<string, LiveAsset[]>; loading: boolean; error: string; revision: number };
let state: State = { projects: [], assets: {}, loading: true, error: '', revision: 0 };
const listeners = new Set<() => void>();
function publish(patch: Partial<State>) { state = { ...state, ...patch, revision: state.revision + 1 }; listeners.forEach(fn => fn()); }
const subscribe = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn); }; };
export function useProjects() { return useSyncExternalStore(subscribe, () => state); }
let pending: Promise<void> | undefined;
export function refreshProjects() {
  if (pending) return pending;
  pending = api.getProjects({ throwOnError: true, forceRefresh: true }).then(rows => {
    publish({ projects: rows.map(r => mapProject(r, state.assets[r.id])), loading: false, error: '' });
  }).catch(e => { publish({ loading: false, error: String(e.message || e) }); }).finally(() => { pending = undefined; });
  return pending;
}
export async function refreshAssets(id: string) {
  const assets = await api.getProjectAssets(id, { throwOnError: true, forceRefresh: true });
  publish({ assets: { ...state.assets, [id]: assets }, projects: state.projects.map(p => p.id === id ? mapProject(p.raw, assets) : p) });
  return assets;
}
export function useAssets(id: string) {
  const s = useProjects();
  useEffect(() => { refreshAssets(id).catch(e => publish({ error: e.message })); }, [id]);
  return s.assets[id];
}
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${resolveApiBase()}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...init.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : body.message || body.error || `Request failed (${response.status})`);
  }
  return response.json();
}
export const getAnnotations = (id: string) => request<Annotation[]>(`/assets/${encodeURIComponent(id)}/annotations`);
export async function exportLabels(id: string, format: 'coco' | 'yolo') {
  const response = await fetch(`${resolveApiBase()}/projects/${encodeURIComponent(id)}/export?format=${format}&annotation_source=approved&include_images=false`);
  if (!response.ok) throw new Error(await response.text());
  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement('a'); a.href = url;
  a.download = response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)/)?.[1] || `${id}-${format}.zip`;
  a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
