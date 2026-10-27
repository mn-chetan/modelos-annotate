import React, { useEffect, useMemo, useState } from 'react';
import { BarChart3, CheckCircle2, Clock, Copy, Cpu, Download, ExternalLink, Layers, Loader2, Mail, Menu, Play, Printer, RotateCcw, Share2, ShieldCheck, Target, TrendingUp, UserCheck, X } from 'lucide-react';
import { TechMahindraLogo } from '../TechMahindraLogo';
import { api, ProductionDashboardResponse, ProjectResponse, QualityReportResponse } from '../../services/api';

interface ProductionReportProps {
  projectId?: string;
  onToggleSidebar?: () => void;
  onNavigateToHitl?: () => void;
  onNavigateToQuality?: () => void;
  onNavigateToAiResults?: (projectId: string) => void;
  onNavigateToHumanAnnotator?: () => void;
  onToast?: (msg: string) => void;
  userEmail?: string;
  onLogout?: () => void;
}

type MetricValue = number | null | undefined;
const formatCount = (value: MetricValue) => (value == null ? 'N/A' : value.toLocaleString());
const formatPercent = (value: MetricValue) => (value == null ? 'N/A' : `${value.toFixed(1)}%`);
const formatDuration = (value: MetricValue) => value == null ? 'N/A' : `${value.toFixed(1)} min/task`;
const isTextProject = (project?: ProjectResponse) => {
  const projectType = String(project?.project_type || '').toLowerCase();
  const modality = String((project as ProjectResponse & { modality?: string })?.modality || '').toLowerCase();
  const taskType = String(project?.task_type || '').toUpperCase();
  return modality === 'text' || modality === 'document' || projectType.includes('text') || projectType.includes('document') || taskType.includes('TEXT') || taskType.includes('NER') || taskType.includes('SENTIMENT');
};

const MetricCard: React.FC<{ label: string; value: string; Icon: React.ElementType; tone?: 'blue' | 'amber' }> = ({ label, value, Icon, tone = 'blue' }) => (
  <div className="bg-white rounded-xl p-3.5 border border-slate-200/90 shadow-xs">
    <div className="flex items-center justify-between text-slate-500 text-xs mb-1"><span className="font-semibold text-slate-700">{label}</span><Icon className={`w-3.5 h-3.5 ${tone === 'amber' ? 'text-amber-600' : 'text-blue-600'}`} /></div>
    <div className="text-2xl font-black tracking-tight text-slate-900">{value}</div>
  </div>
);

type ThroughputPoint = { date: string; actual_images_per_hour?: number | null; target_images_per_hour?: number | null };
const ThroughputChart: React.FC<{ points: ThroughputPoint[]; target?: number | null }> = ({ points = [], target }) => {
  const width = 760;
  const height = 250;
  const left = 48;
  const right = 18;
  const top = 18;
  const bottom = 42;
  const values = points.flatMap((point) => [point.actual_images_per_hour || 0, point.target_images_per_hour || 0, target || 0]);
  const maxValue = Math.max(...values, 1);
  const chartMax = Math.ceil(maxValue * 1.1 / 100) * 100;
  const x = (index: number) => left + (points.length <= 1 ? 0 : index * ((width - left - right) / (points.length - 1)));
  const y = (value: number) => top + (height - top - bottom) * (1 - value / chartMax);
  const actual = points.map((point, index) => `${x(index)},${y(point.actual_images_per_hour || 0)}`).join(' ');
  const area = points.length > 0 ? `${left},${height - bottom} ${actual} ${x(points.length - 1)},${height - bottom}` : '';
  const yTicks = [0, 0.5, 1].map((ratio) => Math.round(chartMax * ratio));

  return <div className="overflow-x-auto"><svg viewBox={`0 0 ${width} ${height}`} className="min-w-[620px] w-full h-64" role="img" aria-label="Throughput velocity trend chart">
    <defs><linearGradient id="throughput-area" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#ef4444" stopOpacity="0.28" /><stop offset="100%" stopColor="#ef4444" stopOpacity="0.03" /></linearGradient></defs>
    {yTicks.map((tick) => <g key={tick}><line x1={left} x2={width - right} y1={y(tick)} y2={y(tick)} stroke="#e2e8f0" strokeDasharray="3 4" /><text x={left - 8} y={y(tick) + 4} textAnchor="end" fontSize="11" fill="#64748b">{tick.toLocaleString()}</text></g>)}
    {target != null && <><line x1={left} x2={width - right} y1={y(target)} y2={y(target)} stroke="#94a3b8" strokeDasharray="5 5" /><text x={width - right - 4} y={y(target) - 7} textAnchor="end" fontSize="10" fill="#64748b">Target: {target.toLocaleString()}</text></>}
    {points.length > 0 && <><polygon points={area} fill="url(#throughput-area)" /><polyline points={actual} fill="none" stroke="#ef4444" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />{points.map((point, index) => <g key={`${point.date}-${index}`}><circle cx={x(index)} cy={y(point.actual_images_per_hour || 0)} r="4" fill="white" stroke="#ef4444" strokeWidth="2" /><text x={x(index)} y={height - 16} textAnchor="middle" fontSize="10" fill="#64748b">{point.date}</text></g>)}</>}
  </svg></div>;
};

