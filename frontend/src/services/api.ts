/**
 * API client module connecting the ModelOS Annotate UI to the FastAPI Backend.
 */

// Dynamic API base: resolves /app1/api/v1 when deployed or accessed beneath /app1 prefix, or /api/v1 otherwise.
export const resolveApiBase = (): string => {
  const env = typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env : undefined;
  if (env?.VITE_API_BASE_URL) {
    return env.VITE_API_BASE_URL;
  }
  const baseUrl = (typeof env?.BASE_URL === 'string' ? env.BASE_URL : '') || '';
  const pathname = typeof window !== 'undefined' ? window.location.pathname : '';
  const isApp1 = baseUrl.startsWith('/app1') || pathname.startsWith('/app1');
  return isApp1 ? '/app1/api/v1' : '/api/v1';
};

const API_BASE = resolveApiBase();
// Keep authentication on the same API mount as the current deployment. This
// matters when the UI is served below /app1: posting to the root /api path can
// be handled by the frontend proxy and return 405 Method Not Allowed.
// Keep project, asset, and report calls on the same API mount as the deployed
// UI. When the UI is served below /app1, the backend is mounted at /app1/api/v1.
const PROJECTS_API_BASE = resolveApiBase();
const REPORT_API_BASE = resolveApiBase();
// Dashboard data is persisted server-side and expensive to aggregate. Keep
// it warm across navigation remounts; mutations explicitly invalidate it.
const DASHBOARD_CACHE_TTL_MS = 300_000;
type TimedCacheEntry<T> = { value: T; expiresAt: number };
const projectsCache = new Map<string, TimedCacheEntry<ProjectResponse[]>>();
const healthCache = new Map<string, TimedCacheEntry<HealthResponse>>();
const dashboardCache = new Map<string, TimedCacheEntry<ProductionDashboardResponse | null>>();
const qualityCache = new Map<string, TimedCacheEntry<QualityReportResponse | null>>();
const assetsCache = new Map<string, TimedCacheEntry<AssetResponse[]>>();

const getCached = <T>(cache: Map<string, TimedCacheEntry<T>>, key: string): T | undefined => {
  const entry = cache.get(key);
  if (!entry) return undefined;
  if (entry.expiresAt <= Date.now()) {
    cache.delete(key);
    return undefined;
  }
  return entry.value;
};

const setCached = <T>(cache: Map<string, TimedCacheEntry<T>>, key: string, value: T): T => {
  cache.set(key, { value, expiresAt: Date.now() + DASHBOARD_CACHE_TTL_MS });
  return value;
};

export interface HealthResponse {
  status: string;
  database?: {
    status: string;
    provider?: string;
  };
  models?: Record<string, string>;
  storage?: {
    status: string;
  };
}

export interface TextHITLDashboardResponse {
  project_id: string;
  confidence_threshold?: number | null;
  qc_sample_rate?: number | null;
  pending_human_annotator_tasks?: number | null;
  pending_quality_auditor_tasks?: number | null;
  low_confidence_tasks?: number | null;
  high_confidence_sampled_tasks?: number | null;
  rework_tasks?: number | null;
  passed_tasks?: number | null;
  failed_tasks?: number | null;
  scorecard?: {
    total_docs: number;
    auto_approved_docs: number;
    auto_rate: number;
    human_review_docs: number;
    human_review_rate: number;
    human_edit_rate: number;
    cost_saved_dollars: number;
    time_saved_hrs: number;
    workload_delta_pct: number;
    threshold?: number;
  };
  annotation_breakdown?: Array<{
    id: string;
    name: string;
    total_docs: number;
    ai_processed_docs: number;
    ai_processed_pct: number;
    hitl_docs: number;
    hitl_pct: number;
    accuracy?: number | null;
    cost_saved_dollars?: number;
  }>;
  area_identification?: Array<{
    area_name: string;
    category: string;
    ai_confidence: number | null;
    identification_rate: number;
    trend_direction: string;
    trend_change: string;
    sample_identified: string;
    volume: number;
  }>;
  annotators?: Array<{
    id: string; name: string; role: string; assigned_docs: number; completed_docs: number;
    avg_time_sec: number | null; ai_edit_rate: number | null; audit_pass_rate: number | null;
    status: string;
  }>;
  triage?: { disputed_count: number; low_latency_count: number; active_learning_count: number };
  audit_pass_rate?: { value?: number | null };
  inter_annotator_agreement?: { value?: number | null };
}

export interface CreateProjectPayload {
  name: string;
  description?: string;
  project_type?: string;
  domain_use_case?: string;
  data_type?: string;
  cloud_storage_url?: string;
  media_format?: string;
  annotation_types?: string[];
  expected_output_format?: string;
  quality_level?: string;
  assigned_team?: string;
  priority?: string;
  due_date?: string;
  target_classes?: Array<{ id?: string; name: string; color?: string }>;
  sentiment_analysis_level?: 'document' | 'page' | 'paragraph' | 'sentence';
  classification_analysis_level?: 'document' | 'page' | 'paragraph' | 'sentence';
}

