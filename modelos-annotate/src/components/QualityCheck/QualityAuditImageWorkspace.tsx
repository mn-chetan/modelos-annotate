import React, { useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, ChevronLeft, ChevronRight, Menu, Save, ShieldCheck, Sparkles } from 'lucide-react';
import { api, AnnotationResponse, QualityAuditRecommendation, QualityAuditTaskResponse } from '../../services/api';

interface Props {
  projectId?: string;
  auditTitle?: string;
  onToggleSidebar?: () => void;
  onNavigateToProjects?: () => void;
  onToast: (msg: string) => void;
}

type AuditDecision = 'PASS' | 'FAIL';

const toPercent = (value: unknown, total: number) => {
  const n = Number(value || 0);
  if (!Number.isFinite(n)) return 0;
  // Annotation coordinates can be normalized (0..1), percentages (0..100),
  // or source pixels. Human HITL edits are persisted as percentages.
  const percentage = n <= 1 ? n * 100 : n <= 100 ? n : total > 0 ? (n / total) * 100 : 0;
  return Math.max(0, Math.min(100, percentage));
};

export const QualityAuditImageWorkspace: React.FC<Props> = ({ projectId, auditTitle = 'Quality Audit', onToggleSidebar, onToast }) => {
  const [queue, setQueue] = useState<QualityAuditTaskResponse[]>([]);
  const [currentTaskIndex, setCurrentTaskIndex] = useState(0);
  const [task, setTask] = useState<QualityAuditTaskResponse | null>(null);
  const [annotations, setAnnotations] = useState<AnnotationResponse[]>([]);
  const [assetPreviewUrl, setAssetPreviewUrl] = useState<string | null>(null);
  const [recommendation, setRecommendation] = useState<QualityAuditRecommendation | null>(null);
  const [decision, setDecision] = useState<AuditDecision>('PASS');
  const [comment, setComment] = useState('');
  const [loading, setLoading] = useState(true);
  const [agentLoading, setAgentLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const selectTaskByIndex = async (index: number, queueList = queue) => {
    if (index < 0 || index >= queueList.length) return;
    setCurrentTaskIndex(index);
    const target = queueList[index];
    setAssetPreviewUrl(null);
    setRecommendation(null);
    setComment('');
    setDecision('PASS');
    try {
      const detail = await api.getQualityAuditTask(target.asset_id || target.id);
      setTask(detail);
      setAnnotations(detail.annotations || []);
      if (detail.image_url || detail.preview_url) {
        setAssetPreviewUrl(detail.preview_url || detail.image_url || null);
      } else {
        setAssetPreviewUrl(api.getAssetImageUrl(detail.id));
        try { setAssetPreviewUrl(await api.getAssetImageBlobUrl(detail.id)); }
        catch { setAssetPreviewUrl(api.getAssetImageUrl(detail.id)); }
      }
    } catch (err) {
      console.error('Failed to load task detail:', err);
    }
  };

  const loadQueue = async () => {
    if (!projectId) { setQueue([]); setTask(null); setLoading(false); return; }
    setAssetPreviewUrl(null);
    setLoading(true);
    try {
      const tasks = await api.getQualityAuditorTasks(projectId);
      setQueue(tasks);
      if (tasks.length > 0) {
        const nextIdx = Math.min(currentTaskIndex, tasks.length - 1);
        await selectTaskByIndex(nextIdx, tasks);
      } else {
        setTask(null);
      }
    } catch (error) {
      setQueue([]); setTask(null); onToast(error instanceof Error ? error.message : 'Quality queue unavailable');
    } finally { setLoading(false); }
  };

  useEffect(() => { void loadQueue(); }, [projectId]);

  const runAgent = async () => {
    if (!task) return;
    setAgentLoading(true); setRecommendation(null);
    try { setRecommendation(await api.getQualityAuditRecommendation(task.id)); }
    catch (error) { onToast(error instanceof Error ? error.message : 'Quality agent unavailable'); }
    finally { setAgentLoading(false); }
  };

  const submit = async (nextDecision: AuditDecision) => {
    if (!task) return;
    setSaving(true); setDecision(nextDecision);
    try {
      await api.saveQualityAudit(task.id, {
        decision: nextDecision,
        comments: comment,
        checklist: {
          selected_categories: recommendation?.categories || [],
          agent_recommendation: recommendation?.recommendation || null,
          agent_run_id: recommendation?.agent_run_id || null,
        },
      });
      onToast(nextDecision === 'PASS' ? 'Quality audit approved' : 'Quality audit sent for rework');
      await loadQueue();
    } catch (error) { onToast(error instanceof Error ? error.message : 'Quality audit could not be saved'); }
    finally { setSaving(false); }
  };

  const imageUrl = assetPreviewUrl || task?.preview_url || task?.image_url;
  const isPii = auditTitle.toLowerCase().includes('pii');
  const labels = useMemo(() => Array.from(new Set(annotations.map((a) => a.label).filter(Boolean))), [annotations]);

  if (loading) return <div className="flex-1 p-8 text-slate-600">Loading Quality Audit queue…</div>;
  if (!projectId) return <EmptyState message="Select a project to load Quality Audit tasks." />;
  if (!task) return <EmptyState message="No Quality Audit tasks are available. Tasks appear here after human or sampled AI work enters QC." />;

  return (
    <div id="quality-audit-image-workspace" className="flex-1 overflow-y-auto bg-[var(--color-bg-canvas,#F6F2EA)] text-slate-800">
      <main className="p-4 md:p-6 lg:p-7 space-y-5 max-w-[1850px] w-full mx-auto">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            {onToggleSidebar && <button onClick={onToggleSidebar} className="p-1.5 lg:hidden" aria-label="Toggle navigation"><Menu className="h-5 w-5" /></button>}
            <div>
              <h1 className="text-2xl font-bold text-slate-900">{auditTitle}</h1>
              <p className="text-xs text-slate-600">Review persisted annotations and use the Quality Agent as an automated second reviewer.</p>
            </div>
          </div>
          {/* Previous / Next Image Navigation Controls */}
          <div className="flex items-center gap-2 bg-white px-3 py-1.5 rounded-xl border border-[#E2DDD5] shadow-2xs">
            <button
              type="button"
              onClick={() => selectTaskByIndex(currentTaskIndex - 1)}
              disabled={currentTaskIndex <= 0}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 bg-white text-xs font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition"
              title="Previous Image (Move backward in queue)"
            >
              <ChevronLeft className="h-4 w-4" /> Prev Image
            </button>
            <span className="text-xs font-bold text-slate-800 px-2 min-w-[70px] text-center">
              {currentTaskIndex + 1} / {queue.length}
            </span>
            <button
              type="button"
              onClick={() => selectTaskByIndex(currentTaskIndex + 1)}
              disabled={currentTaskIndex >= queue.length - 1}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 bg-white text-xs font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition"
              title="Next Image (Move forward in queue)"
            >
              Next Image <ChevronRight className="h-4 w-4" />
            </button>
            {queue.length > 1 && (
              <select
                value={currentTaskIndex}
                onChange={(e) => selectTaskByIndex(Number(e.target.value))}
                className="text-xs font-semibold rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-slate-800 cursor-pointer ml-1"
                title="Jump directly to any image in queue"
              >
                {queue.map((t, i) => (
                  <option key={t.id || i} value={i}>
                    {i + 1}. {t.filename || t.id.slice(0, 16)}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>

        <section className="rounded-xl border border-[#E2DDD5] bg-white p-4 flex flex-wrap justify-between gap-4">
          <div><span className="text-xs font-semibold text-[#247153]">{task.audit_source || 'QC task'}</span><div className="text-sm font-mono font-bold mt-1">{task.filename || task.id}</div></div>
          <div className="flex gap-6 text-xs"><div><span className="block text-slate-400">Queue Position</span><b>{currentTaskIndex + 1} of {queue.length}</b></div><div><span className="block text-slate-400">Modality</span><b>{task.content_type || 'image'}</b></div><div><span className="block text-slate-400">Resolution</span><b>{task.width && task.height ? `${task.width} × ${task.height}` : '—'}</b></div></div>
        </section>

        <div className="grid grid-cols-1 xl:grid-cols-7 gap-5">
          <section className="xl:col-span-4 rounded-xl border border-[#E2DDD5] bg-white p-4">
            <div className="flex justify-between items-center mb-3"><h2 className="font-bold">Annotation View (Human)</h2><span className="text-xs text-slate-500">{annotations.length} annotations</span></div>
            {imageUrl ? <div className="relative overflow-auto rounded-lg bg-slate-100"><div className="relative w-fit max-w-full mx-auto"><img src={imageUrl} alt={task.filename || 'quality audit asset'} className="block max-h-[620px] max-w-full object-contain" />{annotations.map((a, i) => <div key={`overlay-${a.id || i}`} className={`absolute border-2 ${isPii ? 'border-amber-500 bg-black/40' : 'border-blue-500 bg-blue-500/10'}`} style={{ left: `${toPercent(a.x, task.width || 1)}%`, top: `${toPercent(a.y, task.height || 1)}%`, width: `${toPercent(a.w, task.width || 1)}%`, height: `${toPercent(a.h, task.height || 1)}%` }}><span className="absolute -top-5 left-0 whitespace-nowrap bg-slate-900 px-1 text-[10px] text-white">{a.label || `annotation ${i + 1}`}</span></div>)}</div></div> : <div className="h-64 grid place-items-center border border-dashed rounded-lg text-slate-500">Asset preview is unavailable</div>}
            <div className="mt-4 max-h-64 overflow-auto divide-y"><div className="grid grid-cols-4 text-xs font-semibold py-2"><span>#</span><span>Label</span><span>Confidence</span><span>Source</span></div>{annotations.map((a, i) => <div key={a.id || i} className="grid grid-cols-4 text-xs py-2"><span>{i + 1}</span><span>{a.label || 'unlabelled'}</span><span>{a.confidence == null ? '—' : `${(Number(a.confidence) * 100).toFixed(0)}%`}</span><span>{a.source || 'unknown'}</span></div>)}</div>
          </section>

          <aside className="xl:col-span-3 space-y-5">
            <section className="rounded-xl border border-[#E2DDD5] bg-white p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="font-bold flex items-center gap-2"><Sparkles className="h-5 w-5 text-blue-600" />Quality Agent Review</h2>
                <button onClick={runAgent} disabled={agentLoading} className="rounded-lg bg-blue-600 text-white px-3 py-2 text-xs font-semibold disabled:opacity-50 hover:bg-blue-700 cursor-pointer">{agentLoading ? 'Analyzing…' : 'Run Quality Agent'}</button>
              </div>

              {/* Quality Agent Purpose & Guidance Card */}
              <div className="rounded-xl border border-blue-100 bg-gradient-to-r from-blue-50/70 to-indigo-50/40 p-3.5 text-xs text-slate-700 space-y-2">
                <div className="flex items-center gap-2 font-bold text-blue-900">
                  <ShieldCheck className="h-4 w-4 text-blue-600" />
                  <span>Agent Purpose: Automated 2nd Reviewer</span>
                </div>
                <p className="text-[11px] text-slate-600 leading-relaxed">
                  The Quality Agent independently audits this image against the project ontology, checks for hallucinated or missing objects, and validates boundary precision to assist your final human decision.
                </p>
                <div className="grid grid-cols-3 gap-2 pt-1 text-[10px]">
                  <div className="rounded bg-white/80 p-1.5 border border-blue-100 text-center font-semibold text-blue-800">1. Ontology Check</div>
                  <div className="rounded bg-white/80 p-1.5 border border-blue-100 text-center font-semibold text-blue-800">2. IoU Fit Audit</div>
                  <div className="rounded bg-white/80 p-1.5 border border-blue-100 text-center font-semibold text-blue-800">3. Pass/Fail Advice</div>
                </div>
              </div>

              {recommendation ? (
                <div className="rounded-lg bg-blue-50 border border-blue-100 p-3 text-xs space-y-2">
                  <div className="font-semibold text-slate-900 flex items-center justify-between">
                    <span>Recommendation: <strong>{recommendation.recommendation || 'Human review'}</strong></span>
                    <span className="text-[11px] text-blue-700 font-mono">Confidence: {recommendation.confidence == null ? '—' : `${(Number(recommendation.confidence) * 100).toFixed(0)}%`}</span>
                  </div>
                  <p>{recommendation.summary || 'No summary returned.'}</p>
                  {recommendation.categories?.map((c, i) => (
                    <div key={`${c.name}-${i}`}><b>{c.name}</b>{c.severity ? ` · ${c.severity}` : ''}: {c.evidence || 'Agent supplied no evidence.'}</div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-500 italic">Click "Run Quality Agent" above to generate automated multi-point verification evidence for this task.</p>
              )}
            </section>

            <section className="rounded-xl border border-[#E2DDD5] bg-white p-5 space-y-4">
              <h2 className="font-bold flex items-center gap-2"><ShieldCheck className="h-5 w-5 text-blue-600" />Human audit decision</h2>
              <div className="flex gap-2">
                <button onClick={() => setDecision('PASS')} className={`flex-1 p-2 rounded-lg border text-xs font-semibold cursor-pointer transition ${decision === 'PASS' ? 'bg-emerald-50 border-emerald-500 text-emerald-700 shadow-2xs' : 'bg-white hover:bg-slate-50'}`}><CheckCircle2 className="inline h-4 w-4 mr-1" />No issue (Pass)</button>
                <button onClick={() => setDecision('FAIL')} className={`flex-1 p-2 rounded-lg border text-xs font-semibold cursor-pointer transition ${decision === 'FAIL' ? 'bg-rose-50 border-rose-500 text-rose-700 shadow-2xs' : 'bg-white hover:bg-slate-50'}`}><AlertCircle className="inline h-4 w-4 mr-1" />Issues found (Rework)</button>
              </div>
              <p className="text-xs text-slate-500">Observed labels: {labels.length ? labels.join(', ') : 'none'}</p>
              <textarea value={comment} onChange={(e) => setComment(e.target.value.slice(0, 1000))} rows={4} placeholder="Explain the human audit decision (required if issues found)…" className="w-full rounded-lg border border-slate-200 p-3 text-xs bg-white focus:border-blue-500 outline-none" />
              <div className="grid grid-cols-2 gap-2">
                <button onClick={() => onToast('Draft is kept locally until submitted')} className="rounded-lg border border-slate-200 bg-white hover:bg-slate-50 py-2 text-xs font-semibold cursor-pointer transition"><Save className="inline h-4 w-4 mr-1" />Save draft</button>
                <button disabled={saving || (decision === 'FAIL' && !comment.trim())} onClick={() => void submit(decision)} className="rounded-lg bg-blue-600 hover:bg-blue-700 text-white py-2 text-xs font-semibold disabled:opacity-50 cursor-pointer transition">{saving ? 'Saving…' : 'Submit audit'}<ChevronRight className="inline h-4 w-4 ml-1" /></button>
              </div>
            </section>
          </aside>
        </div>
      </main>
    </div>
  );
};

const EmptyState = ({ message }: { message: string }) => <div className="flex-1 grid place-items-center p-8 text-center text-slate-600"><div className="rounded-xl border border-dashed bg-white p-8 max-w-lg"><ShieldCheck className="mx-auto mb-3 h-8 w-8 text-blue-600" /><p>{message}</p></div></div>;
