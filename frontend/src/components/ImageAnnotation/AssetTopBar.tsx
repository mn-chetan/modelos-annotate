import React from 'react';
import { ChevronLeft, ChevronRight, ArrowRight } from 'lucide-react';

interface AssetTopBarProps {
  currentIndex: number;
  totalAssets: number;
  onPrev: () => void;
  onNext: () => void;
}

export const AssetTopBar: React.FC<AssetTopBarProps> = ({
  currentIndex = 12,
  totalAssets = 120,
  onPrev,
  onNext,
}) => {
  return (
    <div
      id="asset-top-bar"
      className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200/90 bg-white px-5 py-3.5 shadow-2xs"
    >
      {/* Asset Thumbnail & Metadata */}
      <div className="flex items-center gap-3.5 min-w-[280px]">
        {/* Thumbnail */}
        <div className="relative h-12 w-16 shrink-0 overflow-hidden rounded-lg border border-slate-200 bg-slate-100 shadow-2xs">
          <svg className="h-full w-full object-cover" viewBox="0 0 64 48" fill="none">
            <rect width="64" height="48" fill="#e2e8f0" />
            {/* Sky & Buildings */}
            <path d="M0 0h64v24H0z" fill="#93c5fd" opacity="0.6" />
            <path d="M4 14h8v10H4zM16 8h10v16H16zM30 11h9v13H30zM42 6h8v18H42zM53 13h8v11H53z" fill="#64748b" opacity="0.4" />
            {/* Road */}
            <path d="M0 24h64v24H0z" fill="#475569" />
            <path d="M30 24l-8 24h4l8-24zM38 24l8 24h-4l-8-24z" fill="#f8fafc" opacity="0.6" />
            {/* Vehicles */}
            <rect x="22" y="32" width="12" height="8" rx="2" fill="#ef4444" />
            <rect x="36" y="27" width="10" height="13" rx="2" fill="#22c55e" />
          </svg>
        </div>

        {/* Title and Specs */}
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-slate-900 tracking-tight">IMG_00452.jpg</span>
            <span className="rounded-full bg-rose-50 px-2 py-0.5 text-[10px] font-semibold text-rose-600 border border-rose-100">
              High Priority
            </span>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-slate-500 font-normal mt-0.5">
            <span>File: JPG</span>
            <span>•</span>
            <span>Size: 2.4 MB</span>
            <span>•</span>
            <span>Resolution: 1920 × 1080</span>
          </div>
        </div>
      </div>

      {/* AI Confidence Meter */}
      <div className="flex items-center gap-3 border-x border-slate-100 px-4">
        {/* Radial progress ring */}
        <div className="relative flex h-11 w-11 items-center justify-center">
          <svg className="h-full w-full -rotate-90 transform" viewBox="0 0 36 36">
            <path
              className="text-slate-100"
              strokeWidth="3.2"
              stroke="currentColor"
              fill="none"
              d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            />
            <path
              className="text-emerald-500"
              strokeDasharray="82, 100"
              strokeLinecap="round"
              strokeWidth="3.2"
              stroke="currentColor"
              fill="none"
              d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            />
          </svg>
          <span className="absolute text-[11px] font-bold text-slate-800">0.82</span>
        </div>

        <div className="flex flex-col">
          <span className="text-xs font-semibold text-slate-800 leading-tight">AI Confidence</span>
          <span className="text-[11px] font-medium text-emerald-600 leading-tight">
            Above threshold (0.80)
          </span>
        </div>
      </div>

      {/* Task Type */}
      <div className="hidden xl:flex flex-col justify-center">
        <span className="text-[11px] font-medium text-slate-400 leading-tight">Task Type</span>
        <span className="text-xs font-bold text-slate-800 leading-tight mt-0.5">
          Object Detection + Classification
        </span>
      </div>

      {/* Pagination & Next Button */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1">
          <button
            id="prev-asset-btn"
            onClick={onPrev}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition cursor-pointer"
            aria-label="Previous image"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>

          <span className="px-2.5 text-xs font-bold text-slate-700 select-none">
            {currentIndex} / {totalAssets}
          </span>

          <button
            id="next-asset-chevron-btn"
            onClick={onNext}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition cursor-pointer"
            aria-label="Next image"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>

        <button
          id="next-asset-btn"
          onClick={onNext}
          className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-blue-700 transition cursor-pointer"
        >
          <span>Next</span>
        </button>
      </div>
    </div>
  );
};
