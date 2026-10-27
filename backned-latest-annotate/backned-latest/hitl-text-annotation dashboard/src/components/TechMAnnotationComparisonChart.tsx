import React from 'react';
import { BarChart3, CheckCircle2, UserCheck, ArrowRight, Layers } from 'lucide-react';
import { AnnotationType } from '../types';

export interface AnnotationComparisonRow {
  id: string;
  name: string;
  total_docs: number;
  ai_processed_docs: number;
  ai_processed_pct: number;
  hitl_docs: number;
  hitl_pct: number;
  accuracy?: number | null;
  cost_saved_dollars?: number;
}

interface TechMAnnotationComparisonChartProps {
  data: AnnotationComparisonRow[];
  activeAnnotationType: AnnotationType;
  onSelectAnnotationType: (type: AnnotationType) => void;
}

export const TechMAnnotationComparisonChart: React.FC<TechMAnnotationComparisonChartProps> = ({
  data,
  activeAnnotationType,
  onSelectAnnotationType
}) => {
  return (
    <section className="bg-white border border-[#E5DFD3] rounded-lg p-5 mb-5 shadow-xs">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-[#E5DFD3] mb-4 gap-2">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-[#E31837]" />
          <div>
            <h2 className="text-sm font-semibold text-[#29251D]">
              Annotation Pipeline Distribution: AI Processed vs. Moved to HITL
            </h2>
            <p className="text-xs text-[#4D4D4F]">
              Comparative breakdown from the selected project's persisted assets
            </p>
          </div>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 text-xs font-medium">
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-xs bg-[#247153]" />
            <span className="text-[#29251D]">Processed Through AI</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-xs bg-[#8A5200]" />
            <span className="text-[#29251D]">Moved to HITL Review</span>
          </div>
        </div>
      </div>

      {/* 5 Annotation Type Bars */}
      <div className="space-y-4">
        {data.map((item) => {
          const isSelected = activeAnnotationType === item.id;
          return (
            <div
              key={item.id}
              onClick={() => onSelectAnnotationType(item.id)}
              className={`p-3 rounded-lg border transition-all cursor-pointer ${
                isSelected
                  ? 'bg-[#F6F2EA] border-[#E31837] shadow-xs ring-1 ring-[#E31837]/30'
                  : 'bg-white border-[#E5DFD3] hover:border-[#4A453D]/30 hover:bg-[#F6F2EA]/40'
              }`}
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 mb-2">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-semibold ${isSelected ? 'text-[#E31837]' : 'text-[#29251D]'}`}>
                    {item.name}
                  </span>
                  {isSelected && (
                    <span className="text-[10px] font-semibold bg-[#E31837] text-white px-2 py-0.2 rounded-xs">
                      Active Section
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-3 text-xs font-mono text-[#4D4D4F]">
                  <span>Total: <strong className="text-[#29251D]">{item.total_docs.toLocaleString()}</strong></span>
                  <span>·</span>
                  <span className="text-[#247153] font-semibold">AI: {item.ai_processed_docs.toLocaleString()} ({item.ai_processed_pct}%)</span>
                  <span>·</span>
                  <span className="text-[#8A5200] font-semibold">HITL: {item.hitl_docs.toLocaleString()} ({item.hitl_pct}%)</span>
                </div>
              </div>

              {/* Stacked Comparative Bar */}
              <div className="w-full h-4 rounded-xs overflow-hidden flex bg-[#E5DFD3]">
                {/* AI Processed segment */}
                <div
                  style={{ width: `${item.ai_processed_pct}%` }}
                  className="bg-[#247153] h-full transition-all hover:opacity-90 flex items-center justify-start pl-2 text-[10px] text-white font-mono font-bold"
                  title={`AI Processed: ${item.ai_processed_docs.toLocaleString()} (${item.ai_processed_pct}%)`}
                >
                  {item.ai_processed_pct}%
                </div>

                {/* Moved to HITL segment */}
                <div
                  style={{ width: `${item.hitl_pct}%` }}
                  className="bg-[#8A5200] h-full transition-all hover:opacity-90 flex items-center justify-end pr-2 text-[10px] text-white font-mono font-bold"
                  title={`Moved to HITL: ${item.hitl_docs.toLocaleString()} (${item.hitl_pct}%)`}
                >
                  {item.hitl_pct}%
                </div>
              </div>

              <div className="flex justify-between items-center text-[11px] text-[#4D4D4F] mt-1.5 pt-1 border-t border-[#E5DFD3]/60">
                <span>Model Baseline Accuracy: <strong className="text-[#29251D]">{item.accuracy == null ? 'N/A' : `${item.accuracy}%`}</strong></span>
                <span className="text-[#E31837] font-medium flex items-center gap-1 hover:underline">
                  <span>View Section Details</span>
                  <ArrowRight className="w-3 h-3" />
                </span>
              </div>
            </div>
          );
        })}
      </div>

    </section>
  );
};
