import React from 'react';
import { Sparkles } from 'lucide-react';

interface TextAISummaryProps {
  mode?: 'NER' | 'Sentiment';
  compact?: boolean;
  analysis?: {
    annotations?: Array<{ confidence?: number }>;
    agent_status?: string;
    quality_report?: { annotation_count?: number; final_decision?: string };
  } | null;
}

export const TextAISummary: React.FC<TextAISummaryProps> = ({ analysis }) => {
  const annotations = analysis?.annotations || [];
  const decision = analysis?.quality_report?.final_decision || analysis?.agent_status;
  const confidenceValues = annotations.map((item) => item.confidence).filter((value): value is number => typeof value === 'number');
  const confidence = confidenceValues.length ? confidenceValues.reduce((sum, value) => sum + value, 0) / confidenceValues.length : null;

  return (
    <div id="text-ai-prediction-summary-card" className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs space-y-4">
      <div className="flex items-center gap-2.5 border-b border-slate-100 pb-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-blue-100 bg-blue-50 text-blue-600"><Sparkles className="h-4 w-4" /></div>
        <h3 className="text-xs font-bold text-slate-900">AI Prediction Summary</h3>
      </div>
      {!analysis ? <p className="text-xs text-slate-500">No agent result yet.</p> : (
        <div className="space-y-3 text-xs">
          <div className="flex justify-between"><span className="text-slate-400">Annotations</span><span className="font-semibold text-slate-800">{analysis.quality_report?.annotation_count ?? annotations.length}</span></div>
          <div className="flex justify-between"><span className="text-slate-400">Agent status</span><span className="font-semibold text-slate-800">{decision || 'COMPLETED'}</span></div>
          {confidence !== null && <div className="space-y-1"><div className="flex justify-between"><span className="text-slate-400">Mean confidence</span><span className="font-semibold text-slate-800">{confidence.toFixed(2)}</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.round(confidence * 100)}%` }} /></div></div>}
        </div>
      )}
    </div>
  );
};
