import React, { useEffect, useState } from 'react';
import { CheckCircle2, Clock, Download, Loader2, Menu, RotateCcw, UserCheck } from 'lucide-react';
import { TechMahindraLogo } from '../TechMahindraLogo';
import { api, ProductionDashboardResponse, ProjectResponse } from '../../services/api';

interface HitlReportProps {
  onToggleSidebar?: () => void;
  onNavigateToProduction?: () => void;
  onNavigateToQuality?: () => void;
  onToast?: (msg: string) => void;
  selectedProjectId?: string;
  onSelectProject?: (id: string) => void;
}

const count = (value: number | null | undefined) => value == null ? 'N/A' : value.toLocaleString();
const percent = (value: number | null | undefined) => value == null ? 'N/A' : `${value.toFixed(1)}%`;
const duration = (value: number | null | undefined) => value == null ? 'N/A' : `${value < 5 ? (value * 60).toFixed(1) : value.toFixed(1)} sec`;

export const HitlReportView: React.FC<HitlReportProps> = ({ onToggleSidebar, onToast, selectedProjectId, onSelectProject }) => {
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [activeProjectId, setActiveProjectId] = useState(selectedProjectId || '');
  const [dashboardData, setDashboardData] = useState<ProductionDashboardResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    api.getProjects().then((list) => {
      if (!mounted) return;
      setProjects(list);
      if (!activeProjectId && list.length > 0) setActiveProjectId(list[0].id);
    }).catch((error) => mounted && setLoadError(error.message || 'Failed to load HITL projects'));
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    if (!activeProjectId) { setIsLoading(false); return; }
    let mounted = true;
    setIsLoading(true);
    api.getProductionDashboard(activeProjectId).then((data) => {
      if (!mounted) return;
      setDashboardData(data);
      setLoadError(data ? null : 'Failed to load HITL data');
    }).catch((error) => mounted && setLoadError(error.message || 'Failed to load HITL data')).finally(() => mounted && setIsLoading(false));
    return () => { mounted = false; };
  }, [activeProjectId]);

  const kpi = dashboardData?.kpiSnapshot;
  const pop = kpi?.population;
  const hitlImages = pop?.human_review_assets;
  const rework = pop?.reworked_assets;
  const project = projects.find((item) => item.id === activeProjectId);
  const scorecard = [
    ['HITL Images Count', count(hitlImages), UserCheck],
    ['Total HC', 'N/A', UserCheck],
    ['AHT (Avg Handling Time)', duration(kpi?.average_review_time), Clock],
    ['AI Suggestion Acceptance', percent(kpi?.review_acceptance_rate), CheckCircle2],
    ['Rework / Corrections', count(rework), RotateCcw],
  ] as const;

  return <div className="flex-1 flex flex-col min-w-0 bg-[#F6F2EA] text-slate-800 overflow-y-auto min-h-screen">
    <div className="sticky top-0 z-30 bg-white/95 backdrop-blur-md border-b border-[#E2DDD5] px-4 sm:px-8 py-2.5"><div className="max-w-[1600px] mx-auto flex items-center justify-between gap-3"><div className="flex items-center gap-3">{onToggleSidebar && <button onClick={onToggleSidebar} className="p-1.5 text-slate-600 rounded-lg lg:hidden" aria-label="Open navigation sidebar"><Menu className="w-5 h-5" /></button>}<TechMahindraLogo size="sm" showSubbrand={true} className="border-r border-[#E2DDD5] pr-3.5" />{projects.length > 0 && <select aria-label="Select project dataset" value={activeProjectId} onChange={(event) => { setActiveProjectId(event.target.value); onSelectProject?.(event.target.value); }} className="text-xs font-bold bg-white border border-[#E2DDD5] rounded-lg px-2 py-1 text-slate-800">{projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>}</div><button onClick={() => onToast?.('Exporting HITL Audit Log CSV...')} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-bold"><Download className="w-3.5 h-3.5" /> Export HITL Log</button></div></div>
    <div className="max-w-[1600px] w-full mx-auto px-4 sm:px-8 py-5 space-y-6"><div><h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">Human-in-the-Loop (HITL) Execution Report</h1><p className="text-xs sm:text-sm text-slate-500 mt-1">{project?.name || 'Project'} human review metrics.</p></div>
      {isLoading ? <div className="flex items-center justify-center py-16"><Loader2 className="w-8 h-8 text-blue-600 animate-spin mr-2" /><span className="text-sm font-semibold text-slate-600">Loading HITL data...</span></div> : loadError ? <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center text-red-700">{loadError}</div> : <section id="hitl-executive-insights-panel" className="bg-white rounded-xl p-5 border border-slate-200/90 shadow-xs space-y-4"><div className="flex items-center gap-2.5 border-b border-slate-100 pb-3"><div className="w-1.5 h-5 bg-amber-500 rounded-full" /><div><h2 className="text-base font-extrabold text-slate-900">HITL Executive Insights Panel</h2><p className="text-xs text-slate-500">Human-in-the-loop review outcomes from persisted review analytics.</p></div></div><h3 className="text-sm font-bold text-slate-900">HITL Scorecard</h3><div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">{scorecard.map(([label, value, Icon]) => <div key={label} className="p-3.5 rounded-xl bg-slate-50/80 border border-slate-200/80"><div className="flex items-center justify-between text-xs text-slate-500 mb-1"><span className="font-semibold text-slate-700">{label}</span><Icon className="w-3.5 h-3.5 text-amber-600" /></div><div className="text-xl font-extrabold text-slate-900">{value}</div></div>)}</div><p className="text-[11px] text-slate-500">Total HC is N/A because the current production dashboard contract does not expose a persisted human-contributor count.</p></section>}
    </div>
  </div>;
};
