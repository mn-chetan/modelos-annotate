/*
 * The live workspace store: projects and their assets from the API, shared by every page
 * through useSyncExternalStore. It also owns the product's routing rule, so every page agrees
 * on what the AI approved, what went to people, and what failed.
 */
import { useEffect, useSyncExternalStore } from 'react';
import { api, resolveApiBase, type AnnotationResponse, type AssetResponse, type ProjectResponse } from '../services/api';
import type { Project, TaskView } from '../showcase/content';
import { colourAt } from './pages/new-project/model';

/** What kind of label a project produces, which decides how it is reviewed. */
export type LabelKind = 'boxes' | 'spans' | 'document';

export type LiveClass = { name: string; color: string };

export type LiveProject = Project & {
  raw: ProjectResponse;
  kind: LabelKind;
  /** The AI approves an item when every label is at or above this confidence. */
  line: number;
  classList: LiveClass[];
};

export type TextAnalysis = {
  text?: string;
  analysis_type?: string;
  annotations?: Annotation[];
  quality_report?: { confidence_score?: number; confidence_threshold?: number; final_decision?: string };
};

export type LiveAsset = AssetResponse & {
  caption?: string;
  inference_error?: string | null;
  ai_completed_at?: string;
  text_analysis?: TextAnalysis | null;
  text_analysis_type?: string;
};

export type Annotation = AnnotationResponse & { review_status?: string | null; version?: number };

/* ---------- Statuses and the routing rule ---------- */

const HUMAN_APPROVED = new Set(['approved', 'final_approved', 'human_approved', 'human_modified_approved', 'accepted']);
const AI_APPROVED = new Set(['auto_approved']);
const REJECTED = new Set(['human_rejected', 'rejected']);

export const isApproved = (status?: string | null) => {
  const s = status?.toLowerCase() ?? '';
  return HUMAN_APPROVED.has(s) || AI_APPROVED.has(s);
};

export const isDrafted = (a: LiveAsset) =>
  !!a.ai_completed_at ||
  !!a.text_analysis ||
  a.status === 'annotated' ||
  (a.status === 'ready' && (a.annotation_count ?? 0) > 0) ||
  isApproved(a.review_status);

/**
 * Where an item stands in the pipeline:
 * - approvedByAi: the AI was sure enough on every label to approve it unseen
 * - toReview: drafted, waiting on a person
 * - approved: a person approved it
 * - rejected: a person rejected it
 * - failed: the AI run failed for this item
 * - notRun: uploaded, not drafted yet
 */
export type Route = 'approvedByAi' | 'toReview' | 'approved' | 'rejected' | 'failed' | 'notRun';

export function routeOf(a: LiveAsset): Route {
  const s = a.review_status?.toLowerCase() ?? '';
  if (AI_APPROVED.has(s)) return 'approvedByAi';
  if (HUMAN_APPROVED.has(s)) return 'approved';
  if (REJECTED.has(s)) return 'rejected';
  if (a.status === 'failed' || a.inference_error) return 'failed';
  if (!isDrafted(a)) return 'notRun';
  return 'toReview';
}

export const needsReview = (a: LiveAsset) => routeOf(a) === 'toReview';

export const isRunning = (a: LiveAsset) => ['queued', 'processing'].includes(a.status);

/* ---------- Mapping API projects onto the workspace's project shape ---------- */

function kindOf(raw: ProjectResponse): LabelKind {
  const modality = raw.modality ?? 'image';
  if (modality !== 'text' && modality !== 'document') return 'boxes';
  const task = (raw.task_type ?? '').toUpperCase();
  return task === 'SENTIMENT_ANALYSIS' || task === 'TEXT_CLASSIFICATION' ? 'document' : 'spans';
}

const TASK_NAMES: Record<string, string> = {
  object_detection: 'Object detection',
  detection: 'Object detection',
  NER: 'Entities',
  ENTITY_EXTRACTION: 'Entities',
  SENTIMENT_ANALYSIS: 'Sentiment',
  TEXT_CLASSIFICATION: 'Classification',
  RELATION_EXTRACTION: 'Relations',
};

function viewOf(raw: ProjectResponse, kind: LabelKind): TaskView {
  if (kind === 'boxes') return 'detection';
  if (kind === 'spans') return 'ner';
  return 'sentiment';
}

type RawPolicy = { auto_approve_threshold?: number; confidence_threshold?: number };

export function lineOf(raw: ProjectResponse): number {
  const policy = (raw as ProjectResponse & { quality_policy?: RawPolicy }).quality_policy;
  return policy?.auto_approve_threshold ?? raw.confidence_threshold ?? policy?.confidence_threshold ?? 0.95;
}

