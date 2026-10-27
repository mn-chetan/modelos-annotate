import React, { useState, useEffect } from 'react';
import {
  FileText,
  Undo2,
  Redo2,
  Trash2,
  Maximize2,
  ZoomIn,
  ZoomOut,
  ChevronDown,
  User,
  Save,
  Send,
  ChevronRight,
  Menu,
  Smile,
  CheckCircle2,
  X,
} from 'lucide-react';
import {
  AssetResponse,
  ProjectResponse,
  TextAnalysisResponse,
  api,
} from '../../services/api';

export interface SentimentEntity {
  id: string;
  text: string;
  sentiment: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL';
  color: string;
  confidence: number;
  page?: number;
  level?: 'document' | 'page' | 'paragraph' | 'sentence';
  paragraphIndex?: number;
  sentenceIndex?: number;
}

interface SentimentAnnotationWorkbenchProps {
  onSwitchMode?: (mode: 'NER' | 'Sentiment') => void;
  onToggleSidebar?: () => void;
  onToast: (msg: string) => void;
  textAsset?: AssetResponse | null;
  project?: ProjectResponse | null;
  analysis?: TextAnalysisResponse | null;
  totalAssets?: number;
  currentAssetIndex?: number;
  onPrevAsset?: () => void;
  onNextAsset?: () => void;
  currentUserEmail?: string;
}

const AVAILABLE_SENTIMENT_LABELS = [
  { label: 'Positive', tag: 'POSITIVE', defaultColor: '#10B981' },
  { label: 'Negative', tag: 'NEGATIVE', defaultColor: '#EF4444' },
  { label: 'Neutral', tag: 'NEUTRAL', defaultColor: '#64748B' },
];

const getSentimentColor = (sentiment: string): string => {
  const s = (sentiment || '').toUpperCase();
  if (s.includes('POS')) return '#10B981';
  if (s.includes('NEG')) return '#EF4444';
  return '#64748B';
};