export interface ProjectResponse {
  id: string;
  name: string;
  task_type?: string;
  confidence_threshold?: number;
  description?: string;
  project_type?: string;
  modality?: 'image' | 'video' | 'text' | 'document' | string;
      sentiment_analysis_level?: 'document' | 'page' | 'paragraph' | 'sentence';
      classification_analysis_level?: 'document' | 'page' | 'paragraph' | 'sentence';
  status?: string;
  created_at?: string;
  updated_at?: string;
  item_count?: number;
  annotated_count?: number;
  reviewed_count?: number;
  approved_count?: number;
  pending_review_count?: number;
  allocated_operators?: number | null;
  average_review_time?: number | null;
  asset_count?: number;
  assigned_team?: string;
  quality_level?: string;
  priority?: string;
  due_date?: string;
  media_format?: string;
  labels?: string[];
  label_ontology?: Array<{ id?: string; name?: string; color?: string; shortcutIndex?: number }>;
  target_classes?: Array<{ id?: string; name?: string; color?: string }>;
}

export interface TextAnalysisRequest {
  projectId: string;
  assetId?: string;
  analysisType: 'NER' | 'Sentiment' | 'Classification' | 'PII';
  assessmentName?: string;
  identificationName?: string;
  text?: string;
  files?: File[];
}

export interface TextAnalysisResponse {
  analysis_type?: string;
  capability?: string;
  analysis_id?: string;
  project_id?: string;
  asset_id?: string;
  assessment_name?: string;
  text?: string;
  annotations?: Array<{
    id?: string;
    label?: string;
    text_span?: { start?: number; end?: number; text?: string; page?: number };
    geometry?: {
      start?: number;
      end?: number;
      text?: string;
      source?: string;
      target?: string;
      relation?: string;
      source_type?: string;
      target_type?: string;
      evidence?: string;
      page?: number;
      level?: 'document' | 'page' | 'paragraph' | 'sentence';
      paragraph_index?: number;
      sentence_index?: number;
    };
    review_status?: 'PENDING' | 'APPROVED' | 'REJECTED' | 'EDITED' | string;
    confidence?: number;
    geometry_type?: string;
    model_id?: string | null;
    provenance?: Record<string, unknown>;
  }>;
  quality_report?: {
    annotation_count?: number;
    invalid_spans?: number;
    errors?: unknown[];
    final_decision?: string;
    confidence_score?: number | null;
    confidence_threshold?: number;
    semantic_conflicts?: unknown[];
  };
  agent_run_id?: string;
  agent_status?: string;
  results?: Array<{
    id?: string;
    text?: string;
    label?: string;
    start?: number;
    end?: number;
    score?: number;
    sentiment?: string;
    confidence?: number;
  }>;
  status?: string;
  summary?: string;
  overall_sentiment?: string;
  raw_result?: {
    analysis_level?: 'document' | 'page' | 'paragraph' | 'sentence';
  };
}

export interface ProductionDashboardResponse {
  id: string;
  runCode?: string;
  datasetName?: string;
  domain?: string;
  status?: string;
  totalTargetImages?: number;
  kpiSnapshot?: {
    images_processed?: number;
    completion_rate?: number | null;
    approval_rate?: number | null;
    review_acceptance_rate?: number | null;
    rework_rate?: number | null;
    defect_rate?: number | null;
    reviewer_agreement?: number | null;
    quality_yield?: number | null;
    quality_index?: number | null;
    average_review_time?: number | null;
    escalation_rate?: number | null;
    consensus_pass_rate?: number | null;
    annotation_productivity?: number | null;
    annotation_confidence?: number | null;
    automation_rate?: number | null;
    hitl_rate?: number | null;
    low_confidence_escalation_rate?: number | null;
    human_override_rate?: number | null;
    unit_production_cost?: number | null;
    production_overview?: {
      processed_images?: number;
      approved_images?: number;
      approved_yield?: number | null;
      reworked_images?: number;
      rework_rate?: number | null;
      rejected_images?: number;
      rejection_rate?: number | null;
      defect_rate?: number | null;
      throughput_per_hour?: number | null;
      target_images?: number | null;
      completion_progress?: number;
      sla_target?: number | null;
      dataset_target_completion?: {
        approved_percentage?: number | null;
        reworked_percentage?: number | null;
        rejected_percentage?: number | null;
      };
      class_breakdown?: Array<{
        label: string;
        annotation_count: number;
        image_count: number;
        approved_annotation_count: number;
        approved_percentage?: number | null;
        completion_percentage?: number | null;
      }>;
      throughput_trend?: Array<{
        date: string;
        actual_images_per_hour?: number | null;
        target_images_per_hour?: number | null;
        throughput?: number | null;
        completed_images?: number;
      }>;
    };
    population?: {
      total_assets: number;
      ai_annotated_assets?: number;
      completed_assets: number;
      reviewed_assets: number;
      approved_assets: number;
      approved_first_pass_assets: number;
      pending_final_assets: number;
      reworked_assets: number;
      defective_assets: number;
      double_reviewed_assets: number;
      eligible_assets: number;
      human_review_assets: number;
      escalated_assets: number;
      human_modified_assets: number;
    };
  };
}