/** The project's classes in order, each with its saved colour or the palette's next one. */
function classesOf(raw: ProjectResponse): LiveClass[] {
  const names = raw.labels?.length ? raw.labels : (raw.label_ontology ?? []).map((c) => c.name ?? '').filter(Boolean);
  return names.map((name, i) => ({
    name,
    color: raw.label_ontology?.find((c) => c.name === name)?.color || colourAt(i),
  }));
}

function mapProject(raw: ProjectResponse, assets?: LiveAsset[]): LiveProject {
  const modality = raw.modality === 'video' ? 'video' : raw.modality === 'text' || raw.modality === 'document' ? 'text' : 'image';
  const kind = kindOf(raw);
  const classList = classesOf(raw);
  const routes = assets?.map(routeOf);
  const count = (r: Route) => routes?.filter((x) => x === r).length ?? 0;
  return {
    raw,
    id: raw.id,
    name: raw.name,
    modality,
    kind,
    view: viewOf(raw, kind),
    task: TASK_NAMES[raw.task_type ?? ''] ?? TASK_NAMES[(raw.task_type ?? '').toUpperCase()] ?? 'Annotation',
    unit: modality === 'image' ? 'images' : modality === 'video' ? 'clips' : 'documents',
    line: lineOf(raw),
    classList,
    classes: classList.map((c) => c.name),
    assets: assets?.length ?? raw.item_count ?? 0,
    aiDone: assets ? assets.filter(isDrafted).length : (raw.annotated_count ?? 0),
    reviewPending: assets ? count('toReview') : (raw.pending_review_count ?? 0),
    // Quality check isn't connected to live projects, so nothing waits there.
    qcPending: 0,
    approved: assets ? count('approved') + count('approvedByAi') : (raw.approved_count ?? 0),
    lead: '—',
    updated: raw.updated_at ? new Date(raw.updated_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—',
  };
}

/* ---------- The store ---------- */

type State = {
  projects: LiveProject[];
  assets: Record<string, LiveAsset[]>;
  loading: boolean;
  error: string;
  revision: number;
};

let state: State = { projects: [], assets: {}, loading: true, error: '', revision: 0 };
const listeners = new Set<() => void>();

function publish(patch: Partial<State>) {
  state = { ...state, ...patch, revision: state.revision + 1 };
  listeners.forEach((fn) => fn());
}

const subscribe = (fn: () => void) => {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
};

export function useProjects() {
  return useSyncExternalStore(subscribe, () => state);
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

let pending: Promise<void> | undefined;

export function refreshProjects() {
  if (pending) return pending;
  pending = api
    .getProjects({ throwOnError: true, forceRefresh: true })
    .then((rows) => publish({ projects: rows.map((r) => mapProject(r, state.assets[r.id])), loading: false, error: '' }))
    .catch((e) => publish({ loading: false, error: message(e) }))
    .finally(() => {
      pending = undefined;
    });
  return pending;
}

export async function refreshAssets(id: string) {
  const assets = (await api.getProjectAssets(id, { throwOnError: true, forceRefresh: true })) as LiveAsset[];
  publish({
    assets: { ...state.assets, [id]: assets },
    projects: state.projects.map((p) => (p.id === id ? mapProject(p.raw, assets) : p)),
  });
  return assets;
}

/** A project's assets, loaded on first use and kept fresh by the pages that change them. */
export function useAssets(id: string) {
  const s = useProjects();
  useEffect(() => {
    refreshAssets(id).catch((e) => publish({ error: message(e) }));
  }, [id]);
  return s.assets[id];
}

/* ---------- Requests ---------- */

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${resolveApiBase()}${path}`, {
    ...init,
    headers: init.body instanceof FormData ? init.headers : { 'Content-Type': 'application/json', ...init.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body.detail === 'string' ? body.detail : body.message || body.error;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json();
}

export const getAnnotations = (assetId: string) => request<Annotation[]>(`/assets/${encodeURIComponent(assetId)}/annotations`);

/** Every annotation in a project, fetched a few assets at a time. */
export async function getProjectAnnotations(assets: LiveAsset[]) {
  const out: Annotation[] = [];
  for (let i = 0; i < assets.length; i += 6) {
    const rows = await Promise.all(assets.slice(i, i + 6).map((a) => getAnnotations(a.id)));
    out.push(...rows.flat());
  }
  return out;
}

export type ExportFormat = 'coco' | 'yolo' | 'json' | 'csv';

export async function exportLabels(projectId: string, format: ExportFormat) {
  const response = await fetch(
    `${resolveApiBase()}/projects/${encodeURIComponent(projectId)}/export?format=${format}&annotation_source=approved&include_images=false`,
  );
  if (!response.ok) throw new Error(await response.text());
  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)/)?.[1] || `${projectId}-${format}.zip`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