export const ProductionReportView: React.FC<ProductionReportProps> = ({ projectId, onToggleSidebar, onToast, onNavigateToAiResults, onNavigateToHumanAnnotator }) => {
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState(projectId || '');
  const [dashboardData, setDashboardData] = useState<ProductionDashboardResponse | null>(null);
  const [qualityData, setQualityData] = useState<QualityReportResponse | null>(null);
  const [backendStatus, setBackendStatus] = useState<'checking' | 'connected' | 'offline'>('checking');
  const [isLoading, setIsLoading] = useState(true);
  const [isExporting, setIsExporting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    Promise.all([api.checkHealth(), api.getProjects()]).then(([health, projectList]) => {
      if (!mounted) return;
      setBackendStatus(health.status ? 'connected' : 'offline');
      setProjects(projectList);
      setSelectedProjectId((current) => {
        const propMatch = projectId && projectList.some((p) => p.id === projectId) ? projectId : null;
        if (propMatch) return propMatch;
        const currentMatch = current && projectList.some((p) => p.id === current) ? current : null;
        if (currentMatch) return currentMatch;
        return projectList[0]?.id || '';
      });
    }).catch(() => mounted && setBackendStatus('offline'));
    return () => { mounted = false; };
  }, [projectId]);

  useEffect(() => {
    if (!selectedProjectId) { setIsLoading(false); return; }
    let mounted = true;
    setIsLoading(true);
    setLoadError(null);
    api.getProductionDashboard(selectedProjectId)
      .then((dashboard) => {
        if (!mounted) return;
        setDashboardData(dashboard);
        if (!dashboard) setLoadError('Failed to load backend metrics');
        setIsLoading(false);
        // Quality report is expensive and only supplies the audited accuracy
        // fallback. Load it after the dashboard is visible.
        api.getQualityReport(selectedProjectId).then((quality) => mounted && setQualityData(quality));
      }).catch((error) => {
        if (!mounted) return;
        console.error('Failed to load production report:', error);
        setDashboardData(null);
        setQualityData(null);
        setLoadError('Failed to load backend metrics');
        setIsLoading(false);
      });
    return () => { mounted = false; };
  }, [selectedProjectId]);

  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const textProject = isTextProject(selectedProject);
  const hasImageScope = !textProject;
  const snapshot = hasImageScope ? dashboardData?.kpiSnapshot : undefined;
  const population = snapshot?.population;
  const overview = snapshot?.production_overview;
  // Audited accuracy is authoritative when review decisions exist. For projects
  // that have AI annotations but no completed audit yet, use the persisted
  // model confidence so the dashboard still reports a useful percentage.
  const aiAnnotationAccuracy = hasImageScope
    ? qualityData?.ai_annotation_accuracy ?? snapshot?.annotation_confidence
    : undefined;

  const handleAiProceed = () => {
    if (!selectedProjectId || !hasImageScope) return;
    onToast?.('Opened existing AI proceed results.');
    onNavigateToAiResults?.(selectedProjectId);
  };

  const imageCards = [
    ['Images Processed', hasImageScope ? formatCount(snapshot?.images_processed ?? overview?.processed_images ?? population?.total_assets) : 'N/A', Layers],
    ['AI Annotated Images', hasImageScope ? formatCount(population?.completed_assets) : 'N/A', Cpu],
    ['HITL Images', hasImageScope ? formatCount(population?.human_review_assets) : 'N/A', UserCheck],
    ['HITL Rate', hasImageScope ? formatPercent(snapshot?.hitl_rate) : 'N/A', UserCheck],
    ['AI Annotation Accuracy', hasImageScope ? formatPercent(aiAnnotationAccuracy) : 'N/A', ShieldCheck],
  ] as const;
  const datasetCompletion = overview?.dataset_target_completion;
  const classBreakdown = overview?.class_breakdown || [];
  const throughputTrend = overview?.throughput_trend || [];
  const hitlCards = [
    ['HITL Images Count', hasImageScope ? formatCount(population?.human_review_assets) : 'N/A', UserCheck],
    ['Total HC', 'N/A', UserCheck],
    ['AHT', hasImageScope ? formatDuration(snapshot?.average_review_time) : 'N/A', Clock],
    ['AI Suggestion Acceptance', hasImageScope ? formatPercent(snapshot?.review_acceptance_rate) : 'N/A', CheckCircle2],
    ['Rework / Corrections', hasImageScope ? formatPercent(snapshot?.rework_rate) : 'N/A', RotateCcw],
  ] as const;
  const projectOverviewRows = useMemo(() => projects.filter((project) => !isTextProject(project)).map((project) => {
    const totalTasks = project.item_count ?? project.asset_count;
    const isSelected = project.id === selectedProjectId;
    const listedAnnotatedTasks = project.annotated_count ?? 0;
    const pendingTasks = isSelected
      ? population?.pending_final_assets ?? (totalTasks != null ? Math.max(0, totalTasks - listedAnnotatedTasks) : 0)
      : totalTasks != null
      ? project.pending_review_count ?? Math.max(0, totalTasks - listedAnnotatedTasks)
      : 0;
    const completionRate = isSelected
      ? snapshot?.completion_rate ?? (totalTasks ? (listedAnnotatedTasks / totalTasks) * 100 : 0)
      : totalTasks
      ? (listedAnnotatedTasks / totalTasks) * 100
      : 0;
    return {
      project,
      totalTasks,
      pendingTasks,
      completionRate,
      operators: project.allocated_operators ?? null,
      aht: isSelected ? snapshot?.average_review_time ?? project.average_review_time : project.average_review_time,
    };
      }), [projects, selectedProjectId, population?.pending_final_assets, snapshot?.average_review_time, snapshot?.completion_rate]);

  const handleExport = async () => {
    if (!selectedProjectId || isExporting) return;
    setIsExporting(true);
    try {
      const { blob, filename } = await api.downloadProjectExport(selectedProjectId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      onToast?.(`Export downloaded: ${filename}`);
    } catch (error) {
      console.error('Project export failed:', error);
      onToast?.(error instanceof Error ? error.message : 'Project export failed');
    } finally {
      setIsExporting(false);
    }
  };

  const [showMethodologyGuide, setShowMethodologyGuide] = useState(false);
  const [showShareModal, setShowShareModal] = useState(false);
  const [copiedLink, setCopiedLink] = useState(false);

  const copyToClipboard = async (text: string): Promise<boolean> => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return true;
      }
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      const success = document.execCommand('copy');
      textArea.remove();
      return success;
    } catch (err) {
      console.warn('Clipboard write fallback error:', err);
      return false;
    }
  };

  const handleShare = async () => {
    const shareUrl = window.location.href;
    setShowShareModal(true);
    setCopiedLink(true);
    const copied = await copyToClipboard(shareUrl);
    onToast?.(copied ? 'Report link copied to clipboard' : 'Share report options opened');
  };

  const handleCopyDirectLink = async () => {
    const shareUrl = window.location.href;
    const copied = await copyToClipboard(shareUrl);
    setCopiedLink(true);
    onToast?.(copied ? 'Report link copied to clipboard' : 'Link ready to copy');
    setTimeout(() => setCopiedLink(false), 2500);
  };

  const handleNativeDeviceShare = async () => {
    const shareUrl = window.location.href;
    const projName = projects.find((p) => p.id === selectedProjectId)?.name || 'Production Report';
    if (navigator.share) {
      try {
        await navigator.share({
          title: `ModelOS Annotate - ${projName}`,
          text: `View live AI & HITL production metrics for ${projName}:`,
          url: shareUrl,
        });
      } catch (err) {
        if ((err as Error)?.name !== 'AbortError') {
          console.warn('Native share error:', err);
        }
      }
    } else {
      await handleCopyDirectLink();
    }
  };

  return <div className="flex-1 flex flex-col min-w-0 bg-[#F6F2EA] text-slate-800 overflow-y-auto min-h-screen">
    <div className="sticky top-0 z-30 bg-white/95 backdrop-blur-md border-b border-[#E2DDD5] px-4 sm:px-8 py-2.5"><div className="max-w-[1600px] mx-auto flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-3">{onToggleSidebar && <button onClick={onToggleSidebar} className="p-1.5 text-slate-600 rounded-lg lg:hidden" aria-label="Open navigation sidebar"><Menu className="w-5 h-5" /></button>}<TechMahindraLogo size="sm" showSubbrand={true} className="border-r border-slate-200 pr-3.5" /><span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold border ${backendStatus === 'connected' ? 'bg-blue-50 text-blue-700 border-blue-200' : 'bg-amber-50 text-amber-700 border-amber-200'}`}><span className={`w-1.5 h-1.5 rounded-full ${backendStatus === 'connected' ? 'bg-blue-600' : 'bg-amber-500'}`} />Backend: {backendStatus === 'connected' ? 'Connected' : 'Syncing'}</span>{projects.length > 0 && <select value={selectedProjectId} onChange={(event) => { setSelectedProjectId(event.target.value); onToast?.(`Loaded metrics for ${projects.find((project) => project.id === event.target.value)?.name || event.target.value}`); }} className="bg-white text-slate-900 font-semibold px-2 py-1 rounded-md border border-slate-200 text-xs">{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select>}</div><div className="flex items-center gap-2"><button type="button" onClick={() => setShowMethodologyGuide(!showMethodologyGuide)} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-blue-50 border border-blue-200 text-xs font-bold text-blue-700 hover:bg-blue-100 transition cursor-pointer"><ShieldCheck className="w-4 h-4 text-blue-600" /> {showMethodologyGuide ? 'Hide Scoring Guide' : 'Scoring & Annotating Guide'}</button><button onClick={handleExport} disabled={!selectedProjectId || isExporting} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white border border-slate-200 text-xs font-bold text-slate-700 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50 transition cursor-pointer"><Download className="w-4 h-4 text-slate-500" /> {isExporting ? 'Exporting...' : 'Export Report'}</button><button onClick={handleShare} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 text-white text-xs font-bold hover:bg-slate-800 transition cursor-pointer shadow-xs"><Share2 className="w-4 h-4" /> Share Report</button></div></div></div>
    <div className="max-w-[1600px] w-full mx-auto px-4 sm:px-8 py-6 space-y-6">
      {/* Interactive Share Report Modal */}
      {showShareModal && (
        <div
          id="share-report-modal-overlay"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4 animate-in fade-in duration-150"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowShareModal(false);
          }}
        >
          <div
            id="share-report-modal"
            className="relative w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl border border-slate-200 space-y-5 animate-in zoom-in-95 duration-150"
          >
            {/* Header */}
            <div className="flex items-start justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-blue-50 text-blue-600 border border-blue-100">
                  <Share2 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-extrabold text-slate-900">Share Production Report</h3>
                  <p className="text-xs text-slate-500">Real-time AI metrics, automation rates &amp; HITL audit data.</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowShareModal(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition cursor-pointer"
                aria-label="Close share dialog"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Selected Project Card */}
            <div className="flex items-center justify-between px-3.5 py-2.5 rounded-xl bg-slate-50 border border-slate-200/90 text-xs">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-500">Project:</span>
                <span className="font-bold text-slate-900">
                  {projects.find((p) => p.id === selectedProjectId)?.name || selectedProjectId || 'Image Project'}
                </span>
              </div>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Live Report
              </span>
            </div>

            {/* Direct Link Box */}
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-slate-700">Direct Report Link</label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  readOnly
                  value={window.location.href}
                  className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-800 font-mono select-all focus:outline-hidden focus:ring-1 focus:ring-blue-500"
                  onClick={(e) => (e.target as HTMLInputElement).select()}
                />
                <button
                  type="button"
                  onClick={handleCopyDirectLink}
                  className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold transition shadow-xs cursor-pointer ${
                    copiedLink
                      ? 'bg-emerald-600 text-white hover:bg-emerald-700'
                      : 'bg-blue-600 text-white hover:bg-blue-700'
                  }`}
                >
                  {copiedLink ? <CheckCircle2 className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  <span>{copiedLink ? 'Copied! ✓' : 'Copy'}</span>
                </button>
              </div>
            </div>

            {/* Share Actions Grid */}
            <div className="space-y-2 pt-1">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Quick Share Options</span>
              <div className="grid grid-cols-2 gap-2.5">
                {/* Email Option */}
                <a
                  href={`mailto:?subject=${encodeURIComponent(
                    `ModelOS Annotate - Production Report (${projects.find((p) => p.id === selectedProjectId)?.name || 'Project'})`
                  )}&body=${encodeURIComponent(
                    `Hello,\n\nPlease review the live ModelOS Annotate Production Report (AI + HITL) here:\n${window.location.href}\n\nBest regards,\nModelOS Annotate Team`
                  )}`}
                  className="flex items-center gap-2.5 p-3 rounded-xl border border-slate-200 hover:border-blue-400 hover:bg-blue-50/40 text-slate-700 transition cursor-pointer text-xs font-semibold"
                >
                  <div className="p-2 rounded-lg bg-blue-100 text-blue-700">
                    <Mail className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="font-bold text-slate-900">Email Link</div>
                    <div className="text-[10px] text-slate-500">Send report via email</div>
                  </div>
                </a>

                {/* Print / Save PDF Option */}
                <button
                  type="button"
                  onClick={() => {
                    setShowShareModal(false);
                    setTimeout(() => window.print(), 200);
                  }}
                  className="flex items-center gap-2.5 p-3 rounded-xl border border-slate-200 hover:border-indigo-400 hover:bg-indigo-50/40 text-slate-700 transition cursor-pointer text-xs font-semibold text-left"
                >
                  <div className="p-2 rounded-lg bg-indigo-100 text-indigo-700">
                    <Printer className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="font-bold text-slate-900">Print / PDF</div>
                    <div className="text-[10px] text-slate-500">Save as PDF document</div>
                  </div>
                </button>

                {/* Open in New Window Option */}
                <button
                  type="button"
                  onClick={() => window.open(window.location.href, '_blank')}
                  className="flex items-center gap-2.5 p-3 rounded-xl border border-slate-200 hover:border-slate-400 hover:bg-slate-50 text-slate-700 transition cursor-pointer text-xs font-semibold text-left"
                >
                  <div className="p-2 rounded-lg bg-slate-100 text-slate-700">
                    <ExternalLink className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="font-bold text-slate-900">Open in Tab</div>
                    <div className="text-[10px] text-slate-500">Standalone fullscreen</div>
                  </div>
                </button>

                {/* Device Apps / Web Share */}
                <button
                  type="button"
                  onClick={handleNativeDeviceShare}
                  className="flex items-center gap-2.5 p-3 rounded-xl border border-slate-200 hover:border-emerald-400 hover:bg-emerald-50/40 text-slate-700 transition cursor-pointer text-xs font-semibold text-left"
                >
                  <div className="p-2 rounded-lg bg-emerald-100 text-emerald-700">
                    <Share2 className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="font-bold text-slate-900">Device Share</div>
                    <div className="text-[10px] text-slate-500">Teams, Slack, Apps</div>
                  </div>
                </button>
              </div>
            </div>

            {/* Footer */}
            <div className="pt-3 flex items-center justify-between border-t border-slate-100">
              <span className="text-[11px] text-slate-400">All metrics secured by Google Cloud IAP</span>
              <button
                type="button"
                onClick={() => setShowShareModal(false)}
                className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition cursor-pointer shadow-xs"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {showMethodologyGuide && (
        <section id="scoring-methodology-guide" className="rounded-2xl border border-blue-200 bg-gradient-to-r from-blue-50/90 via-indigo-50/50 to-white p-5 space-y-4 shadow-xs animate-in fade-in duration-200">
          <div className="flex items-center justify-between border-b border-blue-100 pb-3">
            <div className="flex items-center gap-2.5">
              <div className="p-1.5 rounded-lg bg-blue-600 text-white">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-sm font-black text-slate-900 tracking-tight">AI Confidence Scoring & HITL Annotating Methodology</h2>
                <p className="text-xs text-slate-600">Standard operating procedure for automated certification and human review thresholds.</p>
              </div>
            </div>
            <button type="button" onClick={() => setShowMethodologyGuide(false)} className="text-xs text-slate-500 hover:text-slate-800 font-semibold">✕ Close</button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-3.5 space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                <span className="text-xs font-extrabold text-emerald-900">≥ 95% Confidence (Auto-Certified)</span>
              </div>
              <p className="text-[11px] text-emerald-800 leading-relaxed">High-precision detection validated across the multi-model ensemble (YOLO26 + DINO + SAM2.1). Automatically passed to final production dataset without mandatory human rework.</p>
            </div>
            <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-3.5 space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
                <span className="text-xs font-extrabold text-amber-900">70% - 94% Confidence (HITL Supervised)</span>
              </div>
              <p className="text-[11px] text-amber-800 leading-relaxed">Ambiguous or partially occluded detections. Dispatched to the Human Annotator workbench for verification, bounding box coordinate adjustment, or reclassification.</p>
            </div>
            <div className="rounded-xl border border-rose-200 bg-rose-50/60 p-3.5 space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-500" />
                <span className="text-xs font-extrabold text-rose-900">&lt; 70% Confidence (Mandatory Audit)</span>
              </div>
              <p className="text-[11px] text-rose-800 leading-relaxed">Low-confidence or background noise proposals. Requires mandatory Quality Audit rework or removal before any final export authorization.</p>
            </div>
          </div>
          <div className="rounded-xl border border-blue-100 bg-white/80 p-3 text-xs text-slate-700 flex flex-wrap items-center justify-between gap-2">
            <span><strong>Annotating Pipeline:</strong> 1. Multi-Model AI Inference → 2. Human Verification / Box Nudging → 3. Quality Agent Ontology Validation → 4. Production Dataset Export (COCO/YOLO/Pascal).</span>
            <span className="text-[11px] text-blue-700 font-bold">Standard SLA Target: 95%+ Quality Level</span>
          </div>
        </section>
      )}
      {isLoading && <div className="flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-xl p-3 text-xs text-blue-700 font-semibold"><Loader2 className="w-4 h-4 animate-spin" /> Fetching real project metrics...</div>}{loadError && <div className="bg-rose-50 border border-rose-200 rounded-xl p-3 text-xs text-rose-700 font-semibold">{loadError}. Metrics without backend data are shown as N/A.</div>}
      <section id="production-report" className="space-y-4"><div className="flex flex-wrap items-end justify-between gap-4 border-b border-[#E2DDD5] pb-4"><div><span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-red-100 text-red-800 border border-red-200">Dashboard</span><h1 className="text-2xl sm:text-3xl font-black text-slate-900 tracking-tight mt-1">Image Production Report (AI + HITL)</h1><p className="text-xs sm:text-sm text-slate-600 mt-0.5">Real project production, automation, and human-review metrics.</p></div></div><div className="grid grid-cols-1 gap-5"><div className="rounded-2xl border border-blue-100 bg-blue-50/30 p-4 sm:p-5 space-y-4"><div><h2 className="text-base font-extrabold text-slate-900">Image Scorecard</h2><p className="text-[11px] text-slate-500 mt-1">{hasImageScope ? 'Metrics for the selected image project.' : 'No image assets in the selected project.'}</p></div><div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">{imageCards.map(([label, value, Icon]) => <MetricCard key={label} label={label} value={value} Icon={Icon} />)}</div></div></div></section>
      <section id="ai-executive-insights-panel" className="bg-white rounded-xl p-5 border border-slate-200/90 shadow-xs space-y-5"><div className="flex items-center gap-2.5 border-b border-slate-100 pb-3"><div className="w-1.5 h-5 bg-blue-600 rounded-full" /><div><h2 className="text-base font-extrabold text-slate-900">AI Executive Insights Panel</h2><p className="text-xs text-slate-500">AI-side production insights from persisted image-annotation analytics.</p></div></div><div className="grid grid-cols-2 md:grid-cols-5 gap-3">{[['Images Processed', formatCount(snapshot?.images_processed ?? overview?.processed_images)], ['AI Annotated Images', formatCount(population?.ai_annotated_assets)], ['HITL Rate', formatPercent(snapshot?.hitl_rate)], ['AI Annotation Accuracy', formatPercent(aiAnnotationAccuracy)], ['AI Automation Rate', formatPercent(snapshot?.automation_rate)]].map(([label, value]) => <div key={label} className="rounded-lg bg-slate-50 border border-slate-200 p-3"><div className="text-[11px] font-semibold text-slate-500">{label}</div><div className="mt-1 text-lg font-black text-slate-900">{value}</div></div>)}</div><div className="space-y-3"><div className="flex items-center gap-2"><Target className="w-4 h-4 text-blue-600" /><h3 className="text-sm font-bold text-slate-900">Dataset Target Completion Progress</h3></div>{!hasImageScope || !datasetCompletion ? <div className="rounded-lg border border-dashed border-slate-200 p-5 text-center text-xs italic text-slate-500">No production completion analytics available.</div> : <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-4"><div className="flex items-center justify-between text-xs"><span className="font-semibold text-slate-600">Overall completion</span><span className="font-black text-slate-900">{formatPercent(datasetCompletion.completion_percentage)}</span></div><div className="mt-2 h-3 overflow-hidden rounded-full bg-slate-200"><div className="h-full rounded-full bg-blue-600" style={{ width: `${Math.min(100, Math.max(0, datasetCompletion.completion_percentage || 0))}%` }} /></div><div className="mt-3 grid grid-cols-3 gap-2 text-[11px]"><div><span className="mr-1 inline-block h-2 w-2 rounded-full bg-emerald-500" />Approved <strong>{formatPercent(datasetCompletion.approved_percentage)}</strong></div><div><span className="mr-1 inline-block h-2 w-2 rounded-full bg-amber-500" />Reworked <strong>{formatPercent(datasetCompletion.reworked_percentage)}</strong></div><div><span className="mr-1 inline-block h-2 w-2 rounded-full bg-rose-500" />Rejected <strong>{formatPercent(datasetCompletion.rejected_percentage)}</strong></div></div></div>}</div><div className="space-y-3"><div className="flex items-center gap-2"><BarChart3 className="w-4 h-4 text-blue-600" /><h3 className="text-sm font-bold text-slate-900">Annotation Class Completion Breakdown</h3></div>{!hasImageScope || classBreakdown.length === 0 ? <div className="rounded-lg border border-dashed border-slate-200 p-5 text-center text-xs italic text-slate-500">No class-level production data available.</div> : <div className="grid grid-cols-1 md:grid-cols-2 gap-3">{classBreakdown.map((item) => <div key={item.label} className="rounded-lg border border-slate-200 p-3"><div className="flex items-start justify-between gap-3 text-xs"><span className="font-semibold text-slate-700">{item.label}</span><span className="shrink-0 font-black text-slate-900">{formatPercent(item.approved_percentage)}</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-blue-500" style={{ width: `${Math.min(100, Math.max(0, item.approved_percentage || 0))}%` }} /></div><div className="mt-1 text-[11px] text-slate-500">{formatCount(item.image_count)} images Â· {formatCount(item.annotation_count)} annotations</div></div>)}</div>}</div><div className="space-y-3"><div className="flex items-center justify-between gap-2"><div className="flex items-center gap-2"><TrendingUp className="w-4 h-4 text-blue-600" /><h3 className="text-sm font-bold text-slate-900">Throughput Velocity Trend (Images / Hour)</h3></div>{overview?.sla_target != null && <span className="text-[11px] font-semibold text-slate-500">Target: {overview.sla_target.toLocaleString()} / hr</span>}</div>{!hasImageScope || throughputTrend.length === 0 ? <div className="rounded-lg border border-dashed border-slate-200 p-5 text-center text-xs italic text-slate-500">No throughput history available from completed processing events.</div> : <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-4"><ThroughputChart points={throughputTrend} target={overview?.sla_target} /></div>}<div className="flex justify-end pt-1"><button type="button" onClick={handleAiProceed} disabled={!hasImageScope || !selectedProjectId} className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"><Play className="h-3.5 w-3.5" />AI Proceed Results</button></div></div></section>
      <section id="hitl-executive-insights-panel" className="bg-white rounded-xl p-5 border border-slate-200/90 shadow-xs space-y-5"><div className="flex items-center gap-2.5 border-b border-slate-100 pb-3"><div className="w-1.5 h-5 bg-amber-500 rounded-full" /><div><h2 className="text-base font-extrabold text-slate-900">HITL Executive Insights Panel</h2><p className="text-xs text-slate-500">Human-in-the-loop review outcomes from persisted image-annotation analytics.</p></div></div><div><h3 className="text-sm font-bold text-slate-900 mb-3">HITL Scorecard</h3><div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">{hitlCards.map(([label, value, Icon]) => <MetricCard key={label} label={label} value={value} Icon={Icon} tone="amber" />)}</div></div><div className="space-y-3"><h3 className="text-sm font-bold text-slate-900">Project Level Overview</h3><div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200"><tr><th className="py-2.5 px-4">Project Name</th><th className="py-2.5 px-4">Allocated Operators</th><th className="py-2.5 px-4">Total Images/Tasks</th><th className="py-2.5 px-4">Pending</th><th className="py-2.5 px-4">AHT</th><th className="py-2.5 px-4">Completion Rate</th></tr></thead><tbody className="divide-y divide-slate-100">{projectOverviewRows.length === 0 ? <tr><td colSpan={6} className="py-6 px-4 text-center text-slate-500 italic">No project data available.</td></tr> : projectOverviewRows.map(({ project, totalTasks, pendingTasks, completionRate, operators, aht }) => <tr key={project.id} className="text-slate-700"><td className="py-3 px-4 font-semibold text-slate-900">{project.name}</td><td className="py-3 px-4">{formatCount(operators)}</td><td className="py-3 px-4">{formatCount(totalTasks)}</td><td className="py-3 px-4">{formatCount(pendingTasks)}</td><td className="py-3 px-4">{formatDuration(aht)}</td><td className="py-3 px-4">{formatPercent(completionRate)}</td></tr>)}</tbody></table></div></div><div className="flex justify-end pt-1"><button type="button" onClick={onNavigateToHumanAnnotator} className="inline-flex items-center gap-1.5 rounded-lg bg-amber-500 px-4 py-2 text-xs font-bold text-white shadow-sm transition hover:bg-amber-600"><UserCheck className="h-3.5 w-3.5" />Human Annotator</button></div></section>
      <div className="flex flex-wrap gap-3 text-xs"><span className="inline-flex items-center gap-1.5 px-3 py-2 text-slate-500">Source: persisted project analytics</span></div>
    </div>
  </div>;
};








