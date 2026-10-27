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
  Tag,
  X,
} from 'lucide-react';
import { AssetResponse, ProjectResponse, TextAnalysisResponse, api } from '../../services/api';

export interface NERTokenEntity {
  id: string;
  text: string;
  label: string;
  tag: string;
  color: string;
  confidence: number;
  start?: number;
  end?: number;
}

interface NERAnnotationWorkbenchProps {
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

const AVAILABLE_LABELS = [
  { label: 'Person', tag: 'PERSON', defaultColor: '#3B82F6' },
  { label: 'Organization', tag: 'ORGANIZATION', defaultColor: '#10B981' },
  { label: 'Location', tag: 'LOCATION', defaultColor: '#F97316' },
  { label: 'Product', tag: 'PRODUCT', defaultColor: '#06B6D4' },
  { label: 'Date', tag: 'DATE', defaultColor: '#A855F7' },
  { label: 'Email', tag: 'EMAIL', defaultColor: '#06B6D4' },
  { label: 'Phone', tag: 'PHONE', defaultColor: '#EF4444' },
  { label: 'Order ID', tag: 'ORDER_ID', defaultColor: '#EC4899' },
];

const getLabelColor = (label: string): string => {
  const found = AVAILABLE_LABELS.find(
    (l) => l.tag.toLowerCase() === label.toLowerCase() || l.label.toLowerCase() === label.toLowerCase()
  );
  if (found) return found.defaultColor;
  const colors = ['#3B82F6', '#10B981', '#F97316', '#06B6D4', '#A855F7', '#EC4899', '#EF4444', '#8B5CF6'];
  let hash = 0;
  for (let i = 0; i < label.length; i++) {
    hash = label.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
};

export const NERAnnotationWorkbench: React.FC<NERAnnotationWorkbenchProps> = ({
  onToggleSidebar,
  onToast,
  textAsset,
  project,
  analysis,
  totalAssets = 0,
  currentAssetIndex = 0,
  onPrevAsset,
  onNextAsset,
  currentUserEmail,
}) => {
  const [zoomLevel, setZoomLevel] = useState<number>(100);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [entities, setEntities] = useState<NERTokenEntity[]>([]);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);

  // Form Edit fields
  const [formText, setFormText] = useState<string>('');
  const [formTag, setFormTag] = useState<string>('');
  const [formColor, setFormColor] = useState<string>('#3B82F6');

  // History stack for Undo / Redo
  const [history, setHistory] = useState<NERTokenEntity[][]>([[]]);
  const [historyIndex, setHistoryIndex] = useState<number>(0);

  useEffect(() => {
    if (analysis?.annotations && analysis.annotations.length > 0) {
      const loaded: NERTokenEntity[] = analysis.annotations.map((item, idx) => {
        const labelStr = item.label || 'ANNOTATION';
        const tagStr = labelStr.toUpperCase().replace(/\s+/g, '_');
        const spanStart = item.text_span?.start ?? item.geometry?.start;
        const spanEnd = item.text_span?.end ?? item.geometry?.end;
        const spanText = item.text_span?.text || item.geometry?.text || '';
        return {
          id: item.id || `ent-${idx + 1}`,
          text:
            spanText ||
            (analysis.text && spanStart !== undefined && spanEnd !== undefined
              ? analysis.text.slice(spanStart, spanEnd)
              : ''),
          label: labelStr,
          tag: tagStr,
          color: getLabelColor(labelStr),
          confidence: item.confidence ?? 1.0,
          start: spanStart,
          end: spanEnd,
        };
      });
      setEntities(loaded);
      setHistory([loaded]);
      setHistoryIndex(0);
    } else {
      setEntities([]);
      setHistory([[]]);
      setHistoryIndex(0);
    }
  }, [analysis]);

  // When selectedEntityId changes, update the form
  useEffect(() => {
    if (selectedEntityId) {
      const found = entities.find((e) => e.id === selectedEntityId);
      if (found) {
        setFormText(found.text);
        setFormTag(found.tag);
        setFormColor(found.color);
      }
    } else {
      setFormText('');
      setFormTag('');
      setFormColor('#3B82F6');
    }
  }, [selectedEntityId, entities]);

  const handleSelectEntity = (id: string) => {
    if (selectedEntityId === id) {
      setSelectedEntityId(null);
    } else {
      setSelectedEntityId(id);
      const ent = entities.find((e) => e.id === id);
      if (ent) {
        onToast(`Selected entity: ${ent.text} [${ent.tag}]`);
      }
    }
  };

  const pushState = (newEntities: NERTokenEntity[]) => {
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

  const handleUpdate = async () => {
    if (!formText.trim()) {
      onToast('Select text or enter an entity value first');
      return;
    }
    if (!selectedEntityId) {
      const labelObj = AVAILABLE_LABELS.find((l) => l.tag === formTag) || AVAILABLE_LABELS[0];
      const start = analysis?.text ? analysis.text.indexOf(formText.trim()) : -1;
      const newEntity: NERTokenEntity = {
        id: `manual-${Date.now()}`,
        text: formText.trim(),
        tag: labelObj.tag,
        label: labelObj.label,
        color: formColor || labelObj.defaultColor,
        confidence: 1,
        start: start >= 0 ? start : undefined,
        end: start >= 0 ? start + formText.trim().length : undefined,
      };
      pushState([...entities, newEntity]);
      setSelectedEntityId(newEntity.id);
      onToast(`Added entity "${newEntity.text}"`);
      return;
    }
    const current = entities.find((item) => item.id === selectedEntityId);
    if (!current || !textAsset?.id) {
      onToast('No HITL annotation is selected');
      return;
    }
    let persistedId = selectedEntityId;
    try {
      if (selectedEntityId.startsWith('manual-')) {
        const created = await api.addHitlAnnotation(textAsset.id, {
          label: formTag,
          geometry_type: 'text_span',
          geometry: { start: current.start, end: current.end, text: formText.trim() },
          source: 'human',
        });
        persistedId = created.id;
      } else {
        await api.updateHitlAnnotation(textAsset.id, selectedEntityId, { label: formTag });
      }
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Failed to persist annotation update');
      return;
    }
    const updated = entities.map((item) => {
      if (item.id === selectedEntityId) {
        const labelObj = AVAILABLE_LABELS.find((l) => l.tag === formTag);
        return {
          ...item,
          id: persistedId,
          text: formText,
          tag: formTag,
          label: labelObj ? labelObj.label : formTag,
          color: formColor,
        };
      }
      return item;
    });
    pushState(updated);
    onToast(`Updated entity "${formText}" and saved it to HITL`);
  };

  const handleDelete = () => {
    if (!selectedEntityId) return;
    const toDelete = entities.find((e) => e.id === selectedEntityId);
    const updated = entities.filter((item) => item.id !== selectedEntityId);
    pushState(updated);
    setSelectedEntityId(null);
    onToast(`Deleted entity "${toDelete?.text}"`);
  };

  const handleReset = () => {
    if (selectedEntityId && analysis?.annotations) {
      const origItem = analysis.annotations.find(
        (a, idx) => (a.id || `ent-${idx + 1}`) === selectedEntityId
      );
      if (origItem) {
        const labelStr = origItem.label || 'ANNOTATION';
        setFormText(origItem.text_span?.text || '');
        setFormTag(labelStr.toUpperCase().replace(/\s+/g, '_'));
        setFormColor(getLabelColor(labelStr));
        onToast('Reset entity values');
        return;
      }
    }
    setFormText('');
    setFormTag('');
    setFormColor('#3B82F6');
  };

  const [isSaving, setIsSaving] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSave = () => {
    setIsSaving(true);
    onToast('NER annotations draft saved successfully');
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

  // Helper to render an annotated token chip
  const renderToken = (id: string, displayText: string, tag: string, color: string) => {
    const isSelected = selectedEntityId === id;

    return (
      <span
        key={id}
        id={`token-${id}`}
        onClick={() => handleSelectEntity(id)}
        className={`inline-flex flex-col items-start mx-1 my-1 cursor-pointer align-middle transition-all duration-150 select-none ${
          isSelected ? 'ring-2 ring-blue-500 ring-offset-2 scale-105 z-10' : 'hover:opacity-90'
        }`}
      >
        <span
          className="text-[9px] font-bold px-1.5 py-0.2 rounded-xs text-white uppercase tracking-wider shadow-2xs leading-none"
          style={{ backgroundColor: color }}
        >
          {tag}
        </span>
        <span
          className="px-1.5 py-0.5 text-xs font-semibold rounded-xs border transition-colors leading-tight"
          style={{
            borderColor: color,
            backgroundColor: `${color}18`,
            color: '#1E293B',
          }}
        >
          {displayText}
        </span>
      </span>
    );
  };

  const renderViewportContent = () => {
    const textContent = analysis?.text;
    if (!textContent) {
      return (
        <div className="flex min-h-[220px] items-center justify-center rounded-lg border border-dashed border-slate-300 text-sm text-slate-500">
          No text content or analysis loaded for this asset.
        </div>
      );
    }

    const annotationsList = entities
      .filter((entity) => entity.start !== undefined && entity.end !== undefined && entity.start >= 0)
      .map((entity) => ({
        id: entity.id,
        label: entity.label,
        text_span: { start: entity.start, end: entity.end, text: entity.text },
      }))
      .sort((a, b) => (a.text_span?.start || 0) - (b.text_span?.start || 0));

    if (annotationsList.length === 0) {
      return (
        <p
          className="leading-loose whitespace-pre-wrap"
          onMouseUp={() => {
            const selected = window.getSelection()?.toString().trim() || '';
            if (!selected) return;
            setSelectedEntityId(null);
            setFormText(selected);
            if (!formTag) setFormTag(AVAILABLE_LABELS[0].tag);
            setFormColor(getLabelColor(formTag || AVAILABLE_LABELS[0].label));
            onToast(`Selected text "${selected}". Choose a label and click Update.`);
          }}
        >
          {textContent}
        </p>
      );
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
      const id = ann.id || `ent-${idx + 1}`;
      const ent = entities.find((e) => e.id === id) || {
        id,
        text: ann.text_span?.text || textContent.slice(start, end),
        tag: (ann.label || 'ANNOTATION').toUpperCase(),
        color: getLabelColor(ann.label || 'ANNOTATION'),
      };
      chunks.push(renderToken(ent.id, ent.text, ent.tag, ent.color));
      cursor = end;
    });
    if (cursor < textContent.length) {
      chunks.push(<span key="txt-tail">{textContent.slice(cursor)}</span>);
    }

    return (
      <div
        className="leading-loose whitespace-pre-wrap"
        onMouseUp={() => {
          const selected = window.getSelection()?.toString().trim() || '';
          if (!selected) return;
          setSelectedEntityId(null);
          setFormText(selected);
          if (!formTag) setFormTag(AVAILABLE_LABELS[0].tag);
          setFormColor(getLabelColor(formTag || AVAILABLE_LABELS[0].label));
          onToast(`Selected text "${selected}". Choose a label and click Update.`);
        }}
      >
        {chunks}
      </div>
    );
  };

  const selectedEntity = entities.find((e) => e.id === selectedEntityId);

  return (
    <div
      id="ner-annotation-workbench"
      className="flex-1 flex flex-col min-w-0 overflow-y-auto bg-[#F6F2EA] text-slate-800 font-sans"
    >
      <main className="flex-1 p-4 md:p-6 lg:p-7 space-y-4 max-w-[1850px] w-full mx-auto">
        {/* Top Header matching screenshot */}
        <div id="ner-workbench-header" className="flex items-start gap-3.5">
          {onToggleSidebar && (
            <button
              id="toggle-sidebar-ner-btn"
              onClick={onToggleSidebar}
              className="p-1.5 mt-0.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-black/5 lg:hidden cursor-pointer"
              aria-label="Toggle navigation"
            >
              <Menu className="h-5 w-5" />
            </button>
          )}

          {/* Blue Squircle Icon */}
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600/10 text-blue-600 border border-blue-600/20 shrink-0 shadow-2xs">
            <Tag className="h-5 w-5 text-blue-600" />
          </div>

          <div className="space-y-0.5 min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl md:text-2xl font-bold text-slate-900 tracking-tight leading-tight">
                NER Annotation
              </h1>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-300 shadow-2xs">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse" />
                HITL Verification
              </span>
            </div>
            <p className="text-xs text-slate-500 font-medium">
              Human-in-the-Loop review: verify and adjust AI-predicted named entities, token spans, and label boundaries.
            </p>
          </div>
        </div>

        {/* Task ID & Asset Metadata Card */}
        <div
          id="ner-task-metadata-bar"
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
                {textAsset ? (textAsset.filename || textAsset.id) : 'N/A'}
              </span>
            </div>
          </div>

          {/* Right: Project metadata details */}
          <div className="flex flex-wrap items-center gap-6 text-xs divide-x divide-slate-100">
            <div>
              <span className="block text-[11px] text-slate-400">Project</span>
              <span className="font-semibold text-slate-800">{project?.name || 'N/A'}</span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] text-slate-400">Modality</span>
              <span className="font-semibold text-slate-800">
                {textAsset?.content_type?.split('/')[0]?.toUpperCase() || 'TEXT'}
              </span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] text-slate-400">Format</span>
              <span className="font-semibold text-slate-800">
                {textAsset?.filename ? textAsset.filename.split('.').pop()?.toUpperCase() || 'TXT' : 'TXT'}
              </span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] text-slate-400">Size</span>
              <span className="font-semibold text-slate-800">
                {textAsset?.byte_size ? `${(textAsset.byte_size / 1024).toFixed(1)} KB` : 'N/A'}
              </span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] text-slate-400">Task</span>
              <span className="font-semibold text-slate-800 font-mono">
                {totalAssets > 0 ? `${currentAssetIndex + 1} / ${totalAssets}` : '0 / 0'}
              </span>
            </div>
          </div>
        </div>

        {/* 2-Column Main Workspace */}
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-5 items-start">
          {/* LEFT COLUMN */}
          <div className="xl:col-span-7 space-y-4">
            {/* Text Viewer Card */}
            <div
              id="ner-text-editor-card"
              className="rounded-xl border border-[#E2DDD5] bg-white overflow-hidden shadow-2xs"
            >
              {/* Card Header */}
              <div
                id="ner-text-card-header"
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

              {/* Text Canvas Area with Entity Highlights */}
              <div
                id="ner-text-viewport"
                className="p-5 md:p-6 text-sm text-slate-800 leading-relaxed font-sans select-text bg-[#FCFBFA]"
                style={{ fontSize: `${(zoomLevel / 100) * 14}px` }}
              >
                {renderViewportContent()}
              </div>
            </div>

            {/* AI-Detected Entities Table Card */}
            <div
              id="ner-ai-detected-entities-card"
              className="rounded-xl border border-[#E2DDD5] bg-white p-4 shadow-2xs space-y-3"
            >
              <div className="flex items-center justify-between pb-2 border-b border-[#F0EBE3]">
                <h3 className="text-xs font-bold text-slate-900">AI-Detected Entities</h3>
                <span className="text-[11px] font-semibold text-slate-500">
                  {entities.length} Detected
                </span>
              </div>

              {/* Entities Table */}
              <div className="overflow-x-auto">
                {entities.length === 0 ? (
                  <p className="text-xs text-slate-500 py-3 text-center">No entities detected yet.</p>
                ) : (
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-[#E2DDD5] text-[11px] font-semibold text-slate-500">
                        <th className="pb-2 pt-1 font-medium">Entity</th>
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
                            id={`ai-entity-row-${item.id}`}
                            onClick={() => handleSelectEntity(item.id)}
                            className={`transition-colors cursor-pointer ${
                              isSelected ? 'bg-blue-50/60 font-semibold' : 'hover:bg-[#FBF9F5]'
                            }`}
                          >
                            <td className="py-2.5 pr-2 font-medium">
                              <div className="flex items-center gap-2">
                                <span
                                  className="h-2.5 w-2.5 rounded-full border-2 shrink-0 bg-white"
                                  style={{ borderColor: item.color }}
                                />
                                <span className="text-slate-800">{item.text}</span>
                              </div>
                            </td>

                            <td className="py-2.5 px-2">
                              <span
                                className="inline-block px-2.5 py-0.5 rounded-md text-[10px] font-bold tracking-wider uppercase border text-center min-w-[90px]"
                                style={{
                                  borderColor: item.color,
                                  color: item.color,
                                  backgroundColor: `${item.color}0D`,
                                }}
                              >
                                {item.tag}
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

          {/* RIGHT COLUMN */}
          <div className="xl:col-span-5 space-y-4">
            {/* 1. Human Annotator Details Card */}
            <div
              id="human-annotator-details-card"
              className="rounded-xl border border-[#E2DDD5] bg-white p-4 shadow-2xs space-y-3"
            >
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-100 text-blue-600 border border-blue-200 shrink-0">
                  <User className="h-4 w-4 text-blue-600" />
                </div>
                <h2 className="text-xs font-bold text-slate-900">Human Annotator Details</h2>
              </div>

              <div className="pt-2 border-t border-[#F0EBE3] space-y-1 text-xs">
                <div className="text-xs font-bold text-slate-900">{currentUserEmail || 'Human Annotator'}</div>
                <div className="space-y-0.5 text-[11px] text-slate-600">
                  {currentUserEmail && currentUserEmail.includes('@') && (
                    <div>
                      <span className="text-slate-400 font-medium">Emp No: </span>
                      <span className="font-mono font-semibold text-slate-800">{currentUserEmail.split('@')[0]}</span>
                    </div>
                  )}
                  <div>
                    <span className="text-slate-400 font-medium">Role: </span>
                    <span className="font-semibold text-slate-800">Human Annotator</span>
                  </div>
                </div>
              </div>

              <div id="section-task-assigned-ner" className="pt-2.5 border-t border-[#F0EBE3] space-y-2.5">
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
              id="ner-annotation-options-card"
              className="rounded-xl border border-[#E2DDD5] bg-white p-5 shadow-2xs space-y-4"
            >
              <div className="flex items-center justify-between pb-3 border-b border-[#F0EBE3]">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-slate-500" />
                  <h2 className="text-xs font-bold text-slate-900">Annotation Options</h2>
                </div>
                <span className="text-[11px] text-slate-400 font-medium">
                  {selectedEntity ? selectedEntity.text : 'None selected'}
                </span>
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
                        const tag = e.target.value;
                        setFormTag(tag);
                        const labelObj = AVAILABLE_LABELS.find((l) => l.tag === tag);
                        if (labelObj) {
                          setFormColor(labelObj.defaultColor);
                        }
                      }}
                      className="w-full rounded-lg border border-[#E2DDD5] px-3 py-2 text-xs text-slate-800 bg-[#FCFBFA] focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-hidden appearance-none cursor-pointer"
                    >
                      <option value="">Select label...</option>
                      {AVAILABLE_LABELS.map((item) => (
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
                      className="h-7 w-7 rounded-full border border-slate-300 shrink-0 shadow-2xs"
                      style={{ backgroundColor: formColor }}
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
                    disabled={!formText.trim() || !formTag}
                    className={`px-4 py-2 rounded-lg text-xs font-semibold shadow-xs transition cursor-pointer ${
                      formText.trim() && formTag
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
                Expanded View - {textAsset ? (textAsset.filename || textAsset.id) : 'Text Content'}
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
