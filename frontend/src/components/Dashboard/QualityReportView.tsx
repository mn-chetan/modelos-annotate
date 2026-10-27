import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  Award,
  AlertTriangle,
  CheckCircle2,
  Download,
  TrendingUp,
  Loader2,
} from 'lucide-react';
import { TechMahindraLogo } from '../TechMahindraLogo';
import {
  api,
  ProjectResponse,
  QualityReportResponse,
  ProductionDashboardResponse,
} from '../../services/api';

interface QualityReportProps {
  onToggleSidebar?: () => void;
  onNavigateToProduction?: () => void;
  onNavigateToHitl?: () => void;
  onToast?: (msg: string) => void;
  selectedProjectId?: string;
  onSelectProject?: (id: string) => void;
}

export const QualityReportView: React.FC<QualityReportProps> = ({
  onToggleSidebar,
  onNavigateToProduction,
  onNavigateToHitl,
  onToast,
  selectedProjectId,
  onSelectProject,
}) => {
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string>(selectedProjectId || '');
  const [qualityData, setQualityData] = useState<QualityReportResponse | null>(null);
  const [dashboardData, setDashboardData] = useState<ProductionDashboardResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Load project list on mount
  useEffect(() => {
    async function loadProjects() {
      const projList = await api.getProjects();
      setProjects(projList);
      if (!activeProjectId && projList.length > 0) {
        const savedId = localStorage.getItem('modelos_selected_project_id');
        const defaultId = projList.find((p) => p.id === savedId)?.id || projList[0].id;
        setActiveProjectId(defaultId);
      }
    }
    loadProjects();
  }, []);

  // Update active project if prop changes
  useEffect(() => {
    if (selectedProjectId && selectedProjectId !== activeProjectId) {
      setActiveProjectId(selectedProjectId);
    }
  }, [selectedProjectId]);

  // Fetch quality report data when active project changes
  useEffect(() => {
    if (!activeProjectId) {
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setLoadError(null);

    Promise.all([
      api.getQualityReport(activeProjectId),
      api.getProductionDashboard(activeProjectId),
    ])
      .then(([qData, dData]) => {
        setQualityData(qData);
        setDashboardData(dData);
        setIsLoading(false);
      })
      .catch((err) => {
        console.error('Error fetching quality report:', err);
        setLoadError(err.message || 'Failed to load quality report data');
        setIsLoading(false);
      });
  }, [activeProjectId]);

  const activeProject = projects.find((p) => p.id === activeProjectId);
  const kpi = dashboardData?.kpiSnapshot;

  // 1. Audit Pass Rate
  const rawAuditPassRate =
    qualityData?.audit_pass_rate != null
      ? qualityData.audit_pass_rate
      : qualityData?.qc_pass_rate != null
      ? qualityData.qc_pass_rate
      : kpi?.approval_rate != null
      ? kpi.approval_rate
      : kpi?.quality_yield != null
      ? kpi.quality_yield
      : null;
  const auditPassRateStr = rawAuditPassRate != null ? `${rawAuditPassRate.toFixed(1)}%` : 'N/A';

  // 2. Mean IoU
  const rawMeanIoU =
    qualityData?.mean_iou != null
      ? qualityData.mean_iou
      : kpi?.annotation_confidence != null
      ? kpi.annotation_confidence / 100
      : null;
  const meanIoUStr = rawMeanIoU != null ? rawMeanIoU.toFixed(3) : 'N/A';

  // 3. Defect Leakage
  const rawDefectLeakage =
    qualityData?.defect_leakage != null
      ? qualityData.defect_leakage
      : qualityData?.defect_rate != null
      ? qualityData.defect_rate
      : kpi?.defect_rate != null
      ? kpi.defect_rate
      : null;
  const defectLeakageStr = rawDefectLeakage != null ? `${rawDefectLeakage.toFixed(2)}%` : 'N/A';

  // 4. Inter-Annotator Agreement
  const rawAgreement =
    qualityData?.inter_annotator_agreement != null
      ? qualityData.inter_annotator_agreement
      : kpi?.reviewer_agreement != null
      ? kpi.reviewer_agreement
      : null;
  const agreementStr =
    rawAgreement != null
      ? rawAgreement > 1.0
        ? `${(rawAgreement / 100).toFixed(2)} Cohen's Kappa`
        : `${rawAgreement.toFixed(2)} Cohen's Kappa`
      : 'N/A';

  // IoU Distribution
  const dist = qualityData?.iou_distribution;
  const bucket1 = dist?.gt_0_95;
  const bucket2 = dist?.['0_85_0_95'];
  const bucket3 = dist?.['0_70_0_85'];
  const bucket4 = dist?.lt_0_70;

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-[#F6F2EA] text-slate-800 overflow-y-auto min-h-screen">
      {/* Top Banner */}
      <div className="sticky top-0 z-30 bg-white/95 backdrop-blur-md border-b border-[#E2DDD5] px-4 sm:px-8 py-2.5">
        <div className="max-w-[1600px] mx-auto flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <TechMahindraLogo
              size="sm"
              showSubbrand={true}
              className="border-r border-[#E2DDD5] pr-3.5"
            />

            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-purple-50 text-purple-700 border border-purple-200">
                <ShieldCheck className="w-3 h-3 text-purple-600" />
                Quality Assurance & Audit
              </span>
              {projects.length > 0 && (
                <div className="flex items-center gap-1">
                  <span>Dataset:</span>
                  <select
                    aria-label="Select project dataset"
                    value={activeProjectId}
                    onChange={(e) => {
                      const id = e.target.value;
                      setActiveProjectId(id);
                      if (onSelectProject) onSelectProject(id);
                      localStorage.setItem('modelos_selected_project_id', id);
                    }}
                    className="text-xs font-bold bg-white border border-[#E2DDD5] rounded-lg px-2 py-0.5 text-slate-800 cursor-pointer"
                  >
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => onToast?.('Exporting QA & Consensus Audit Certificate...')}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold shadow-xs transition cursor-pointer"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export Certificate</span>
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-[1600px] w-full mx-auto px-4 sm:px-8 py-5 space-y-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">
            Quality Assurance & Ground-Truth Audit Report
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">
            Statistical distribution of IoU consensus, confusion matrix scores, and compliance certification metrics.
          </p>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 text-purple-600 animate-spin mr-2" />
            <span className="text-sm font-semibold text-slate-600">Loading Quality Assurance Data...</span>
          </div>
        ) : loadError ? (
          <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center text-red-700">
            <AlertTriangle className="w-8 h-8 text-red-500 mx-auto mb-2" />
            <p className="font-bold">Failed to load Quality data</p>
            <p className="text-xs text-red-600 mt-1">{loadError}</p>
          </div>
        ) : (
          <>
            {/* Core QA KPI Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
                <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
                  <span className="font-semibold text-slate-700">Audit Pass Rate</span>
                  <Award className="w-4 h-4 text-emerald-600" />
                </div>
                <div className="text-2xl font-black text-slate-900">{auditPassRateStr}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">certified against QA audit policy</div>
                <div className="mt-2 text-[10px] text-emerald-600 font-bold">
                  {rawAuditPassRate != null
                    ? rawAuditPassRate >= 98.0
                      ? 'Surpassed 98.0% SLA Threshold'
                      : 'Quality audit active'
                    : 'N/A'}
                </div>
              </div>

              <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
                <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
                  <span className="font-semibold text-slate-700">Mean IoU (Ground Truth)</span>
                  <ShieldCheck className="w-4 h-4 text-purple-600" />
                </div>
                <div className="text-2xl font-black text-slate-900">{meanIoUStr}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">across verified bounding & masks</div>
                <div className="mt-2 text-[10px] text-emerald-600 font-bold flex items-center gap-1">
                  <TrendingUp className="w-3 h-3" />
                  {rawMeanIoU != null ? 'Ground-truth audit score' : 'N/A'}
                </div>
              </div>

              <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
                <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
                  <span className="font-semibold text-slate-700">Defect Leakage</span>
                  <AlertTriangle className="w-4 h-4 text-rose-500" />
                </div>
                <div className="text-2xl font-black text-slate-900">{defectLeakageStr}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">post-review QA audit sampling</div>
                <div className="mt-2 text-[10px] text-emerald-600 font-bold">
                  {rawDefectLeakage != null
                    ? rawDefectLeakage <= 1.5
                      ? 'Well below 1.5% max ceiling'
                      : 'Monitored defect rate'
                    : 'N/A'}
                </div>
              </div>

              <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
                <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
                  <span className="font-semibold text-slate-700">Inter-Annotator Agreement</span>
                  <CheckCircle2 className="w-4 h-4 text-blue-600" />
                </div>
                <div className="text-2xl font-black text-slate-900">{agreementStr}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">cross-validation redundancy tests</div>
                <div className="mt-2 text-[10px] text-blue-600 font-bold">
                  {rawAgreement != null ? 'Consensus agreement score' : 'N/A'}
                </div>
              </div>
            </div>

            {/* Quality Audit Breakdown */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-xs p-5">
              <h3 className="text-sm font-bold text-slate-900 mb-3">
                Model IoU Threshold Acceptance Distribution
              </h3>

              {!dist ? (
                <div className="py-6 text-center text-xs text-slate-500 italic">
                  No QA/ground-truth distribution data available for this project.
                </div>
              ) : (
                <div className="space-y-3">
                  <div>
                    <div className="flex justify-between text-xs mb-1 font-medium">
                      <span>IoU &gt; 0.95 (Pristine Pixel Boundary Match)</span>
                      <span className="font-mono text-slate-600">
                        {bucket1 ? `${bucket1.percentage.toFixed(1)}% (${bucket1.count.toLocaleString()} annotations)` : 'N/A'}
                      </span>
                    </div>
                    <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-emerald-600 rounded-full"
                        style={{ width: `${bucket1 ? bucket1.percentage : 0}%` }}
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-xs mb-1 font-medium">
                      <span>IoU 0.85 - 0.95 (Certified Production Grade)</span>
                      <span className="font-mono text-slate-600">
                        {bucket2 ? `${bucket2.percentage.toFixed(1)}% (${bucket2.count.toLocaleString()} annotations)` : 'N/A'}
                      </span>
                    </div>
                    <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-600 rounded-full"
                        style={{ width: `${bucket2 ? bucket2.percentage : 0}%` }}
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-xs mb-1 font-medium">
                      <span>IoU 0.70 - 0.85 (Human Adjusted in HITL)</span>
                      <span className="font-mono text-slate-600">
                        {bucket3 ? `${bucket3.percentage.toFixed(1)}% (${bucket3.count.toLocaleString()} annotations)` : 'N/A'}
                      </span>
                    </div>
                    <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-amber-500 rounded-full"
                        style={{ width: `${bucket3 ? bucket3.percentage : 0}%` }}
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-xs mb-1 font-medium">
                      <span>IoU &lt; 0.70 (Flagged & Discarded)</span>
                      <span className="font-mono text-slate-600">
                        {bucket4 ? `${bucket4.percentage.toFixed(1)}% (${bucket4.count.toLocaleString()} annotations)` : 'N/A'}
                      </span>
                    </div>
                    <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-rose-600 rounded-full"
                        style={{ width: `${bucket4 ? bucket4.percentage : 0}%` }}
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

