import React from 'react';
import { ChevronLeft } from 'lucide-react';

interface BottomTimelineBarProps {
  assetId: string;
  currentPhase: number;
  onPrevious: () => void;
}

export const BottomTimelineBar: React.FC<BottomTimelineBarProps> = ({
  assetId = '',
  currentPhase = 1,
  onPrevious,
}) => {
  return (
    <div
      id="text-bottom-timeline-bar"
      className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white px-5 py-3 shadow-2xs mt-4"
    >
      {/* Asset ID with green indicator */}
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
        <span className="text-xs font-bold text-slate-800">
          Asset ID: <span className="font-mono text-slate-600 font-semibold">{assetId}</span>
        </span>
      </div>

      {/* Stepper Timeline: 1 AI Result -> 2 Review -> 3 Submit */}
      <div className="flex items-center gap-3 text-xs font-semibold">
        {/* Step 1 */}
        <div className="flex items-center gap-1.5">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-[11px] font-bold text-white shadow-xs">
            1
          </span>
          <span className="text-blue-600 font-bold">AI Result</span>
        </div>

        {/* Divider */}
        <span className="h-0.5 w-8 bg-slate-200" />

        {/* Step 2 */}
        <div className="flex items-center gap-1.5">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-200 text-[11px] font-bold text-slate-600">
            2
          </span>
          <span className="text-slate-500">Review</span>
        </div>

        {/* Divider */}
        <span className="h-0.5 w-8 bg-slate-200" />

        {/* Step 3 */}
        <div className="flex items-center gap-1.5">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-200 text-[11px] font-bold text-slate-600">
            3
          </span>
          <span className="text-slate-500">Submit</span>
        </div>
      </div>

      {/* Previous Button */}
      <button
        onClick={onPrevious}
        className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition cursor-pointer"
      >
        <ChevronLeft className="h-4 w-4" />
        <span>Previous</span>
      </button>
    </div>
  );
};