export interface QualityReportResponse {
  project_id?: string;
  total_items?: number;
  total_annotated?: number;
  total_human_reviewed?: number;
  total_audited?: number;
  total_passed?: number;
  total_failed?: number;
  audit_pass_rate?: number | null;
  qc_pass_rate?: number | null;
  ai_annotation_accuracy?: number | null;
  ai_accuracy_correct_evaluated?: number;
  ai_accuracy_total_evaluated?: number;
  mean_iou?: number | null;
  defect_leakage?: number | null;
  inter_annotator_agreement?: number | null;
  iou_distribution?: {
    gt_0_95?: { count: number; percentage: number };
    '0_85_0_95'?: { count: number; percentage: number };
    '0_70_0_85'?: { count: number; percentage: number };
    lt_0_70?: { count: number; percentage: number };
  } | null;
  rework_rate?: number | null;
  defect_rate?: number | null;
  defect_breakdown?: Record<string, number>;
}

export interface AssetResponse {
  id: string;
  project_id: string;
  filename: string;
  content_type: string;
  width: number;
  height: number;
  status: string;
  review_status: string;
  mean_confidence?: number | null;
  annotation_count?: number;
  image_url: string;
  preview_url?: string;
  byte_size?: number;
  duration?: number;
  created_at?: string;
  updated_at?: string;
}

export interface AnnotationResponse {
  id: string;
  asset_id: string;
  label: string;
  geometry_type?: string;
  geometry?: {
    start?: number;
    end?: number;
    text?: string;
    source?: string;
    target?: string;
    relation?: string;
    source_type?: string;
    target_type?: string;
    evidence?: string;
  };
  text_span?: { start?: number; end?: number; text?: string };
  x: number;
  y: number;
  w: number;
  h: number;
  confidence?: number | null;
  evidence_confidence?: number | null;
  original_ai_confidence?: number | null;
  source: string;
  model_id?: string | null;
  provenance?: Record<string, unknown>;
  inferred_at?: string;
  polygon?: number[][];
  created_at?: string;
}

export interface BatchItemResponse {
  id: string;
  batch_id: string;
  asset_id: string;
  status: string;
  detection_count?: number;
}

export interface BatchResponse {
  id: string;
  project_id: string;
  status: string;
  updated_at?: string;
  items?: BatchItemResponse[];
}

export interface HumanAnnotatorTaskResponse {
  id: string;
  project_id: string;
  asset_id: string;
  status: string;
  audit_source?: string | null;
  revisions?: Array<{ status?: string; source?: string }>;
  current_annotations?: Array<Record<string, unknown>>;
}

export interface QualityAuditTaskResponse extends HumanAnnotatorTaskResponse {
  filename?: string;
  content_type?: string;
  width?: number;
  height?: number;
  image_url?: string;
  preview_url?: string;
  annotations?: AnnotationResponse[];
  decision?: Record<string, unknown>;
  audit_source?: string;
}

export interface QualityAuditRecommendation {
  status: 'ready' | 'unavailable' | string;
  summary?: string;
  recommendation?: 'PASS' | 'FAIL' | 'HUMAN_REVIEW' | string;
  confidence?: number | null;
  categories?: Array<{ name: string; evidence?: string; severity?: string }>;
  evidence?: string[];
  agent_run_id?: string | null;
}

class ApiService {
  invalidateProjectCache(projectId: string) {
    const cacheKey = `anonymous:${projectId}`;
    dashboardCache.delete(cacheKey);
    qualityCache.delete(cacheKey);
    assetsCache.delete(cacheKey);
    projectsCache.delete('anonymous');
  }

  private getHeaders(isJson = true): HeadersInit {
    const headers: Record<string, string> = {
      'X-User-Role': 'PROJECT_MANAGER',
      'X-User-Id': 'human_operator_1',
    };
    if (isJson) {
      headers['Content-Type'] = 'application/json';
    }
    return headers;
  }

