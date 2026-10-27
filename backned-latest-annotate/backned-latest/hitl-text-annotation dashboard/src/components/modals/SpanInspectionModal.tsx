import React from 'react';
import { X, Split, CheckCircle2, ArrowRight } from 'lucide-react';

interface SpanInspectionModalProps {
  example: any | null;
  onClose: () => void;
}

export const SpanInspectionModal: React.FC<SpanInspectionModalProps> = ({
  example,
  onClose
}) => {
  if (!example) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-xl w-full shadow-2xl flex flex-col overflow-hidden">
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-950/50">
          <div className="flex items-center gap-2">
            <Split className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-semibold text-white">
              Span Mutation Deep Dive: {example.type}
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4 text-xs">
          <div>
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
              Source Narrative Text
            </div>
            <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-slate-200 font-mono leading-relaxed">
              "{example.text}"
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-lg">
              <div className="text-[11px] text-rose-400 font-semibold mb-1">
                Model Inference (AI)
              </div>
              <div className="font-mono text-slate-200 text-xs font-bold">
                "{example.modelSpan}"
              </div>
              <div className="text-[10px] text-slate-400 font-mono mt-1">
                Tag: [{example.modelTag}]
              </div>
            </div>

            <div className="p-3 bg-slate-950/80 border border-emerald-900/50 rounded-lg">
              <div className="text-[11px] text-emerald-400 font-semibold mb-1">
                Human Ground Truth (HITL)
              </div>
              <div className="font-mono text-slate-200 text-xs font-bold">
                "{example.humanCorrection}"
              </div>
              <div className="text-[10px] text-emerald-400 font-mono mt-1">
                Verified by Lead Arbiter
              </div>
            </div>
          </div>

          <div className="p-3 bg-slate-950/40 border border-slate-800 rounded-lg text-slate-400 leading-relaxed">
            <span className="font-semibold text-slate-300">Root Cause Analysis: </span>
            {example.reason}
          </div>
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-slate-800 bg-slate-950/50 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-white rounded transition-colors"
          >
            Close
          </button>
        </div>

      </div>
    </div>
  );
};