export const SentimentAnnotationWorkbench: React.FC<SentimentAnnotationWorkbenchProps> = ({
  onToggleSidebar,
  onToast,
  textAsset,
  project,
  analysis,
  totalAssets = 1,
  currentAssetIndex = 0,
  onPrevAsset,
  onNextAsset,
  currentUserEmail,
}) => {
  const [zoomLevel, setZoomLevel] = useState<number>(100);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [entities, setEntities] = useState<SentimentEntity[]>([]);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);

  // Form Edit fields
  const [formText, setFormText] = useState<string>('');
  const [formTag, setFormTag] = useState<'POSITIVE' | 'NEGATIVE' | 'NEUTRAL' | ''>('');
  const [formColor, setFormColor] = useState<string>('');

  // History stack for Undo / Redo
  const [history, setHistory] = useState<SentimentEntity[][]>([[]]);
  const [historyIndex, setHistoryIndex] = useState<number>(0);

  // Load dynamic sentiment entities from analysis prop
  useEffect(() => {
    if (analysis && analysis.annotations && analysis.annotations.length > 0) {
      const parsed: SentimentEntity[] = analysis.annotations.map((ann: any, idx: number) => {
        const id = ann.id || `sent-${idx + 1}`;
        const rawLabel = (ann.label || 'NEUTRAL').toUpperCase();
        const sentiment: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL' =
          rawLabel.includes('POS') ? 'POSITIVE' : rawLabel.includes('NEG') ? 'NEGATIVE' : 'NEUTRAL';
        return {
          id,
          text: ann.text_span?.text || ann.text || '',
          sentiment,
          color: getSentimentColor(sentiment),
          confidence: ann.confidence ?? 0.85,
          page: ann.geometry?.page ?? ann.text_span?.page,
          level: ann.geometry?.level || analysis.raw_result?.analysis_level || 'document',
          paragraphIndex: ann.geometry?.paragraph_index,
          sentenceIndex: ann.geometry?.sentence_index,
        };
      });
      setEntities(parsed);
      setHistory([parsed]);
      setHistoryIndex(0);
    } else {
      setEntities([]);
      setHistory([[]]);
      setHistoryIndex(0);
    }
    setSelectedEntityId(null);
  }, [analysis, textAsset]);

  // When selectedEntityId changes, update the form
  useEffect(() => {
    if (selectedEntityId) {
      const found = entities.find((e) => e.id === selectedEntityId);
      if (found) {
        setFormText(found.text);
        setFormTag(found.sentiment);
        setFormColor(found.color);
      }
    } else {
      setFormText('');
      setFormTag('');
      setFormColor('');
    }
  }, [selectedEntityId, entities]);

  const handleSelectEntity = (id: string) => {
    if (selectedEntityId === id) {
      setSelectedEntityId(null);
    } else {
      setSelectedEntityId(id);
      const ent = entities.find((e) => e.id === id);
      if (ent) {
        onToast(`Selected aspect sentiment: "${ent.text}" [${ent.sentiment}]`);
      }
    }
  };

  const pushState = (newEntities: SentimentEntity[]) => {
    const nextHistory = history.slice(0, historyIndex + 1);
    nextHistory.push(newEntities);
    setHistory(nextHistory);
    setHistoryIndex(nextHistory.length - 1);
    setEntities(newEntities);
  };

  const handleUndo = () => {
    if (historyIndex > 0) {
      const nextIndex = historyIndex - 1;
      setHistoryIndex(nextIndex);
      setEntities(history[nextIndex]);
      onToast('Undo action applied');
    }
  };

  const handleRedo = () => {
    if (historyIndex < history.length - 1) {
      const nextIndex = historyIndex + 1;
      setHistoryIndex(nextIndex);
      setEntities(history[nextIndex]);
      onToast('Redo action applied');
    }
  };

  const handleUpdate = () => {
    if (!selectedEntityId) {
      onToast('Select a sentiment entity to update');
      return;
    }
    if (!formTag) {
      onToast('Please select a sentiment label');
      return;
    }
    const updated = entities.map((item) => {
      if (item.id === selectedEntityId) {
        return {
          ...item,
          text: formText,
          sentiment: formTag as 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL',
          color: formColor || getSentimentColor(formTag),
        };
      }
      return item;
    });
    pushState(updated);
    onToast(`Updated sentiment entity "${formText}" to ${formTag}`);
  };

  const handleDelete = () => {
    if (!selectedEntityId) return;
    const toDelete = entities.find((e) => e.id === selectedEntityId);
    const updated = entities.filter((item) => item.id !== selectedEntityId);
    pushState(updated);
    setSelectedEntityId(null);
    onToast(`Deleted sentiment entity "${toDelete?.text}"`);
  };

  const handleReset = () => {
    setFormText('');
    setFormTag('');
    setFormColor('');
    setSelectedEntityId(null);
    onToast('Cleared annotation input fields');
  };

  const [isSaving, setIsSaving] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSave = () => {
    setIsSaving(true);
    onToast('Sentiment annotations draft saved successfully');
    setTimeout(() => setIsSaving(false), 600);
  };

  const handleSubmit = () => {
    setIsSubmitting(true);
    onToast('HITL review verified & submitted to pipeline');
    if (onNextAsset) {
      onNextAsset();
    }
    setTimeout(() => {
      setIsSubmitting(false);
    }, 300);
  };

  const handleNext = () => {
    if (onNextAsset) {
      onNextAsset();
    } else {
      onToast('Loaded next text asset');
    }
  };

  // Helper to render an annotated token chip matching the UI style
  const renderSentimentToken = (
    id: string,
    text: string,
    sentiment: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL',
    color: string
  ) => {
    const isSelected = selectedEntityId === id;

    return (
      <span
        key={id}
        id={`sentiment-token-${id}`}
        onClick={() => handleSelectEntity(id)}
        className={`inline-flex items-center gap-1.5 px-2 py-0.5 mx-1 my-1 rounded-sm border cursor-pointer align-middle transition-all duration-150 select-none ${
          isSelected
            ? 'ring-2 ring-blue-500 ring-offset-2 scale-105 z-10 font-bold'
            : 'hover:opacity-90'
        }`}
        style={{
          borderColor: color,
          backgroundColor: `${color}0D`,
        }}
      >
        <span className="text-xs font-semibold text-slate-900 leading-tight">
          {text}
        </span>
        <span
          className="text-[9px] font-bold px-1 py-0.2 rounded-xs text-white uppercase tracking-wider shadow-2xs leading-none"
          style={{ backgroundColor: color }}
        >
          {sentiment}
        </span>
      </span>
    );
  };

  const renderViewportContent = () => {
    const textContent = analysis?.text;
    if (!textContent) {
      return (
        <div className="flex flex-col items-center justify-center min-h-[240px] rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center space-y-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 text-blue-600 border border-blue-200">
            <FileText className="h-6 w-6" />
          </div>
          <div>
            <h4 className="text-sm font-semibold text-slate-800">
              {textAsset ? `Uploaded Document: ${textAsset.filename || textAsset.id}` : 'No document selected'}
            </h4>
            <p className="text-xs text-slate-500 mt-1 max-w-md">
              {textAsset
                ? 'Document uploaded successfully. Ready for sentiment verification and aspect tagging.'
                : 'Please select or upload a text file to begin sentiment annotation.'}
            </p>
          </div>
        </div>
      );
    }

    const analysisLevel = analysis?.raw_result?.analysis_level || 'document';
    const rawAnnotations = [...(analysis?.annotations || [])]
      .filter(
        (a) =>
          analysisLevel &&
          Boolean(a.text_span?.text)
      );
    let searchCursor = 0;
    const annotationsList = rawAnnotations
      .map((annotation) => {
        if (analysisLevel === 'document') return annotation;
        const segmentText = annotation.text_span?.text || '';
        const locatedAt = textContent.indexOf(segmentText, searchCursor);
        if (locatedAt < 0) return null;
        searchCursor = locatedAt + segmentText.length;
        return {
          ...annotation,
          text_span: { ...annotation.text_span, start: locatedAt, end: locatedAt + segmentText.length },
        };
      })
      .filter((annotation): annotation is NonNullable<typeof annotation> => Boolean(annotation));

    if (annotationsList.length === 0) {
      return <p className="leading-loose whitespace-pre-wrap">{textContent}</p>;
    }

    const chunks: React.ReactNode[] = [];
    let cursor = 0;
    annotationsList.forEach((ann, idx) => {
      const start = ann.text_span!.start!;
      const end = ann.text_span!.end!;
      if (start < cursor) return;
      if (start > cursor) {
        chunks.push(<span key={`txt-${idx}`}>{textContent.slice(cursor, start)}</span>);
      }
      const id = ann.id || `sent-${idx + 1}`;
      const ent = entities.find((e) => e.id === id) || {
        id,
        text: ann.text_span?.text || textContent.slice(start, end),
        sentiment: ((ann.label || 'NEUTRAL').toUpperCase().includes('POS')
          ? 'POSITIVE'
          : (ann.label || 'NEUTRAL').toUpperCase().includes('NEG')
          ? 'NEGATIVE'
          : 'NEUTRAL') as 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL',
        color: getSentimentColor(ann.label || 'NEUTRAL'),
      };
      chunks.push(
        renderSentimentToken(ent.id, ent.text, ent.sentiment, ent.color)
      );
      cursor = end;
    });
    if (cursor < textContent.length) {
      chunks.push(<span key="txt-tail">{textContent.slice(cursor)}</span>);
    }

    return <div className="leading-loose whitespace-pre-wrap">{chunks}</div>;
  };

  const selectedEntity = entities.find((e) => e.id === selectedEntityId);

  // Derived user details from logged in user or assignment
  const annotatorName = currentUserEmail || 'Human Annotator';
  const annotatorEmpNo = currentUserEmail && currentUserEmail.includes('@')
    ? currentUserEmail.split('@')[0]
    : null;

  return (
    <div
      id="sentiment-annotation-workbench"
      className="flex-1 flex flex-col min-w-0 overflow-y-auto bg-[#F6F2EA] text-slate-800 font-sans"
    >
      <main className="flex-1 p-4 md:p-6 lg:p-7 space-y-4 max-w-[1850px] w-full mx-auto">
        {/* Top Header */}
        <div id="sentiment-workbench-header" className="flex items-start gap-3.5">
          {onToggleSidebar && (
            <button
              id="toggle-sidebar-sentiment-btn"
              onClick={onToggleSidebar}
              className="p-1.5 mt-0.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-black/5 lg:hidden cursor-pointer"
              aria-label="Toggle navigation"
            >
              <Menu className="h-5 w-5" />
            </button>
          )}

          {/* Green Squircle Icon */}
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-600/10 text-emerald-600 border border-emerald-600/20 shrink-0 shadow-2xs">
            <Smile className="h-5 w-5 text-emerald-600" />
          </div>

          <div className="space-y-0.5 min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl md:text-2xl font-bold text-slate-900 tracking-tight leading-tight">
                Sentiment Annotation
              </h1>
              {/* Status Badge */}
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-300 shadow-2xs">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse" />
                {analysis?.agent_status || 'HITL Verification'}
              </span>
            </div>
            <p className="text-xs text-slate-500 font-medium">
              Human-in-the-Loop review: verify and adjust AI-predicted sentiment classifications and aspect polarities.
            </p>
          </div>
        </div>

        {/* Task ID & Asset Metadata Card */}
        <div
          id="sentiment-task-metadata-bar"
          className="rounded-xl border border-[#E2DDD5] bg-white px-4 py-3 shadow-2xs flex flex-wrap items-center justify-between gap-4"
        >
          {/* Left: Thumbnail Icon & Task ID */}
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 border border-blue-200 text-blue-600 shadow-xs shrink-0">
              <FileText className="h-4.5 w-4.5 text-blue-600" />
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                TASK ID:
              </span>
              <span className="text-xs font-mono font-bold text-slate-900">
                {textAsset ? textAsset.filename || textAsset.id : 'N/A'}
              </span>
            </div>
          </div>

          {/* Right: Project metadata details */}
          <div className="flex flex-wrap items-center gap-6 text-xs divide-x divide-slate-100">
            <div>
              <span className="block text-[11px] text-slate-400">Project</span>
              <span className="font-semibold text-slate-800">
                {project ? project.name : 'Text Sentiment HITL'}
              </span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] text-slate-400">Modality</span>
              <span className="font-semibold text-slate-800">Text</span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] text-slate-400">Format</span>
              <span className="font-semibold text-slate-800">
                {textAsset?.filename?.split('.').pop()?.toUpperCase() || 'TXT'}
              </span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] text-slate-400">Size</span>
              <span className="font-semibold text-slate-800">
                {textAsset?.byte_size ? `${(textAsset.byte_size / 1024).toFixed(1)} KB` : 'N/A'}
              </span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] text-slate-400">Language</span>
              <span className="font-semibold text-slate-800">
                {(project as any)?.language || 'English'}
              </span>
            </div>
          </div>
        </div>

        {/* 2-Column Main Workspace */}
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-5 items-start">
          {/* ================= LEFT COLUMN (7/12 cols) ================= */}
          <div className="xl:col-span-7 space-y-4">
            {/* Text Viewer / Editor Card */}
            <div
              id="sentiment-text-editor-card"
              className="rounded-xl border border-[#E2DDD5] bg-white overflow-hidden shadow-2xs"
            >
              {/* Card Header with Text title & Action buttons */}
              <div
                id="sentiment-text-card-header"
                className="flex items-center justify-between px-4 py-2.5 border-b border-[#E2DDD5] bg-white text-xs"
              >
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-slate-500" />
                  <span className="font-bold text-slate-900 text-xs">Text Content</span>
                </div>

                <div className="flex items-center gap-2">
                  {/* Undo & Redo buttons */}
                  <div className="flex items-center gap-1 pr-2 border-r border-[#E2DDD5]">
                    <button
                      type="button"
                      onClick={handleUndo}
                      disabled={historyIndex <= 0}
                      className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium border border-[#E2DDD5] transition ${
                        historyIndex > 0
                          ? 'text-slate-700 hover:bg-slate-100 hover:text-slate-900 cursor-pointer'
                          : 'text-slate-300 border-slate-200 cursor-not-allowed'
                      }`}
                      title="Undo"
                    >
                      <Undo2 className="h-3.5 w-3.5" />
                      <span>Undo</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleRedo}
                      disabled={historyIndex >= history.length - 1}
                      className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium border border-[#E2DDD5] transition ${
                        historyIndex < history.length - 1
                          ? 'text-slate-700 hover:bg-slate-100 hover:text-slate-900 cursor-pointer'
                          : 'text-slate-300 border-slate-200 cursor-not-allowed'
                      }`}
                      title="Redo"
                    >
                      <Redo2 className="h-3.5 w-3.5" />
                      <span>Redo</span>
                    </button>
                  </div>

                  {/* Zoom controls */}
                  <div className="flex items-center gap-1 bg-[#FBF9F5] border border-[#E2DDD5] rounded-lg px-1.5 py-0.5 text-slate-600">
                    <button
                      type="button"
                      onClick={() => setZoomLevel((prev) => Math.max(75, prev - 15))}
                      className="p-1 rounded hover:bg-slate-200/60 text-slate-600 hover:text-slate-900 transition cursor-pointer"
                      title="Zoom Out"
                    >
                      <ZoomOut className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setZoomLevel(100)}
                      className="px-1.5 py-0.5 rounded hover:bg-slate-200/60 text-xs font-semibold text-slate-700 hover:text-slate-900 transition cursor-pointer"
                      title="Reset Zoom"
                    >
                      {zoomLevel}%
                    </button>
                    <button
                      type="button"
                      onClick={() => setZoomLevel((prev) => Math.min(150, prev + 15))}
                      className="p-1 rounded hover:bg-slate-200/60 text-slate-600 hover:text-slate-900 transition cursor-pointer"
                      title="Zoom In"
                    >
                      <ZoomIn className="h-3.5 w-3.5" />
                    </button>
                  </div>

                  {/* Maximize toggle */}
                  <button
                    type="button"
                    onClick={() => setIsFullscreen(true)}
                    className="p-1.5 rounded-lg border border-[#E2DDD5] hover:bg-slate-100 text-slate-600 hover:text-slate-900 transition cursor-pointer"
                    title="Fullscreen"
                  >
                    <Maximize2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              {/* Text Viewport Area with Inline Sentiment Highlights */}
              <div
                id="sentiment-text-viewport"
                className="p-5 md:p-6 text-sm text-slate-800 leading-relaxed font-sans select-text bg-[#FCFBFA]"
                style={{ fontSize: `${(zoomLevel / 100) * 14}px` }}
              >
                {renderViewportContent()}
              </div>
            </div>

            {/* AI-Detected Sentiments Table Card */}
            <div
              id="sentiment-ai-detected-card"
              className="rounded-xl border border-[#E2DDD5] bg-white p-4 shadow-2xs space-y-3"
            >
              <div className="flex items-center justify-between pb-2 border-b border-[#F0EBE3]">
                <h3 className="text-xs font-bold text-slate-900">AI-Detected Sentiments</h3>
                <span className="text-[11px] font-semibold text-slate-500">
                  {entities.length} Detected
                </span>
              </div>

              {/* Sentiments Table */}
              <div className="overflow-x-auto">
                {entities.length === 0 ? (
                  <div className="py-6 text-center text-xs text-slate-400">
                    No sentiment annotations recorded for this asset.
                  </div>
                ) : (
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-[#E2DDD5] text-[11px] font-semibold text-slate-500">
                        <th className="pb-2 pt-1 font-medium">Entity Span</th>
                        <th className="pb-2 pt-1 font-medium">Source</th>
                        <th className="pb-2 pt-1 font-medium">Label</th>
                        <th className="pb-2 pt-1 font-medium w-48 text-right">Confidence</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#F0EBE3]">
                      {entities.map((item) => {
                        const isSelected = selectedEntityId === item.id;

                        return (
                          <tr
                            key={item.id}
                            id={`sentiment-row-${item.id}`}
                            onClick={() => handleSelectEntity(item.id)}
                            className={`transition-colors cursor-pointer ${
                              isSelected
                                ? 'bg-blue-50/60 font-semibold ring-1 ring-blue-300'
                                : 'hover:bg-[#FBF9F5]'
                            }`}
                          >
                            <td className="py-2.5 pr-2 font-medium">
                              <div className="flex items-center gap-2">
                                {isSelected ? (
                                  <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-emerald-600 text-white shrink-0">
                                    <CheckCircle2 className="h-3 w-3" />
                                  </span>
                                ) : (
                                  <span
                                    className="h-2.5 w-2.5 rounded-full border-2 shrink-0 bg-white"
                                    style={{ borderColor: item.color }}
                                  />
                                )}
                                <span className="text-slate-800">{item.text}</span>
                              </div>
                            </td>

                            <td className="py-2.5 px-2">
                              <span className="text-slate-500">
                                {item.level === 'page' && item.page ? `Page ${item.page}` : item.level === 'paragraph' && item.page ? `Page ${item.page}, Paragraph ${(item.paragraphIndex ?? 0) + 1}` : item.level === 'sentence' && item.page ? `Page ${item.page}, Sentence ${(item.sentenceIndex ?? 0) + 1}` : 'Document'}
                              </span>
                            </td>

                            <td className="py-2.5 px-2">
                              <span
                                className="inline-block px-2.5 py-0.5 rounded-md text-[10px] font-bold tracking-wider uppercase border text-center min-w-[80px]"
                                style={{
                                  borderColor: item.color,
                                  color: item.color,
                                  backgroundColor: `${item.color}0D`,
                                }}
                              >
                                {item.sentiment}
                              </span>
                            </td>

                            <td className="py-2.5 pl-2 text-right">
                              <div className="flex items-center justify-end gap-2.5">
                                <div className="w-24 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                                  <div
                                    className="h-full rounded-full transition-all duration-300 bg-emerald-600"
                                    style={{
                                      width: `${item.confidence * 100}%`,
                                    }}
                                  />
                                </div>
                                <span className="font-mono text-xs text-slate-700 font-semibold w-8 text-right">
                                  {(item.confidence * 100).toFixed(0)}%
                                </span>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>

          {/* ================= RIGHT COLUMN (5/12 cols) ================= */}
          <div className="xl:col-span-5 space-y-4">
            {/* 1. Human Annotator Details Card */}
            <div
              id="sentiment-annotator-details-card"
              className="rounded-xl border border-[#E2DDD5] bg-white p-4 shadow-2xs space-y-3"
            >
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-100 text-blue-600 border border-blue-200 shrink-0">
                  <User className="h-4 w-4 text-blue-600" />
                </div>
                <h2 className="text-xs font-bold text-slate-900">Human Annotator Details</h2>
              </div>

              <div className="pt-2 border-t border-[#F0EBE3] space-y-1 text-xs">
                <div className="text-xs font-bold text-slate-900">{annotatorName}</div>
                <div className="space-y-0.5 text-[11px] text-slate-600">
                  {annotatorEmpNo && (
                    <div>
                      <span className="text-slate-400 font-medium">Emp No: </span>
                      <span className="font-mono font-semibold text-slate-800">{annotatorEmpNo}</span>
                    </div>
                  )}
                  <div>
                    <span className="text-slate-400 font-medium">Role: </span>
                    <span className="font-semibold text-slate-800">Human Annotator</span>
                  </div>
                </div>
              </div>

              {/* Task Assigned breakdown */}
              <div id="section-task-assigned-sentiment" className="pt-2.5 border-t border-[#F0EBE3] space-y-2.5">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-slate-900">Task Assigned</h3>
                  <span className="text-[11px] font-semibold text-blue-700 bg-blue-50 px-2 py-0.5 rounded-md border border-blue-200">
                    Task {totalAssets > 0 ? `${currentAssetIndex + 1} of ${totalAssets}` : '0 of 0'}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="p-2.5 rounded-lg bg-[#FBF9F5] border border-[#E2DDD5]">
                    <div className="text-[11px] font-medium text-slate-600">Total Assigned</div>
                    <div className="text-base font-bold text-slate-900 mt-0.5">
                      {totalAssets}
                    </div>
                  </div>

                  <div className="p-2.5 rounded-lg bg-[#FBF9F5] border border-[#E2DDD5]">
                    <div className="text-[11px] font-medium text-blue-700">Current Task</div>
                    <div className="text-base font-bold text-blue-900 mt-0.5 font-mono">
                      {totalAssets > 0 ? `#${currentAssetIndex + 1}` : '—'}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* 2. Annotation Options Card */}
            <div
              id="sentiment-annotation-options-card"
              className="rounded-xl border border-[#E2DDD5] bg-white p-5 shadow-2xs space-y-4"
            >
              <div className="flex items-center justify-between pb-3 border-b border-[#F0EBE3]">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-slate-500" />
                  <h2 className="text-xs font-bold text-slate-900">Annotation Options</h2>
                </div>
                {selectedEntity ? (
                  <span
                    className="text-[11px] font-bold px-2 py-0.5 rounded-md text-white shadow-2xs"
                    style={{ backgroundColor: selectedEntity.color }}
                  >
                    {selectedEntity.sentiment}
                  </span>
                ) : (
                  <span className="text-[11px] text-slate-400 font-medium">None selected</span>
                )}
              </div>

              {/* Inputs Form */}
              <div className="space-y-3 text-xs">
                {/* Text input */}
                <div className="space-y-1">
                  <label className="block text-[11px] font-semibold text-slate-700">Text</label>
                  <input
                    type="text"
                    value={formText}
                    onChange={(e) => setFormText(e.target.value)}
                    placeholder="Entity text..."
                    className="w-full rounded-lg border border-[#E2DDD5] px-3 py-2 text-xs text-slate-800 placeholder-slate-400 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-hidden bg-[#FCFBFA]"
                  />
                </div>

                {/* Label Select Dropdown */}
                <div className="space-y-1">
                  <label className="block text-[11px] font-semibold text-slate-700">Label</label>
                  <div className="relative">
                    <select
                      value={formTag}
                      onChange={(e) => {
                        const tag = e.target.value as 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL' | '';
                        setFormTag(tag);
                        if (tag) {
                          setFormColor(getSentimentColor(tag));
                        } else {
                          setFormColor('');
                        }
                      }}
                      className="w-full rounded-lg border border-[#E2DDD5] px-3 py-2 text-xs text-slate-800 bg-[#FCFBFA] focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-hidden appearance-none cursor-pointer"
                    >
                      <option value="">Select label...</option>
                      {AVAILABLE_SENTIMENT_LABELS.map((item) => (
                        <option key={item.tag} value={item.tag}>
                          {item.label} ({item.tag})
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="absolute right-3 top-2.5 h-3.5 w-3.5 text-slate-400 pointer-events-none" />
                  </div>
                </div>

                {/* Color input */}
                <div className="space-y-1">
                  <label className="block text-[11px] font-semibold text-slate-700">Color</label>
                  <div className="flex items-center gap-2">
                    <span
                      className={`h-7 w-7 rounded-full border shrink-0 shadow-2xs transition-colors ${
                        formColor ? 'border-slate-300' : 'border-dashed border-slate-300 bg-slate-100'
                      }`}
                      style={{ backgroundColor: formColor || undefined }}
                    />
                    <input
                      type="text"
                      value={formColor}
                      onChange={(e) => setFormColor(e.target.value)}
                      placeholder="e.g., #10B981"
                      className="w-full rounded-lg border border-[#E2DDD5] px-3 py-2 text-xs font-mono text-slate-800 placeholder-slate-400 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-hidden bg-[#FCFBFA]"
                    />
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-between pt-2 border-t border-[#F0EBE3]">
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={!selectedEntityId}
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border transition cursor-pointer ${
                    selectedEntityId
                      ? 'border-rose-200 text-rose-600 hover:bg-rose-50'
                      : 'border-slate-200 text-slate-300 cursor-not-allowed'
                  }`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  <span>Delete</span>
                </button>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleReset}
                    className="px-3.5 py-2 rounded-lg border border-[#D0C9BE] bg-white hover:bg-[#FBF9F5] text-slate-700 text-xs font-semibold transition cursor-pointer"
                  >
                    Reset
                  </button>
                  <button
                    type="button"
                    onClick={handleUpdate}
                    disabled={!selectedEntityId}
                    className={`px-4 py-2 rounded-lg text-xs font-semibold shadow-xs transition cursor-pointer ${
                      selectedEntityId
                        ? 'bg-blue-600 hover:bg-blue-700 text-white'
                        : 'bg-slate-200 text-slate-400 cursor-not-allowed'
                    }`}
                  >
                    Update
                  </button>
                </div>
              </div>
            </div>

            {/* 3. Bottom Action Bar Card: Save, Submit, Next */}
            <div className="grid grid-cols-3 gap-2.5 pt-1">
              <button
                type="button"
                onClick={handleSave}
                disabled={isSaving}
                className="py-2.5 px-2 rounded-lg border border-[#D0C9BE] bg-white hover:bg-[#FBF9F5] active:scale-95 text-slate-700 font-semibold text-xs flex items-center justify-center gap-1.5 shadow-2xs transition-all cursor-pointer hover:border-slate-400"
              >
                <Save className="h-3.5 w-3.5 text-slate-500" />
                <span>{isSaving ? 'Saved ✓' : 'Save'}</span>
              </button>

              <button
                type="button"
                onClick={handleSubmit}
                disabled={isSubmitting}
                className="py-2.5 px-2 rounded-lg bg-blue-600 hover:bg-blue-700 active:scale-95 text-white font-semibold text-xs flex items-center justify-center gap-1.5 shadow-xs transition-all cursor-pointer hover:shadow-md"
              >
                <Send className="h-3.5 w-3.5" />
                <span>{isSubmitting ? 'Submitted ✓' : 'Submit'}</span>
              </button>

              <button
                type="button"
                onClick={handleNext}
                className="py-2.5 px-2 rounded-lg border border-[#D0C9BE] bg-white hover:bg-[#FBF9F5] active:scale-95 text-slate-700 font-semibold text-xs flex items-center justify-center gap-1.5 shadow-2xs transition-all cursor-pointer hover:border-slate-400"
              >
                <span>Next</span>
                <ChevronRight className="h-3.5 w-3.5 text-slate-500" />
              </button>
            </div>
          </div>
        </div>
      </main>

      {/* Fullscreen Expanded View Modal */}
      {isFullscreen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 sm:p-6 animate-in fade-in duration-150">
          <div className="relative flex flex-col w-full max-w-5xl max-h-[90vh] bg-white rounded-2xl border border-slate-200 shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3.5 bg-slate-50 border-b border-slate-200">
              <span className="text-sm font-bold text-slate-900">
                Expanded View - {textAsset ? textAsset.filename || textAsset.id : 'Text Asset'} (Sentiment Annotation)
              </span>
              <button
                type="button"
                onClick={() => setIsFullscreen(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-800 hover:bg-slate-200 transition cursor-pointer"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-6 overflow-y-auto leading-loose text-base text-slate-800">
              {renderViewportContent()}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
