import React from 'react';
import { AlertTriangle } from 'lucide-react';

interface RightDetailsPanelProps {
  onReject?: () => void;
  onEdit?: () => void;
  onSubmitReview?: () => void;
}

export const RightDetailsPanel: React.FC<RightDetailsPanelProps> = () => {
  return (
    <div
      id="text-right-details-panel"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs space-y-5"
    >
      <h3 className="text-sm font-bold text-slate-900">Annotation Details</h3>

      {/* AI Sentiment Prediction */}
      <div>
        <span className="block text-xs font-semibold text-slate-700 mb-1.5">
          AI Sentiment Prediction
        </span>
        <div className="flex items-center gap-2.5">
          <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700 border border-emerald-200">
            Positive
          </span>
          <span className="text-xs font-semibold text-slate-600">
            Confidence: <strong className="text-slate-900">0.82</strong>
          </span>
        </div>
      </div>

      {/* Overall AI Confidence Meter */}
      <div>
        <div className="flex items-center justify-between text-xs font-semibold text-slate-700 mb-1.5">
          <span>Overall AI Confidence</span>
          <span className="font-bold text-slate-900">0.82</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full rounded-full bg-gradient-to-r from-teal-500 to-emerald-500"
            style={{ width: '82%' }}
          />
        </div>
      </div>

      {/* Why this needs review? Alert */}
      <div className="rounded-lg border border-amber-200 bg-amber-50/70 p-3.5 flex items-start gap-3">
        <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-600 mt-0.5">
          <AlertTriangle className="h-3.5 w-3.5" />
        </div>
        <div>
          <h4 className="text-xs font-bold text-amber-900">Confidence below threshold (0.80)</h4>
          <p className="text-[11px] text-amber-800 mt-0.5 leading-relaxed font-medium">
            The overall confidence score is 0.82, which is slightly below the required threshold.
          </p>
        </div>
      </div>
    </div>
  );
};
