import React from 'react';
import { AlertCircle, ArrowRight, CheckCircle2, Quote, Sparkles } from 'lucide-react';

interface RelationItem {
  id?: string;
  label?: string;
  confidence?: number | null;
  review_status?: string;
  text_span?: { text?: string };
  geometry?: {
    source?: string;
    target?: string;
    relation?: string;
    source_type?: string;
    target_type?: string;
    evidence?: string;
    confidence?: number | null;
  };
  geometry_type?: string;
  provenance?: {
    raw_result?: {
      confidence?: number | null;
    };
  };
}

interface TextAIPredictionsProps {
  selectedEntityId: string | null;
  onSelectEntity: (id: string) => void;
  analysis?: {
    analysis_type?: string;
    capability?: string;
    annotations?: RelationItem[];
  } | null;
}

const isRelationAnalysis = (analysis?: TextAIPredictionsProps['analysis']) =>
  analysis?.analysis_type === 'RELATION_EXTRACTION' || analysis?.capability === 'text_relation_extraction';

const statusStyle = (status: string) => {
  if (status === 'APPROVED') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (status === 'REJECTED') return 'border-rose-200 bg-rose-50 text-rose-700';
  if (status === 'EDITED') return 'border-amber-200 bg-amber-50 text-amber-700';
  return 'border-slate-200 bg-slate-50 text-slate-600';
};

export const TextAIPredictions: React.FC<TextAIPredictionsProps> = ({ selectedEntityId, onSelectEntity, analysis }) => {
  const annotations = analysis?.annotations || [];
  const relationMode = isRelationAnalysis(analysis);

  return (
    <div id="text-ai-predictions-card" className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-2xs">
      <div className="flex items-start justify-between gap-3 border-b border-slate-100 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-blue-100 bg-blue-50 text-blue-600">
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-slate-900">{relationMode ? 'Extracted relationships' : 'AI predictions'}</h3>
            <p className="mt-0.5 text-[11px] text-slate-500">{annotations.length} persisted result{annotations.length === 1 ? '' : 's'}</p>
          </div>
        </div>
        {relationMode && <span className="rounded-full bg-blue-50 px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-blue-700">AI + evidence</span>}
      </div>

      {!analysis ? <p className="text-xs text-slate-500">Run the agent to see predictions.</p> : annotations.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-200 px-3 py-5 text-center text-xs text-slate-500">
          {relationMode ? 'No supported relationships were returned.' : 'No persisted predictions were returned for this analysis.'}
        </div>
      ) : relationMode ? (
        <div className="space-y-2.5">
          {annotations.map((item, index) => {
            const id = item.id || `annotation-${index}`;
            const geometry = item.geometry || {};
            const status = String(item.review_status || 'PENDING').toUpperCase();
            // Human edits may clear the editable field. Prefer the persisted
            // model score, then the raw relation result, without inventing a
            // confidence value when neither is available.
            const confidenceValue = item.confidence ?? geometry.confidence ?? item.provenance?.raw_result?.confidence ?? null;
            const confidence = confidenceValue == null ? null : Math.round(confidenceValue * 100);
            return (
              <button key={id} onClick={() => onSelectEntity(id)} className={`w-full rounded-xl border p-3 text-left transition ${selectedEntityId === id ? 'border-blue-300 bg-blue-50/60 shadow-sm' : 'border-slate-200 bg-white hover:border-blue-200 hover:bg-slate-50'}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="rounded-md bg-blue-100 px-2 py-1 text-[10px] font-extrabold uppercase tracking-wide text-blue-800">{geometry.relation || item.label || 'RELATION'}</span>
                  <span className={`rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase ${statusStyle(status)}`}>{status}</span>
                </div>
                <div className="mt-3 flex items-center gap-2 text-xs">
                  <span className="min-w-0 flex-1 truncate rounded-md border border-slate-200 bg-white px-2 py-1.5 font-semibold text-slate-800" title={geometry.source}>{geometry.source || 'Unknown subject'}</span>
                  <ArrowRight className="h-3.5 w-3.5 shrink-0 text-blue-500" />
                  <span className="min-w-0 flex-1 truncate rounded-md border border-slate-200 bg-white px-2 py-1.5 font-semibold text-slate-800" title={geometry.target}>{geometry.target || 'Unknown object'}</span>
                </div>
                <div className="mt-2 flex items-start gap-1.5 rounded-md bg-slate-50 px-2 py-1.5 text-[11px] leading-4 text-slate-600">
                  <Quote className="mt-0.5 h-3 w-3 shrink-0 text-slate-400" />
                  <span className="line-clamp-2">{geometry.evidence || item.text_span?.text || 'Evidence not available'}</span>
                </div>
                <div className="mt-2 flex items-center justify-between text-[10px] text-slate-500">
                  <span>{geometry.source_type || 'ENTITY'} → {geometry.target_type || 'ENTITY'}</span>
                  <span className="font-bold text-slate-700">{confidence == null ? 'Confidence unavailable' : `${confidence}% model confidence`}</span>
                </div>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="space-y-2">{annotations.map((item, index) => {
          const id = item.id || `annotation-${index}`;
          return <button key={id} onClick={() => onSelectEntity(id)} className={`flex w-full items-center justify-between rounded-lg border p-2 text-left ${selectedEntityId === id ? 'border-blue-200 bg-blue-50' : 'border-transparent hover:bg-slate-50'}`}><span className="truncate text-xs font-semibold text-slate-800">{item.text_span?.text || 'Document annotation'}</span><span className="text-[10px] font-bold uppercase text-blue-700">{item.label || 'ANNOTATION'}</span></button>;
        })}</div>
      )}

      {relationMode && annotations.length > 0 && (
        <div className="flex items-center gap-3 border-t border-slate-100 pt-3 text-[10px] text-slate-500">
          <span className="inline-flex items-center gap-1"><CheckCircle2 className="h-3 w-3 text-emerald-500" /> reviewed</span>
          <span className="inline-flex items-center gap-1"><AlertCircle className="h-3 w-3 text-amber-500" /> select to edit</span>
        </div>
      )}
    </div>
  );
};
