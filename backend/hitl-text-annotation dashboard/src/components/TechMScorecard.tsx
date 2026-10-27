import React from 'react';
import {
  FileText,
  CheckCircle2,
  Users,
  Edit3,
  TrendingUp,
  DollarSign,
  Clock
} from 'lucide-react';

interface TechMScorecardProps {
  totalDocs?: number;
  autoApprovedRate?: number;
  autoApprovedDocs?: number;
  threshold?: number;
  humanReviewRate?: number;
  humanReviewDocs?: number;
  humanEditRate?: number;
  costSavedDollars?: number;
  timeSavedHrs?: number;
  workloadDeltaPct?: number;
}

export const TechMScorecard: React.FC<TechMScorecardProps> = ({
  totalDocs = 0,
  autoApprovedRate = 0,
  autoApprovedDocs = 0,
  threshold = 0,
  humanReviewRate = 0,
  humanReviewDocs = 0,
  humanEditRate = 0,
  costSavedDollars = 0,
  timeSavedHrs = 0,
  workloadDeltaPct = 0
}) => {
  return (
    <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5 mb-5">
      
      {/* 1. Total Ingested Docs */}
      <div className="bg-white border border-[#E5DFD3] rounded-lg p-4 transition-all hover:border-[#4A453D]/40 shadow-xs">
        <div className="flex items-center justify-between text-xs text-[#4D4D4F] mb-1.5 font-medium">
          <span>Total Ingested Docs</span>
          <FileText className="w-4 h-4 text-[#4A453D]" />
        </div>
        <div className="text-2xl font-bold tracking-tight text-[#29251D] font-mono tabular-nums">
          {totalDocs.toLocaleString()}
        </div>
        <div className="flex items-center gap-1.5 text-xs text-[#247153] mt-2 font-medium">
          <TrendingUp className="w-3.5 h-3.5" />
          <span>+12.4%</span>
          <span className="text-[#4D4D4F] font-normal">· this week</span>
        </div>
      </div>

      {/* 2. Auto-Approved Rate */}
      <div className="bg-white border border-[#E5DFD3] rounded-lg p-4 transition-all hover:border-[#247153]/50 shadow-xs border-t-2 border-t-[#247153]">
        <div className="flex items-center justify-between text-xs text-[#4D4D4F] mb-1.5 font-medium">
          <span>Auto-Approved Rate</span>
          <CheckCircle2 className="w-4 h-4 text-[#247153]" />
        </div>
        <div className="text-2xl font-bold tracking-tight text-[#247153] font-mono tabular-nums">
          {autoApprovedRate.toFixed(1)}%
        </div>
        <div className="flex items-center gap-1.5 text-xs text-[#4D4D4F] mt-2">
          <span className="font-mono text-[#29251D] font-medium">
            {autoApprovedDocs.toLocaleString()} docs
          </span>
          <span>·</span>
          <span>Score ≥ {threshold.toFixed(2)}</span>
        </div>
      </div>

      {/* 3. Human Review Rate */}
      <div className="bg-white border border-[#E5DFD3] rounded-lg p-4 transition-all hover:border-[#8A5200]/50 shadow-xs border-t-2 border-t-[#8A5200]">
        <div className="flex items-center justify-between text-xs text-[#4D4D4F] mb-1.5 font-medium">
          <span>Human Review Rate</span>
          <Users className="w-4 h-4 text-[#8A5200]" />
        </div>
        <div className="text-2xl font-bold tracking-tight text-[#8A5200] font-mono tabular-nums">
          {humanReviewRate.toFixed(1)}%
        </div>
        <div className="flex items-center gap-1.5 text-xs text-[#4D4D4F] mt-2">
          <span className="font-mono text-[#29251D] font-medium">
            {humanReviewDocs.toLocaleString()} docs
          </span>
          <span>·</span>
          {workloadDeltaPct === 0 ? (
            <span className="text-[#4D4D4F]">Baseline load</span>
          ) : workloadDeltaPct > 0 ? (
            <span className="text-[#8A5200]">+{workloadDeltaPct}% manual</span>
          ) : (
            <span className="text-[#247153]">{workloadDeltaPct}% manual</span>
          )}
        </div>
      </div>

      {/* 4. Human Edit Rate */}
      <div className="bg-white border border-[#E5DFD3] rounded-lg p-4 transition-all hover:border-[#4A453D]/40 shadow-xs">
        <div className="flex items-center justify-between text-xs text-[#4D4D4F] mb-1.5 font-medium">
          <span>Human Edit Rate</span>
          <Edit3 className="w-4 h-4 text-[#185F8D]" />
        </div>
        <div className="text-2xl font-bold tracking-tight text-[#29251D] font-mono tabular-nums">
          {humanEditRate.toFixed(1)}%
        </div>
        <div className="flex items-center gap-1.5 text-xs text-[#4D4D4F] mt-2">
          <span className="text-[#185F8D] font-medium">1 in 6.7</span>
          <span>spans modified</span>
        </div>
      </div>

      {/* 5. Cost & Time Saved */}
      <div className="bg-white border border-[#E5DFD3] rounded-lg p-4 transition-all hover:border-[#E31837]/40 shadow-xs border-t-2 border-t-[#E31837]">
        <div className="flex items-center justify-between text-xs text-[#4D4D4F] mb-1.5 font-medium">
          <span>Cost & Time Saved</span>
          <DollarSign className="w-4 h-4 text-[#E31837]" />
        </div>
        <div className="text-2xl font-bold tracking-tight text-[#E31837] font-mono tabular-nums">
          ${costSavedDollars.toLocaleString()}
        </div>
        <div className="flex items-center gap-1.5 text-xs text-[#4D4D4F] mt-2">
          <Clock className="w-3.5 h-3.5 text-[#4D4D4F]" />
          <span className="font-mono text-[#29251D] font-medium">
            ~{timeSavedHrs.toLocaleString()} hrs
          </span>
          <span>· vs 100% manual</span>
        </div>
      </div>

    </section>
  );
};
