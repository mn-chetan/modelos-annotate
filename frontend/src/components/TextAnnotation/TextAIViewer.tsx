import React, { useMemo, useState } from 'react';
import { ZoomIn, ZoomOut } from 'lucide-react';

interface TextAnnotation {
  id?: string;
  label?: string;
  text_span?: { start?: number; end?: number; text?: string };
  geometry?: { page?: number };
  confidence?: number;
}

interface TextAIViewerProps {
  selectedEntityId: string | null;
  onSelectEntity: (id: string) => void;
  onToast: (msg: string) => void;
  taskType?: string;
  mode?: 'NER' | 'Sentiment';
  text?: string;
  annotations?: TextAnnotation[];
  analysisLevel?: 'document' | 'page' | 'paragraph' | 'sentence';
}

export const TextAIViewer: React.FC<TextAIViewerProps> = ({
  selectedEntityId,
  onSelectEntity,
  onToast,
  taskType = 'NER',
  text,
  annotations = [],
  analysisLevel = 'document',
}) => {
  const [zoom, setZoom] = useState(100);
  const spans = useMemo(() => {
    if (!analysisLevel) return [];
    if (analysisLevel === 'document') {
      return annotations
        .map((item) => ({ ...item, start: item.text_span?.start ?? -1, end: item.text_span?.end ?? -1 }))
        .filter((item) => item.start >= 0 && item.end > item.start)
        .sort((a, b) => a.start - b.start);
    }
    let searchCursor = 0;
    return annotations.flatMap((item) => {
      const segmentText = item.text_span?.text || '';
      if (!segmentText) return [];
      const start = text?.indexOf(segmentText, searchCursor) ?? -1;
      if (start < 0) return [];
      searchCursor = start + segmentText.length;
      return [{ ...item, start, end: searchCursor }];
    });
  }, [annotations, analysisLevel, text]);

  const renderText = () => {
    if (!text) return null;
    if (spans.length === 0) {
      return <span className="whitespace-pre-wrap">{text}</span>;
    }
    const chunks: React.ReactNode[] = [];
    let cursor = 0;
    spans.forEach((span, index) => {
      if (span.start < cursor) return;
      if (span.start > cursor) chunks.push(<span key={`plain-${index}`}>{text.slice(cursor, span.start)}</span>);
      const id = span.id || `annotation-${index}`;
      chunks.push(
        <span
          key={id}
          onClick={() => onSelectEntity(id)}
          title={`${span.label || 'Annotation'} · ${Math.round((span.confidence || 0) * 100)}% confidence`}
          className={`mx-1 inline-flex cursor-pointer flex-col items-center rounded-md border-2 px-2 py-0.5 leading-normal ${selectedEntityId === id ? 'ring-2 ring-blue-400 font-bold scale-105' : ''} border-blue-300 bg-blue-50 text-blue-950`}
        >
          <span className="mb-1 text-[10px] font-extrabold uppercase leading-none text-blue-700">{span.label || 'ANNOTATION'}</span>
          {span.text_span?.text || text.slice(span.start, span.end)}
        </span>,
      );
      cursor = span.end;
    });
    if (cursor < text.length) chunks.push(<span key="plain-tail">{text.slice(cursor)}</span>);
    return chunks;
  };

  return (
    <div id="text-ai-viewer-card" className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4 text-xs">
        <h3 className="font-bold text-slate-900"><span className="font-medium text-slate-500">Task Type:</span> {taskType}</h3>
        <div className="inline-flex items-center overflow-hidden rounded-lg border border-slate-200 divide-x divide-slate-100">
          <button onClick={() => setZoom((value) => Math.max(70, value - 10))} className="flex h-7 w-7 items-center justify-center text-slate-600 hover:bg-slate-50" aria-label="Zoom out"><ZoomOut className="h-3.5 w-3.5" /></button>
          <button onClick={() => setZoom((value) => value >= 150 ? 100 : value + 25)} className="h-7 px-2.5 font-semibold text-slate-700">{zoom}%</button>
          <button onClick={() => setZoom((value) => Math.min(200, value + 10))} className="flex h-7 w-7 items-center justify-center text-slate-600 hover:bg-slate-50" aria-label="Zoom in"><ZoomIn className="h-3.5 w-3.5" /></button>
        </div>
      </div>
      <div id="text-content-viewport" className="min-h-[360px] px-4 py-8 text-slate-800" style={{ fontSize: `${(15 * zoom) / 100}px`, lineHeight: '2.8rem' }}>
        {text ? <div className="whitespace-pre-wrap">{renderText()}</div> : (
          <div className="flex min-h-[280px] items-center justify-center rounded-lg border border-dashed border-slate-300 text-sm text-slate-500 p-6 text-center">
            Uploaded document text is being prepared. Select an asset or run agentic analysis.
          </div>
        )}
      </div>
    </div>
  );
};
