import React from 'react';
import {
  AlertCircle,
  Clock,
  Sparkles,
  ArrowRight,
  ShieldAlert,
  Download,
  Users2,
  FileSpreadsheet,
  CheckCircle2,
  Zap
} from 'lucide-react';

interface TriageDrawerProps {
  disputedCount: number;
  lowLatencyCount: number;
  activeLearningCount: number;
  onOpenDisputeResolution: () => void;
  onOpenLeadAudit: () => void;
  onOpenActiveLearningExport: () => void;
}

export const TriageDrawer: React.FC<TriageDrawerProps> = ({
  disputedCount,
  lowLatencyCount,
  activeLearningCount,
  onOpenDisputeResolution,
  onOpenLeadAudit,
  onOpenActiveLearningExport
}) => {
  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 flex flex-col justify-between h-full">
      <div>
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800/80 mb-4">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-amber-400" />
            <h2 className="text-sm font-semibold text-white tracking-wide">
              Actionable HITL Triage Drawer
            </h2>
          </div>
          <span className="text-[11px] font-mono text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
            3 Active Queues
          </span>
        </div>

        {/* 3 Actionable Alert Blocks */}
        <div className="space-y-3.5">
          
          {/* Block 1: Disputed Items */}
          <div className="p-3.5 bg-slate-950/70 border border-amber-900/40 rounded-lg transition-all hover:border-amber-700/60 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-300">
                  <Users2 className="w-3.5 h-3.5 text-amber-400" />
                  <span>Dual Annotator Disagreements</span>
                </div>
                <span className="text-xs font-mono font-bold text-amber-400 tabular-nums">
                  {disputedCount} Items
                </span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed mb-3">
                Dual blind reviewers differed on token boundary offsets or entity taxonomy tags. Requires senior arbiter sign-off.
              </p>
            </div>

            <button
              type="button"
              onClick={onOpenDisputeResolution}
              className="w-full py-2 px-3 text-xs font-medium bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold rounded-md flex items-center justify-center gap-2 transition-colors shadow-sm"
            >
              <span>Open Dispute Resolution</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Block 2: Low-Latency Submissions (Rubber-stamping alert) */}
          <div className="p-3.5 bg-slate-950/70 border border-rose-900/40 rounded-lg transition-all hover:border-rose-700/60 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-rose-300">
                  <Clock className="w-3.5 h-3.5 text-rose-400" />
                  <span>Low-Latency Submissions</span>
                </div>
                <span className="text-xs font-mono font-bold text-rose-400 tabular-nums">
                  {lowLatencyCount} Items
                </span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed mb-3">
                Heuristic telemetry detected 89 submissions finalized in &lt;12 seconds with 0 edits. Possible rubber-stamping detected.
              </p>
            </div>

            <button
              type="button"
              onClick={onOpenLeadAudit}
              className="w-full py-2 px-3 text-xs font-medium bg-rose-600 hover:bg-rose-500 text-white font-semibold rounded-md flex items-center justify-center gap-2 transition-colors shadow-sm"
            >
              <span>Trigger Lead Audit</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Block 3: Active Learning Export */}
          <div className="p-3.5 bg-slate-950/70 border border-indigo-900/40 rounded-lg transition-all hover:border-indigo-700/60 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-indigo-300">
                  <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                  <span>Active Learning Queue</span>
                </div>
                <span className="text-xs font-mono font-bold text-indigo-400 tabular-nums">
                  {activeLearningCount} Edge Cases
                </span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed mb-3">
                High epistemic entropy & margin uncertainty samples synthesized and ready for model fine-tuning loop (v1.5 candidate).
              </p>
            </div>

            <button
              type="button"
              onClick={onOpenActiveLearningExport}
              className="w-full py-2 px-3 text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-md flex items-center justify-center gap-2 transition-colors shadow-sm"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export to Retraining Queue</span>
            </button>
          </div>

        </div>
      </div>

      {/* Footer System Status */}
      <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400 mt-2">
        <div className="flex items-center gap-1.5">
          <Zap className="w-3.5 h-3.5 text-emerald-400" />
          <span>Real-time HITL Kafka consumer</span>
        </div>
        <span className="text-emerald-400 font-mono text-[11px]">Synced</span>
      </div>
    </div>
  );
};