  async checkHealth(): Promise<HealthResponse> {
    const cacheKey = 'anonymous';
    const cached = getCached(healthCache, cacheKey);
    if (cached) return cached;
    try {
      // Health is exposed on the root API prefix in deployments where the UI
      // is mounted below /app1. Using API_BASE there would fetch the SPA HTML.
      const res = await fetch(`${PROJECTS_API_BASE}/health`, {
        headers: this.getHeaders(),
      });
      if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
      const contentType = res.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) {
        throw new Error(`Health check returned ${contentType || 'non-JSON'} content`);
      }
      return setCached(healthCache, cacheKey, await res.json());
    } catch (err) {
      console.warn('Backend health check error:', err);
      return { status: 'degraded', database: { status: 'unknown' } };
    }
  }

  async getProjects(options?: { throwOnError?: boolean; forceRefresh?: boolean }): Promise<ProjectResponse[]> {
    const cacheKey = 'anonymous';
    const cached = options?.forceRefresh ? undefined : getCached(projectsCache, cacheKey);
    if (cached) return cached;
    try {
      const res = await fetch(`${PROJECTS_API_BASE}/projects`, {
        headers: this.getHeaders(),
      });
      if (!res.ok) {
        const body = await res.text().catch(() => '');
        throw new Error(`Projects request failed (${res.status})${body ? `: ${body.slice(0, 160)}` : ''}`);
      }
      const contentType = res.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) {
        throw new Error(`Projects endpoint returned ${contentType || 'non-JSON'} response`);
      }
      const data = await res.json();
      return setCached(projectsCache, cacheKey, Array.isArray(data) ? data : (data as any).projects || []);
    } catch (err) {
      console.error('Error fetching projects from backend:', err);
      if (options?.throwOnError) throw err;
      return [];
    }
  }

  async deleteProject(projectId: string): Promise<void> {
    const res = await fetch(`${PROJECTS_API_BASE}/projects/${encodeURIComponent(projectId)}`, {
      method: 'DELETE',
      headers: this.getHeaders(),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to delete project' }));
      throw new Error(err.detail || err.message || 'Failed to delete project');
    }
    this.invalidateProjectCache(projectId);
  }




  async createProject(payload: CreateProjectPayload): Promise<ProjectResponse> {
    const annotationTypes = payload.annotation_types?.includes('All Text Features')
      ? ['NER Annotation', 'Sentiment Annotation', 'Text Classification', 'Relation Extraction']
      : payload.annotation_types || [];
    const textTaskType = annotationTypes.includes('NER Annotation')
      ? 'NER'
      : annotationTypes.includes('Sentiment Annotation')
      ? 'SENTIMENT_ANALYSIS'
      : annotationTypes.includes('Text Classification')
      ? 'TEXT_CLASSIFICATION'
      : annotationTypes.includes('Relation Extraction')
      ? 'RELATION_EXTRACTION'
      : null;
    const isTextAnnotation = payload.project_type === 'Text Annotation';
    const isImageAnnotation = payload.project_type === 'Image Annotation';
    const imageTargets = (payload.target_classes || []).filter((target) => target.name.trim());
    const imageTaskType = payload.annotation_types?.includes('Segmentation')
      ? 'segmentation'
      : payload.annotation_types?.includes('Classification')
      ? 'classification'
      : 'object_detection';
    // Persist every Text Annotation project as a text project, even while the
    // user has not selected a text subtype yet (for example, Save Draft).
    // Falling through to the image/default payload used to store these as
    // object_detection projects.
    const requestBody = isTextAnnotation
      ? {
          name: payload.name,
          goal: payload.description || '',
          task_type: textTaskType || 'NER',
          classification_mode: 'single',
          labels: (textTaskType || 'NER') === 'NER' ? imageTargets.map((target) => target.name.trim()) : [],
          label_ontology: (textTaskType || 'NER') === 'NER' ? imageTargets : [],
          label_strategy: 'generic',
          expected_output_format: payload.expected_output_format || '',
          modality: 'text',
          sentiment_analysis_level: payload.sentiment_analysis_level || 'document',
          classification_analysis_level: payload.classification_analysis_level || 'document',
        }
      : isImageAnnotation
      ? {
          name: payload.name,
          goal: payload.description || '',
          task_type: imageTaskType,
          classification_mode: 'single',
          labels: imageTargets.map((target) => target.name.trim()),
          label_ontology: imageTargets,
          label_strategy: 'generic',
          expected_output_format: payload.expected_output_format || '',
          modality: 'image',
        }
      : {
          name: payload.name,
          description: payload.description || '',
          project_type: payload.project_type || 'Image Annotation',
          modality: (payload.media_format || (payload.project_type?.includes('Text') ? 'text' : 'image')).toLowerCase(),
          domain_use_case: payload.domain_use_case,
          data_type: payload.data_type,
          cloud_storage_url: payload.cloud_storage_url,
          media_format: payload.media_format,
          annotation_types: payload.annotation_types || [],
          expected_output_format: payload.expected_output_format,
          quality_level: payload.quality_level,
          assigned_team: payload.assigned_team,
          priority: payload.priority,
          due_date: payload.due_date,
          target_classes: payload.target_classes || [],
        };
    // Project CRUD is exposed on the root API prefix in the deployed app,
    // including when the UI itself is mounted below /app1.
    const res = await fetch(`${PROJECTS_API_BASE}/projects`, {
      method: 'POST',
      headers: this.getHeaders(true),
      body: JSON.stringify(requestBody),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ detail: 'Failed to create project' }));
      throw new Error(errData.detail || errData.message || 'Error creating project in backend');
    }

    const createdProject = await res.json();
    projectsCache.delete('anonymous');
    return createdProject;
  }

  async getProjectDetail(projectId: string): Promise<ProjectResponse | null> {
    try {
      // Project routes are served from the root API prefix even when the app
      // itself is served under /app1.
      const res = await fetch(`${PROJECTS_API_BASE}/projects/${encodeURIComponent(projectId)}`, {
        headers: this.getHeaders(),
      });
      if (!res.ok) return null;
      const contentType = res.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) {
        throw new Error(`Project detail returned ${contentType || 'non-JSON'} content`);
      }
      return await res.json();
    } catch (err) {
      console.error(`Error fetching project ${projectId}:`, err);
      return null;
    }
  }

  async getProjectAssets(projectId: string, options?: { throwOnError?: boolean; forceRefresh?: boolean }): Promise<AssetResponse[]> {
    const cacheKey = `anonymous:${projectId}`;
    const cached = options?.forceRefresh ? undefined : getCached(assetsCache, cacheKey);
    if (cached) return cached;
    try {
      const res = await fetch(`${PROJECTS_API_BASE}/projects/${encodeURIComponent(projectId)}/assets`, {
        headers: this.getHeaders(),
      });
      console.debug('[API] project assets response', { projectId, status: res.status, ok: res.ok });
      if (!res.ok) throw new Error(`Asset list request failed: ${res.status}`);
      const payload = await res.json();
      return setCached(assetsCache, cacheKey, Array.isArray(payload) ? payload : []);
    } catch (err) {
      console.error(`Error fetching assets for project ${projectId}:`, err);
      if (options?.throwOnError) throw err;
      return [];
    }
  }

  private assetAnnotationsCache = new Map<string, AnnotationResponse[]>();

  async getAssetAnnotations(assetId: string, options?: { throwOnError?: boolean }): Promise<AnnotationResponse[]> {
    const cached = this.assetAnnotationsCache.get(assetId);
    if (cached) return cached;
    try {
      const res = await fetch(`${PROJECTS_API_BASE}/assets/${assetId}/annotations`, {
        headers: this.getHeaders(),
      });
      console.debug('[API] asset annotations response', { assetId, status: res.status, ok: res.ok });
      if (!res.ok) throw new Error(`Annotation request failed: ${res.status}`);
      const payload = await res.json();
      const list = Array.isArray(payload) ? payload : [];
      this.assetAnnotationsCache.set(assetId, list);
      return list;
    } catch (err) {
      console.error(`Error fetching annotations for asset ${assetId}:`, err);
      if (options?.throwOnError) throw err;
      return [];
    }
  }

  private imageBlobUrlCache = new Map<string, string>();

  getAssetImageUrl(assetId: string): string {
    return `${PROJECTS_API_BASE}/assets/${encodeURIComponent(assetId)}/image`;
  }

  getAssetPreviewUrl(assetId: string): string {
    return `${PROJECTS_API_BASE}/assets/${encodeURIComponent(assetId)}/preview`;
  }

  invalidateAssetImage(assetId: string): void {
    const cached = this.imageBlobUrlCache.get(assetId);
    if (cached) {
      try {
        URL.revokeObjectURL(cached);
      } catch {
        // ignore
      }
      this.imageBlobUrlCache.delete(assetId);
    }
  }

  async getAssetImageBlobUrl(assetId: string): Promise<string> {
    const cached = this.imageBlobUrlCache.get(assetId);
    if (cached) return cached;
    try {
      const res = await fetch(this.getAssetImageUrl(assetId), {
        headers: this.getHeaders(false),
      });
      if (!res.ok) {
        throw new Error(`Asset image request failed: ${res.status}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      this.imageBlobUrlCache.set(assetId, url);
      return url;
    } catch (err) {
      this.imageBlobUrlCache.delete(assetId);
      throw err;
    }
  }

  async getProjectBatches(projectId: string): Promise<BatchResponse[]> {
    const maxAttempts = 3;
    const baseDelayMs = 300;
    const base = resolveApiBase();

    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        const res = await fetch(`${base}/projects/${encodeURIComponent(projectId)}/batches`, {
          headers: this.getHeaders(),
        });

        // 4xx client errors (400, 401, 403, 404, 422) are permanent: do not retry
        if (res.status >= 400 && res.status < 500) {
          if (res.status === 404) {
            console.warn(`[API] Batches endpoint not found for project ${projectId} (HTTP 404)`);
          } else {
            console.warn(`[API] Failed to fetch batches for project ${projectId} (HTTP ${res.status})`);
          }
          return [];
        }

        // 502/503/504 transient server errors: retry with backoff if attempts remain
        if (!res.ok) {
          if (attempt < maxAttempts && (res.status === 502 || res.status === 503 || res.status === 504)) {
            const delay = baseDelayMs * Math.pow(2, attempt - 1);
            await new Promise((resolve) => setTimeout(resolve, delay));
            continue;
          }
          return [];
        }

        return await res.json();
      } catch (err: unknown) {
        // Transient network failures (TypeError: Failed to fetch / net::ERR_NETWORK_CHANGED / socket resets)
        if (attempt < maxAttempts) {
          const delay = baseDelayMs * Math.pow(2, attempt - 1);
          await new Promise((resolve) => setTimeout(resolve, delay));
          continue;
        }
        console.error(`Error fetching batches for project ${projectId} after ${maxAttempts} attempts:`, err);
        return [];
      }
    }
    return [];
  }

  async getHumanAnnotatorTasks(projectId: string): Promise<HumanAnnotatorTaskResponse[]> {
    try {
      const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/hitl/human/tasks`, {
        headers: this.getHeaders(),
      });
      if (!res.ok) {
        console.warn(`[API] Human Annotator queue unavailable for ${projectId}: ${res.status}`);
        return [];
      }
      const payload = await res.json();
      if (Array.isArray(payload)) return payload;
      return Array.isArray(payload?.tasks) ? payload.tasks : Array.isArray(payload?.items) ? payload.items : [];
    } catch (err) {
      console.warn(`Error fetching Human Annotator tasks for project ${projectId}:`, err);
      return [];
    }
  }

  async getQualityAuditorTasks(projectId: string): Promise<QualityAuditTaskResponse[]> {
    const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/hitl/qc/tasks`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error(`Quality queue request failed (${res.status})`);
    const payload = await res.json();
    return Array.isArray(payload) ? payload : [];
  }

  async getQualityAuditTask(taskId: string): Promise<QualityAuditTaskResponse> {
    const res = await fetch(`${API_BASE}/hitl/tasks/${encodeURIComponent(taskId)}`, { headers: this.getHeaders() });
    if (!res.ok) throw new Error(`Quality task request failed (${res.status})`);
    const created = await res.json();
    projectsCache.delete('anonymous');
    return created;
  }

  async getQualityAuditRecommendation(taskId: string): Promise<QualityAuditRecommendation> {
    const res = await fetch(`${API_BASE}/hitl/tasks/${encodeURIComponent(taskId)}/qc/recommendation`, {
      method: 'POST', headers: this.getHeaders(true), body: JSON.stringify({}),
    });
    if (!res.ok) throw new Error(`Quality agent request failed (${res.status})`);
    return await res.json();
  }

  async saveQualityAudit(taskId: string, payload: { checklist: Record<string, unknown>; comments?: string; decision: 'PASS' | 'FAIL' }): Promise<unknown> {
    const base = `${API_BASE}/hitl/tasks/${encodeURIComponent(taskId)}/qc`;
    const path = payload.decision === 'PASS' ? '/pass' : '/fail';
    const body = payload.decision === 'PASS'
      ? { checklist: payload.checklist, comments: payload.comments || '' }
      : { failure_reason: payload.comments || 'Quality issue identified', feedback: payload.comments || '', required_corrections: payload.comments || '', checklist: payload.checklist };
    const res = await fetch(`${base}${path}`, { method: 'POST', headers: this.getHeaders(true), body: JSON.stringify(body) });
    if (!res.ok) throw new Error(`Quality audit submit failed (${res.status})`);
    return await res.json();
  }

  async createAssetAnnotation(assetId: string, payload: {
    label: string;
    geometry_type: 'box' | 'polygon' | 'polyline' | 'point';
    geometry?: Record<string, unknown>;
    x: number;
    y: number;
    w: number;
    h: number;
    source: 'human';
  }): Promise<AnnotationResponse> {
    const res = await fetch(`${PROJECTS_API_BASE}/assets/${encodeURIComponent(assetId)}/annotations`, {
      method: 'POST',
      headers: this.getHeaders(true),
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`Failed to save annotation (${res.status})`);
    assetsCache.clear();
    return await res.json();
  }

  async updateAssetAnnotation(annotationId: string, payload: {
    label?: string;
    geometry_type?: 'box' | 'polygon' | 'polyline' | 'point';
    geometry?: Record<string, unknown>;
    x?: number;
    y?: number;
    w?: number;
    h?: number;
    source?: 'human';
  }): Promise<AnnotationResponse> {
    const res = await fetch(`${PROJECTS_API_BASE}/annotations/${encodeURIComponent(annotationId)}`, {
      method: 'PATCH',
      headers: this.getHeaders(true),
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`Failed to update annotation (${res.status})`);
    return await res.json();
  }

  async deleteAssetAnnotation(annotationId: string): Promise<void> {
    const res = await fetch(`${PROJECTS_API_BASE}/annotations/${encodeURIComponent(annotationId)}`, {
      method: 'DELETE',
      headers: this.getHeaders(false),
    });
    if (!res.ok) throw new Error(`Failed to delete annotation (${res.status})`);
  }

  async reviewAssetAnnotation(annotationId: string, action: 'approve' | 'reject' | 'modify' = 'approve'): Promise<void> {
    const res = await fetch(`${PROJECTS_API_BASE}/annotations/${encodeURIComponent(annotationId)}/review`, {
      method: 'POST',
      headers: this.getHeaders(true),
      body: JSON.stringify({ action, reviewer_id: 'human_annotator' }),
    });
    if (!res.ok) throw new Error(`Failed to submit annotation (${res.status})`);
  }

  async batchSaveAssetAnnotations(assetId: string, annotations: Array<Record<string, unknown>>): Promise<Record<string, unknown>> {
    const res = await fetch(`${PROJECTS_API_BASE}/assets/${encodeURIComponent(assetId)}/annotations/batch`, {
      method: 'PUT',
      headers: this.getHeaders(true),
      body: JSON.stringify({ annotations }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to batch save annotations' }));
      throw new Error(err.detail || 'Failed to batch save annotations');
    }
    assetsCache.clear();
    return await res.json();
  }

  async submitHitlTaskForQc(taskId: string, annotations?: Array<Record<string, unknown>>): Promise<Record<string, unknown>> {
    const res = await fetch(`${PROJECTS_API_BASE}/hitl/tasks/${encodeURIComponent(taskId)}/submit-qc`, {
      method: 'POST',
      headers: this.getHeaders(true),
      body: JSON.stringify(annotations ? { annotations } : {}),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to submit task for Quality Check' }));
      throw new Error(err.detail || 'Failed to submit task for Quality Check');
    }
    assetsCache.clear();
    return await res.json();
  }

  async updateHitlAnnotation(taskId: string, annotationId: string, payload: { label?: string; bbox?: number[] }): Promise<AnnotationResponse> {
    const res = await fetch(`${PROJECTS_API_BASE}/hitl/tasks/${encodeURIComponent(taskId)}/annotations/${encodeURIComponent(annotationId)}`, {
      method: 'PATCH', headers: this.getHeaders(true), body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to update HITL annotation' }));
      throw new Error(err.detail || 'Failed to update HITL annotation');
    }
    return await res.json();
  }

  async addHitlAnnotation(taskId: string, payload: { label: string; geometry_type: 'text_span'; geometry: Record<string, unknown>; source?: 'human' }): Promise<AnnotationResponse> {
    const res = await fetch(`${PROJECTS_API_BASE}/hitl/tasks/${encodeURIComponent(taskId)}/annotations`, {
      method: 'POST', headers: this.getHeaders(true), body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to add HITL annotation' }));
      throw new Error(err.detail || 'Failed to add HITL annotation');
    }
    return await res.json();
  }

  async submitHumanReview(
    decisionId: string,
    annotations: unknown[],
    annotatorId: string
  ): Promise<HumanAnnotatorTaskResponse> {
    const url = `${API_BASE}/decisions/${encodeURIComponent(decisionId)}/submit-human-review`;
    let lastError = 'Failed to submit Human Annotator review';

    // Firestore can briefly return 503 while a connection is being refreshed.
    // Retry only transient server failures; validation/auth failures must be
    // returned immediately and must not duplicate a human revision.
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const res = await fetch(url, {
        method: 'POST',
        headers: this.getHeaders(true),
        body: JSON.stringify({ annotations, annotator_id: annotatorId }),
      });
      if (res.ok) return await res.json();

      const err = await res.json().catch(() => ({}));
      lastError = err.detail || err.error || lastError;
      const transient = res.status === 502 || res.status === 503 || res.status === 504;
      if (!transient || attempt === 2) break;
      await new Promise((resolve) => window.setTimeout(resolve, 500 * (attempt + 1)));
    }

    throw new Error(lastError);
  }

  async getProductionDashboard(projectId: string): Promise<ProductionDashboardResponse | null> {
    const cacheKey = `anonymous:${projectId}`;
    const cached = getCached(dashboardCache, cacheKey);
    if (cached !== undefined) return cached;
    try {
      const res = await fetch(`${REPORT_API_BASE}/projects/${encodeURIComponent(projectId)}/production-dashboard`, {
        headers: this.getHeaders(),
      });
      if (!res.ok) return null;
      return setCached(dashboardCache, cacheKey, await res.json());
    } catch (err) {
      console.error(`Error fetching production dashboard for ${projectId}:`, err);
      return null;
    }
  }

  async getQualityReport(projectId: string): Promise<QualityReportResponse | null> {
    const cacheKey = `anonymous:${projectId}`;
    const cached = getCached(qualityCache, cacheKey);
    if (cached !== undefined) return cached;
    try {
      const res = await fetch(`${REPORT_API_BASE}/projects/${encodeURIComponent(projectId)}/quality-report`, {
        headers: this.getHeaders(),
      });
      if (!res.ok) return null;
      return setCached(qualityCache, cacheKey, await res.json());
    } catch (err) {
      console.error(`Error fetching quality report for ${projectId}:`, err);
      return null;
    }
  }

  async getTextHITLDashboard(projectId: string): Promise<TextHITLDashboardResponse | null> {
    try {
      const res = await fetch(`${REPORT_API_BASE}/projects/${encodeURIComponent(projectId)}/hitl-metrics`, {
        headers: this.getHeaders(),
      });
      if (!res.ok) return null;
      return await res.json();
    } catch (err) {
      console.error(`Error fetching text HITL dashboard for ${projectId}:`, err);
      return null;
    }
  }

  async downloadProjectExport(projectId: string): Promise<{ blob: Blob; filename: string }> {
    const endpoint = `${API_BASE}/projects/${encodeURIComponent(projectId)}/export`;
    let res: Response | null = null;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      res = await fetch(endpoint, {
        headers: this.getHeaders(false),
        cache: 'no-store',
      });
      if (res.status !== 503 || attempt === 2) break;
      await new Promise((resolve) => window.setTimeout(resolve, 400 * (attempt + 1)));
    }
    if (!res) throw new Error('Project export failed');
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Project export failed' }));
      throw new Error(err.detail || 'Project export failed');
    }

    const disposition = res.headers.get('Content-Disposition') || '';
    const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || `project-${projectId}-export.zip`;
    return { blob: await res.blob(), filename };
  }

  async uploadAssets(projectId: string, files: File[]): Promise<any> {
    // Snapshot the browser-selected files before constructing multipart data.
    // A File handle can outlive the picker/drag-drop event, but the upload must
    // contain the bytes that were selected at this call site. This also makes
    // the payload validation below detect an empty or placeholder part before
    // it reaches the backend.
    const uploadFiles = await Promise.all(
      files.map(async (file) => {
        const bytes = await file.arrayBuffer();
        if (bytes.byteLength === 0 || bytes.byteLength !== file.size) {
          throw new Error(
            `Selected file "${file.name}" could not be read completely. Please select it again.`
          );
        }
        return new File([bytes], file.name, {
          type: file.type,
          lastModified: file.lastModified,
        });
      })
    );

    // Cloud Run limits a single HTTP request body. Keep multipart requests
    // comfortably below that limit so folders and multi-file selections do
    // not fail as one oversized request. This only changes transport; the
    // backend asset records and annotation workflows remain unchanged.
    const maxBatchBytes = 24 * 1024 * 1024;
    const batches: File[][] = [];
    let batch: File[] = [];
    let batchBytes = 0;
    for (const file of uploadFiles) {
      if (file.size > maxBatchBytes) {
        throw new Error(`File "${file.name}" is too large for direct upload. Use a smaller file or cloud storage.`);
      }
      if (batch.length > 0 && batchBytes + file.size > maxBatchBytes) {
        batches.push(batch);
        batch = [];
        batchBytes = 0;
      }
      batch.push(file);
      batchBytes += file.size;
    }
    if (batch.length > 0) batches.push(batch);

    const data: any[] = [];
    for (const batchFiles of batches) {
      const formData = new FormData();
      batchFiles.forEach((file) => formData.append('files', file, file.name));
      const payloadFiles = formData.getAll('files');
      const payloadMatchesSelection =
        payloadFiles.length === batchFiles.length &&
        payloadFiles.every((entry, index) =>
          entry instanceof File &&
          entry.name === batchFiles[index].name &&
          entry.size === batchFiles[index].size &&
          entry.type === batchFiles[index].type &&
          entry.size > 0
        );
      if (!payloadMatchesSelection) {
        throw new Error('Asset upload form data does not match the selected files. Please select them again.');
      }
      console.info('asset_upload_form_data', {
        projectId,
        fieldName: 'files',
        selectedFileCount: batchFiles.length,
        totalSelectedBytes: batchFiles.reduce((total, file) => total + file.size, 0),
      });

      const res = await fetch(`${PROJECTS_API_BASE}/projects/${encodeURIComponent(projectId)}/assets`, {
        method: 'POST',
        headers: this.getHeaders(false),
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Asset upload failed' }));
        throw new Error(err.detail || 'Asset upload failed');
      }
      const batchData = await res.json();
      if (Array.isArray(batchData)) data.push(...batchData);
    }
    this.invalidateProjectCache(projectId);
    return data;
  }

  async analyzeText(payload: TextAnalysisRequest): Promise<TextAnalysisResponse> {
    if (!payload.assetId) {
      throw new Error('Text analysis requires a persisted asset ID.');
    }
    const formData = new FormData();
    formData.append('project_id', payload.projectId);
    formData.append('asset_id', payload.assetId);
    formData.append('analysis_type', payload.analysisType);
    formData.append('assessment_name', payload.assessmentName || `${payload.analysisType} Analysis`);
    if (payload.text) {
      formData.append('text', payload.text);
    }
    if (payload.identificationName) {
      formData.append('identification_name', payload.identificationName);
    }
    if (payload.files && payload.files.length > 0) {
      payload.files.forEach((f) => formData.append('files', f));
    }

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 180_000);
    let res: Response;
    try {
      res = await fetch(`${PROJECTS_API_BASE}/text-annotation/analyze`, {
        method: 'POST',
        headers: this.getHeaders(false),
        body: formData,
        signal: controller.signal,
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new Error('Text AI annotation timed out after 3 minutes. Please check the backend logs and retry.');
      }
      throw error;
    } finally {
      window.clearTimeout(timeoutId);
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Text analysis failed' }));
      throw new Error(err.detail || 'Text analysis failed');
    }

    const result = await res.json();
    const cacheKey = `${payload.projectId}:${payload.assetId}`;
    this.textAnalysisCache.set(cacheKey, result);
    this.textAnalysesCache.delete(cacheKey);
    return result;
  }

  private textAnalysisCache = new Map<string, TextAnalysisResponse>();
  private textAnalysesCache = new Map<string, TextAnalysisResponse[]>();

  async getTextAnalysis(projectId: string, assetId: string): Promise<TextAnalysisResponse | null> {
    const cacheKey = `${projectId}:${assetId}`;
    if (this.textAnalysisCache.has(cacheKey)) {
      return this.textAnalysisCache.get(cacheKey)!;
    }
    const res = await fetch(`${PROJECTS_API_BASE}/projects/${encodeURIComponent(projectId)}/text-annotation/assets/${encodeURIComponent(assetId)}`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) return null;
    const data = await res.json();
    if (data) this.textAnalysisCache.set(cacheKey, data);
    return data;
  }

  async getTextAnalyses(projectId: string, assetId: string): Promise<TextAnalysisResponse[]> {
    const cacheKey = `${projectId}:${assetId}`;
    if (this.textAnalysesCache.has(cacheKey)) {
      return this.textAnalysesCache.get(cacheKey)!;
    }
    const res = await fetch(`${PROJECTS_API_BASE}/projects/${encodeURIComponent(projectId)}/text-annotation/assets/${encodeURIComponent(assetId)}/analyses`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) return [];
    const data = await res.json();
    const list = Array.isArray(data) ? data : [];
    if (list.length > 0) this.textAnalysesCache.set(cacheKey, list);
    return list;
  }

  async triggerAiAnnotation(projectId: string): Promise<any> {
    const res = await fetch(`${PROJECTS_API_BASE}/projects/${encodeURIComponent(projectId)}/ai-annotate`, {
      method: 'POST',
      headers: this.getHeaders(),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'AI Annotation trigger failed' }));
      throw new Error(err.detail || 'AI Annotation trigger failed');
    }

    const data = await res.json();
    this.invalidateProjectCache(projectId);
    return data;
  }
}

export const api = new ApiService();
