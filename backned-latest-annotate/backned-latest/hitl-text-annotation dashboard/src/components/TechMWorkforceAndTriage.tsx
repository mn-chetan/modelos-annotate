import React, { useState } from 'react';
import {
  Users,
  Search,
  AlertTriangle,
  Clock,
  CheckCircle2,
  ShieldAlert,
  ArrowRight,
  Activity,
  Award,
  Download,
  Users2,
  FileSpreadsheet,
  Zap
} from 'lucide-react';
import { AnnotatorRecord } from '../types';

interface TechMWorkforceAndTriageProps {
  annotators: AnnotatorRecord[];
  disputedCount: number;
  lowLatencyCount: number;
  activeLearningCount: number;
  onSelectAnnotator: (ann: AnnotatorRecord) => void;
  onOpenDisputeResolution: () => void;
  onOpenLeadAudit: () => void;
  onOpenActiveLearningExport: () => void;
}

export const TechMWorkforceAndTriage: React.FC<TechMWorkforceAndTriageProps> = ({
  annotators,
  disputedCount,
  lowLatencyCount,
  activeLearningCount,
  onSelectAnnotator,
  onOpenDisputeResolution,
  onOpenLeadAudit,
  onOpenActiveLearningExport
}) => {
  const activeQueueCount = [disputedCount, lowLatencyCount, activeLearningCount].filter((count) => count > 0).length;
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState<'all' | 'flagged' | 'star'>('all');

  const filteredAnnotators = annotators.filter((ann) => {
    const matches =
      ann.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      ann.role.toLowerCase().includes(searchTerm.toLowerCase());
    if (!matches) return false;
    if (filterStatus === 'flagged') return ann.status === 'flagged';
    if (filterStatus === 'star') return ann.status === 'star';
    return true;
  });

  return (
    <section className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch">
      
      {/* Left Column (8 cols): Annotator Performance & Safeguard Audit */}
      <div className="lg:col-span-8 bg-white border border-[#E5DFD3] rounded-lg p-5 flex flex-col justify-between shadow-xs">
        <div>
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-[#E5DFD3] mb-4 gap-2">
            <div className="flex items-center gap-2">
              <Users className="w-5 h-5 text-[#E31837]" />
              <div>
                <h3 className="text-sm font-semibold text-[#29251D]">
                  Annotator Performance & Safeguard Audit
                </h3>
                <p className="text-xs text-[#4D4D4F]">
                  Workforce throughput, review latency, AI override rate, and automated rubber-stamping safeguards
                </p>
              </div>
            </div>

            {/* Search & Filter */}
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-[#4D4D4F]" />
                <input
                  type="text"
                  placeholder="Search reviewer..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="bg-[#F6F2EA] border border-[#E5DFD3] rounded-md pl-8 pr-3 py-1 text-xs text-[#29251D] placeholder-[#4D4D4F] focus:outline-none w-40"
                />
              </div>

              <div className="flex items-center p-0.5 bg-[#F6F2EA] border border-[#E5DFD3] rounded-md text-xs">
                <button
                  type="button"
                  onClick={() => setFilterStatus('all')}
                  className={`px-2 py-0.5 rounded transition-colors ${
                    filterStatus === 'all'
                      ? 'bg-white text-[#29251D] font-semibold shadow-xs'
                      : 'text-[#4D4D4F] hover:text-[#29251D]'
                  }`}
                >
                  All
                </button>
                <button
                  type="button"
                  onClick={() => setFilterStatus('flagged')}
                  className={`px-2 py-0.5 rounded transition-colors flex items-center gap-1 ${
                    filterStatus === 'flagged'
                      ? 'bg-[#9C1936] text-white font-semibold shadow-xs'
                      : 'text-[#9C1936] hover:bg-[#F8B4A3]/30'
                  }`}
                >
                  <AlertTriangle className="w-3 h-3" />
                  <span>Alerts</span>
                </button>
              </div>
            </div>
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-[#E5DFD3] bg-[#F6F2EA] text-[#4D4D4F] font-medium">
                  <th className="py-2.5 px-3">Annotator Name</th>
                  <th className="py-2.5 px-3">Assigned / Done</th>
                  <th className="py-2.5 px-3 text-right">Avg Time / Doc</th>
                  <th className="py-2.5 px-3 text-right">AI Edit Rate</th>
                  <th className="py-2.5 px-3 text-right">Audit Pass Rate</th>
                  <th className="py-2.5 px-3">Status & Flags</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E5DFD3]">
                {filteredAnnotators.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-12 px-3 text-center text-xs text-[#4D4D4F]">
                      {annotators.length === 0
                        ? 'No human review activity for this project.'
                        : 'No reviewers match the current search or filter.'}
                    </td>
                  </tr>
                ) : filteredAnnotators.map((ann) => {
                  const isFlagged = ann.status === 'flagged';
                  const isStar = ann.status === 'star';
                  const completionPct = Math.round((ann.completedDocs / ann.assignedDocs) * 100);

                  return (
                    <tr
                      key={ann.id}
                      onClick={() => onSelectAnnotator(ann)}
                      className={`transition-colors cursor-pointer ${
                        isFlagged
                          ? 'bg-[#9C1936]/5 hover:bg-[#9C1936]/10'
                          : 'hover:bg-[#F6F2EA]/60'
                      }`}
                    >
                      {/* Name */}
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-2.5">
                          <div
                            className={`w-7 h-7 rounded-full flex items-center justify-center font-bold text-[11px] ${
                              isFlagged
                                ? 'bg-[#9C1936] text-white'
                                : isStar
                                ? 'bg-[#29251D] text-white'
                                : 'bg-[#E5DFD3] text-[#29251D]'
                            }`}
                          >
                            {ann.avatarSeed}
                          </div>
                          <div>
                            <div className="font-semibold text-[#29251D] flex items-center gap-1">
                              <span>{ann.name}</span>
                              {isStar && (
                                <span title="Top Quality Reviewer">
                                  <Award className="w-3.5 h-3.5 text-[#8A5200]" />
                                </span>
                              )}
                            </div>
                            <div className="text-[11px] text-[#4D4D4F]">{ann.role}</div>
                          </div>
                        </div>
                      </td>

                      {/* Assigned / Completed */}
                      <td className="py-3 px-3 font-mono">
                        <div>
                          <span className="font-bold text-[#29251D]">{ann.completedDocs.toLocaleString()}</span>
                          <span className="text-[#4D4D4F]"> / {ann.assignedDocs.toLocaleString()}</span>
                        </div>
                        <div className="w-20 bg-[#E5DFD3] h-1.5 rounded-full mt-1 overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              completionPct >= 95 ? 'bg-[#247153]' : 'bg-[#29251D]'
                            }`}
                            style={{ width: `${completionPct}%` }}
                          />
                        </div>
                      </td>

                      {/* Avg Time / Doc (Outlier in red) */}
                      <td className="py-3 px-3 text-right font-mono font-bold tabular-nums">
                        <div className={ann.avgTimeSec < 20 ? 'text-[#9C1936] flex items-center justify-end gap-1 font-extrabold' : 'text-[#29251D]'}>
                          {ann.avgTimeSec < 20 && <Clock className="w-3.5 h-3.5 text-[#9C1936]" />}
                          <span>{ann.avgTimeSec}s</span>
                        </div>
                        <div className="text-[10px] text-[#4D4D4F] font-normal">
                          {ann.avgTimeSec < 20 ? 'Sub-latency alert' : 'Normal'}
                        </div>
                      </td>

                      {/* AI Edit Rate */}
                      <td className="py-3 px-3 text-right font-mono font-bold tabular-nums">
                        <span className={ann.aiEditRate < 2.0 ? 'text-[#9C1936]' : 'text-[#247153]'}>
                          {ann.aiEditRate.toFixed(1)}%
                        </span>
                      </td>

                      {/* Audit Pass Rate */}
                      <td className="py-3 px-3 text-right font-mono font-bold tabular-nums">
                        <span className={ann.auditPassRate < 80 ? 'text-[#9C1936]' : 'text-[#247153]'}>
                          {ann.auditPassRate.toFixed(1)}%
                        </span>
                      </td>

                      {/* Status / Flags */}
                      <td className="py-3 px-3">
                        {isFlagged ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-xs bg-[#9C1936]/10 text-[#9C1936] border border-[#9C1936]/30 text-[11px] font-semibold">
                            <ShieldAlert className="w-3 h-3 shrink-0" />
                            <span>Rubber-Stamping Alert</span>
                          </span>
                        ) : ann.status === 'in_calibration' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-xs bg-[#8A5200]/10 text-[#8A5200] border border-[#8A5200]/30 text-[11px]">
                            <Activity className="w-3 h-3 shrink-0" />
                            <span>In Calibration</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-xs bg-[#247153]/10 text-[#247153] border border-[#247153]/30 text-[11px]">
                            <CheckCircle2 className="w-3 h-3 shrink-0" />
                            <span>Verified</span>
                          </span>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="py-3 px-3 text-right">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectAnnotator(ann);
                          }}
                          className="px-2.5 py-1 text-[11px] bg-[#F6F2EA] hover:bg-[#E5DFD3] text-[#29251D] border border-[#E5DFD3] rounded transition-colors font-medium whitespace-nowrap"
                        >
                          Audit Drilldown
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Table Footer */}
        <div className="pt-3 border-t border-[#E5DFD3] flex items-center justify-between text-xs text-[#4D4D4F] mt-2">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-[#9C1936]" />
            <span>Safeguard alert triggered when review velocity &lt; 15s and edit rate &lt; 3%</span>
          </span>
          <span className="font-mono text-[#29251D] font-medium">{annotators.length} Reviewers</span>
        </div>
      </div>

      {/* Right Column (4 cols): Actionable HITL Triage Drawer */}
      <div className="lg:col-span-4 bg-white border border-[#E5DFD3] rounded-lg p-5 flex flex-col justify-between shadow-xs">
        <div>
          {/* Header */}
          <div className="flex items-center justify-between pb-4 border-b border-[#E5DFD3] mb-4">
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-5 h-5 text-[#E31837]" />
              <h3 className="text-sm font-semibold text-[#29251D]">
                Actionable HITL Triage Drawer
              </h3>
            </div>
            <span className="text-[11px] font-mono font-semibold text-[#E31837] bg-[#F8B4A3]/20 px-2 py-0.5 rounded border border-[#F8B4A3]">
              {activeQueueCount} Queues Active
            </span>
          </div>

          {/* 3 Actionable Alert Blocks */}
          <div className="space-y-3.5">
            
            {/* Block 1: Disputed Items */}
            <div className="p-3.5 bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-[#29251D]">
                    <Users2 className="w-3.5 h-3.5 text-[#E31837]" />
                    <span>Disputed Items</span>
                  </div>
                  <span className="text-xs font-mono font-bold text-[#E31837] tabular-nums">
                    {disputedCount} Items
                  </span>
                </div>
                <p className="text-xs text-[#4D4D4F] leading-relaxed mb-3">
                  Dual blind annotators disagreed on entity boundaries or class assignment.
                </p>
              </div>

              <button
                type="button"
                onClick={onOpenDisputeResolution}
                disabled={disputedCount === 0}
                className="w-full py-2 px-3 text-xs bg-[#E31837] hover:bg-[#5F0229] text-white font-semibold rounded-md flex items-center justify-center gap-2 transition-colors shadow-xs disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <span>Open Dispute Resolution</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Block 2: Low-Latency Submissions */}
            <div className="p-3.5 bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-[#29251D]">
                    <Clock className="w-3.5 h-3.5 text-[#9C1936]" />
                    <span>Low-Latency Submissions</span>
                  </div>
                  <span className="text-xs font-mono font-bold text-[#9C1936] tabular-nums">
                    {lowLatencyCount} Items
                  </span>
                </div>
                <p className="text-xs text-[#4D4D4F] leading-relaxed mb-3">
                  Submissions finalized in &lt;12 seconds with 0 modifications. Possible rubber-stamping.
                </p>
              </div>

              <button
                type="button"
                onClick={onOpenLeadAudit}
                disabled={lowLatencyCount === 0}
                className="w-full py-2 px-3 text-xs bg-[#9C1936] hover:bg-[#5F0229] text-white font-semibold rounded-md flex items-center justify-center gap-2 transition-colors shadow-xs disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <span>Trigger Lead Audit</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Block 3: Active Learning Export */}
            <div className="p-3.5 bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-[#29251D]">
                    <Download className="w-3.5 h-3.5 text-[#185F8D]" />
                    <span>Active Learning Export</span>
                  </div>
                  <span className="text-xs font-mono font-bold text-[#185F8D] tabular-nums">
                    {activeLearningCount} Edge Cases
                  </span>
                </div>
                <p className="text-xs text-[#4D4D4F] leading-relaxed mb-3">
                  {activeLearningCount} high-uncertainty edge cases from persisted low-confidence results.
                </p>
              </div>

              <button
                type="button"
                onClick={onOpenActiveLearningExport}
                disabled={activeLearningCount === 0}
                className="w-full py-2 px-3 text-xs bg-[#29251D] hover:bg-[#4A453D] text-white font-semibold rounded-md flex items-center justify-center gap-2 transition-colors shadow-xs disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <span>Export to Retraining Queue</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>

          </div>
        </div>

        {/* Footer */}
        <div className="pt-3 border-t border-[#E5DFD3] flex items-center justify-between text-xs text-[#4D4D4F] mt-2">
          <div className="flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-[#247153]" />
            <span>HITL Queue Live Sync</span>
          </div>
          <span className="text-[#247153] font-mono text-[11px] font-semibold">Active</span>
        </div>
      </div>

    </section>
  );
};
