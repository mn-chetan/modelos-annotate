import React from 'react';
import {
  Sliders,
  RotateCcw,
  ShieldCheck,
  AlertTriangle,
  ArrowRight,
  TrendingDown,
  Percent
} from 'lucide-react';

interface TechMConfidenceThresholdBarProps {
  threshold: number;
  onChangeThreshold: (val: number) => void;
  autoRate: number;
  humanReviewRate: number;
  workloadDeltaPct: number;
}

export const TechMConfidenceThresholdBar: React.FC<TechMConfidenceThresholdBarProps> = ({
  threshold,
  onChangeThreshold,
  autoRate,
  humanReviewRate,
  workloadDeltaPct
}) => {
  return (
    <section className="bg-white border border-[#E5DFD3] rounded-lg p-4 mb-5 shadow-xs">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        
        {/* Left: Title & Threshold Value */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-md bg-[#F6F2EA] border border-[#E5DFD3] flex items-center justify-center text-[#E31837] shrink-0">
            <Sliders className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-[#29251D]">
                Confidence Threshold Governor
              </h2>
              <span className="text-xs font-mono font-bold text-[#E31837] bg-[#F8B4A3]/20 px-2 py-0.5 rounded border border-[#F8B4A3]">
                τ = {threshold.toFixed(2)}
              </span>
            </div>
            <p className="text-xs text-[#4D4D4F] mt-0.5">
              Controls routing: Spans with confidence ≥ {threshold.toFixed(2)} are Auto-Approved; below threshold routed to HITL review.
            </p>
          </div>
        </div>

        {/* Center: Slider Bar & Live Ratio */}
        <div className="flex-1 max-w-xl px-2">
          <div className="flex items-center justify-between text-xs mb-1.5 font-medium">
            <div className="flex items-center gap-2">
              <span className="text-[#247153] font-bold">
                {autoRate.toFixed(1)}% AI Auto-Approved
              </span>
              <span className="text-[#E5DFD3]">|</span>
              <span className="text-[#8A5200] font-bold">
                {humanReviewRate.toFixed(1)}% Moved to HITL
              </span>
            </div>
            <div className="text-[11px] text-[#4D4D4F] font-mono">
              {workloadDeltaPct === 0 ? (
                <span>Baseline Workload</span>
              ) : workloadDeltaPct > 0 ? (
                <span className="text-[#8A5200]">Workload +{workloadDeltaPct}%</span>
              ) : (
                <span className="text-[#247153]">Workload {workloadDeltaPct}%</span>
              )}
            </div>
          </div>

          {/* Interactive Range Slider */}
          <div className="relative py-1">
            <input
              type="range"
              min="0.70"
              max="0.98"
              step="0.01"
              value={threshold}
              onChange={(e) => onChangeThreshold(parseFloat(e.target.value))}
              className="w-full h-2.5 bg-[#E5DFD3] rounded-lg appearance-none cursor-pointer accent-[#E31837] hover:accent-[#5F0229] transition-all"
            />
            <div className="flex justify-between text-[10px] text-[#4D4D4F] font-mono mt-1">
              <span>0.70 (High Volume)</span>
              <span>0.85</span>
              <span className="font-semibold text-[#29251D]">0.90 (Balanced)</span>
              <span>0.95</span>
              <span>0.98 (Strict Safety)</span>
            </div>
          </div>
        </div>

        {/* Right: Preset Buttons & Reset */}
        <div className="flex items-center gap-2 shrink-0 border-t lg:border-t-0 pt-2 lg:pt-0 border-[#E5DFD3]">
          <span className="text-[11px] text-[#4D4D4F] font-medium hidden sm:inline">Presets:</span>
          <button
            type="button"
            onClick={() => onChangeThreshold(0.85)}
            className={`px-2.5 py-1 text-xs rounded border transition-colors ${
              threshold === 0.85
                ? 'bg-[#E31837] text-white border-[#E31837] font-semibold'
                : 'bg-white text-[#29251D] border-[#E5DFD3] hover:bg-[#F6F2EA]'
            }`}
          >
            0.85
          </button>
          <button
            type="button"
            onClick={() => onChangeThreshold(0.90)}
            className={`px-2.5 py-1 text-xs rounded border transition-colors ${
              threshold === 0.90
                ? 'bg-[#E31837] text-white border-[#E31837] font-semibold'
                : 'bg-white text-[#29251D] border-[#E5DFD3] hover:bg-[#F6F2EA]'
            }`}
          >
            0.90
          </button>
          <button
            type="button"
            onClick={() => onChangeThreshold(0.95)}
            className={`px-2.5 py-1 text-xs rounded border transition-colors ${
              threshold === 0.95
                ? 'bg-[#E31837] text-white border-[#E31837] font-semibold'
                : 'bg-white text-[#29251D] border-[#E5DFD3] hover:bg-[#F6F2EA]'
            }`}
          >
            0.95
          </button>
          <button
            type="button"
            onClick={() => onChangeThreshold(0.90)}
            className="p-1.5 text-[#4D4D4F] hover:text-[#29251D] border border-[#E5DFD3] rounded bg-white hover:bg-[#F6F2EA] transition-colors"
            title="Reset to 0.90 baseline"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>

      </div>
    </section>
  );
};
