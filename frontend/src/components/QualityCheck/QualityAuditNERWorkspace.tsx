import React, { useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, ChevronRight, FileText, Menu, Save, ShieldCheck, Sparkles } from 'lucide-react';
import { api, AnnotationResponse, QualityAuditRecommendation, QualityAuditTaskResponse } from '../../services/api';

interface Props { projectId?: string; mode?: 'NER' | 'Sentiment' | 'Classification'; onToggleSidebar?: () => void; onNavigateToProjects?: () => void; onToast: (msg: string) => void; }

export const QualityAuditNERWorkspace: React.FC<Props> = ({ projectId, mode = 'NER', onToggleSidebar, onToast }) => {
  const [queue, setQueue] = useState<QualityAuditTaskResponse[]>([]);
  const [task, setTask] = useState<QualityAuditTaskResponse | null>(null);
  const [annotations, setAnnotations] = useState<AnnotationResponse[]>([]);
  const [agent, setAgent] = useState<QualityAuditRecommendation | null>(null);
  const [comment, setComment] = useState('');
  const [decision, setDecision] = useState<'PASS' | 'FAIL'>('PASS');
  const [loading, setLoading] = useState(true);
  const [agentLoading, setAgentLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    if (!projectId) { setQueue([]); setTask(null); setLoading(false); return; }
    setLoading(true);
    try {
      const tasks = await api.getQualityAuditorTasks(projectId);
      setQueue(tasks);
      if (tasks[0]) { const detail = await api.getQualityAuditTask(tasks[0].asset_id || tasks[0].id); setTask(detail); setAnnotations(detail.annotations || []); }
      else setTask(null);
    } catch (error) { setTask(null); setQueue([]); onToast(error instanceof Error ? error.message : 'Text quality queue unavailable'); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, [projectId]);

  const runAgent = async () => {
    if (!task) return;
    setAgentLoading(true); setAgent(null);
    try { setAgent(await api.getQualityAuditRecommendation(task.id)); }
    catch (error) { onToast(error instanceof Error ? error.message : 'Quality agent unavailable'); }
    finally { setAgentLoading(false); }
  };
  const submit = async () => {
    if (!task) return;
    setSaving(true);
    try {
      await api.saveQualityAudit(task.id, { decision, comments: comment, checklist: { mode, agent_recommendation: agent?.recommendation || null, agent_run_id: agent?.agent_run_id || null } });
      onToast(decision === 'PASS' ? 'Text quality audit approved' : 'Text quality audit sent for rework');
      await load();
    } catch (error) { onToast(error instanceof Error ? error.message : 'Text audit could not be saved'); }
    finally { setSaving(false); }
  };

  const text = String((task as any)?.text || (task as any)?.content || (task as any)?.raw_text || (task as any)?.document_text || '');
  if (loading) return <div className="flex-1 p-8 text-slate-600">Loading text Quality Audit queue…</div>;
  if (!projectId) return <Empty message="Select a project to load text Quality Audit tasks." />;
  if (!task) return <Empty message="No text Quality Audit tasks are available. Human or sampled AI work will appear here after entering QC." />;

  return <div className="flex-1 overflow-y-auto bg-[var(--color-bg-canvas,#F6F2EA)] text-slate-800"><main className="p-4 md:p-6 lg:p-7 space-y-5 max-w-[1850px] w-full mx-auto">
    <div className="flex items-center gap-3">{onToggleSidebar && <button onClick={onToggleSidebar} className="p-1.5 lg:hidden"><Menu className="h-5 w-5" /></button>}<div><h1 className="text-2xl font-bold text-slate-900">{mode} Annotation Quality Audit</h1><p className="text-xs text-slate-600">Review persisted text annotations with an agent-assisted, evidence-based audit.</p></div></div>
    <section className="rounded-xl border border-[#E2DDD5] bg-white p-4 flex flex-wrap justify-between gap-4"><div><span className="text-xs font-semibold text-[#247153]">{task.audit_source || `${mode} audit`}</span><div className="text-sm font-mono font-bold mt-1">{task.filename || task.id}</div></div><div className="flex gap-6 text-xs"><div><span className="block text-slate-400">Queue</span><b>{queue.length} pending</b></div><div><span className="block text-slate-400">Modality</span><b>Text</b></div><div><span className="block text-slate-400">Annotations</span><b>{annotations.length}</b></div></div></section>
    <div className="grid grid-cols-1 xl:grid-cols-7 gap-5"><section className="xl:col-span-4 rounded-xl border border-[#E2DDD5] bg-white p-5"><h2 className="font-bold flex items-center gap-2 pb-3 border-b"><FileText className="h-5 w-5 text-rose-600" />Text Content</h2><div className="mt-4 min-h-[300px] whitespace-pre-wrap leading-8 text-sm">{text || <span className="text-slate-500">Text content is not included in this task payload.</span>}</div><div className="mt-4 border-t pt-3"><h3 className="text-xs font-bold mb-2">Persisted annotations</h3><div className="flex flex-wrap gap-2">{annotations.map((a, i) => <span key={a.id || i} className="rounded-md border border-blue-200 bg-blue-50 px-2 py-1 text-xs"><b>{a.label || 'unlabelled'}</b>{a.text_span?.text ? `: ${a.text_span.text}` : ''}</span>)}</div></div></section>
      <aside className="xl:col-span-3 space-y-5"><section className="rounded-xl border border-[#E2DDD5] bg-white p-5 space-y-4"><div className="flex items-center justify-between"><h2 className="font-bold flex gap-2 items-center"><Sparkles className="h-5 w-5 text-blue-600" />Agent review</h2><button onClick={runAgent} disabled={agentLoading} className="rounded-lg bg-blue-600 text-white px-3 py-2 text-xs font-semibold disabled:opacity-50">{agentLoading ? 'Analyzing…' : 'Run agent'}</button></div>{agent ? <div className="rounded-lg bg-blue-50 border border-blue-100 p-3 text-xs space-y-2"><b>{agent.recommendation || 'HUMAN_REVIEW'}</b><p>{agent.summary || 'No summary returned.'}</p>{agent.categories?.map((c, i) => <div key={`${c.name}-${i}`}><b>{c.name}</b>: {c.evidence || 'No evidence returned.'}</div>)}<span className="text-slate-500">Confidence: {agent.confidence == null ? '—' : `${(Number(agent.confidence) * 100).toFixed(0)}%`}</span></div> : <p className="text-xs text-slate-500">Run the agent to receive task-specific evidence and categories.</p>}</section><section className="rounded-xl border border-[#E2DDD5] bg-white p-5 space-y-4"><h2 className="font-bold flex gap-2 items-center"><ShieldCheck className="h-5 w-5 text-blue-600" />Human audit decision</h2><div className="flex gap-2"><button onClick={() => setDecision('PASS')} className={`flex-1 p-2 rounded-lg border text-xs font-semibold ${decision === 'PASS' ? 'bg-emerald-50 border-emerald-500 text-emerald-700' : ''}`}><CheckCircle2 className="inline h-4 w-4 mr-1" />No issue</button><button onClick={() => setDecision('FAIL')} className={`flex-1 p-2 rounded-lg border text-xs font-semibold ${decision === 'FAIL' ? 'bg-rose-50 border-rose-500 text-rose-700' : ''}`}><AlertCircle className="inline h-4 w-4 mr-1" />Issues found</button></div><textarea value={comment} onChange={e => setComment(e.target.value.slice(0, 1000))} rows={4} placeholder="Explain the human audit decision…" className="w-full rounded-lg border p-3 text-xs" /><div className="grid grid-cols-2 gap-2"><button onClick={() => onToast('Draft kept until submitted')} className="rounded-lg border py-2 text-xs font-semibold"><Save className="inline h-4 w-4 mr-1" />Save draft</button><button disabled={saving || (decision === 'FAIL' && !comment.trim())} onClick={() => void submit()} className="rounded-lg bg-blue-600 text-white py-2 text-xs font-semibold disabled:opacity-50">{saving ? 'Saving…' : 'Submit audit'}<ChevronRight className="inline h-4 w-4 ml-1" /></button></div></section></aside>
    </div></main></div>;
};

const Empty = ({ message }: { message: string }) => <div className="flex-1 grid place-items-center p-8 text-center text-slate-600"><div className="rounded-xl border border-dashed bg-white p-8 max-w-lg"><ShieldCheck className="mx-auto mb-3 h-8 w-8 text-blue-600" /><p>{message}</p></div></div>;
