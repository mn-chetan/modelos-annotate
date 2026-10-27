import React, { useEffect, useState } from 'react';
import { FileText, Menu, Send, UserCheck, Undo2, Redo2 } from 'lucide-react';
import { AssetResponse, ProjectResponse, TextAnalysisResponse, api } from '../../services/api';
import { TextAIViewer } from './TextAIViewer';
import { TextAIPredictions } from './TextAIPredictions';

type TaskType = 'NER' | 'SENTIMENT_ANALYSIS' | 'TEXT_CLASSIFICATION' | 'RELATION_EXTRACTION';
type ReviewAnnotation = NonNullable<TextAnalysisResponse['annotations']>[number];

interface TextTaskHitlWorkbenchProps {
  taskType: TaskType;
  onToggleSidebar?: () => void;
  onToast: (message: string) => void;
  onSubmit: (annotations: ReviewAnnotation[]) => Promise<void>;
  textAsset?: AssetResponse | null;
  project?: ProjectResponse | null;
  analysis?: TextAnalysisResponse | null;
  totalAssets?: number;
  currentAssetIndex?: number;
  onPrevAsset?: () => void;
  onNextAsset?: () => void;
  currentUserEmail?: string;
}

export const TextTaskHitlWorkbench: React.FC<TextTaskHitlWorkbenchProps> = ({
  taskType,
  onToggleSidebar,
  onToast,
  onSubmit,
  textAsset,
  project,
  analysis,
  totalAssets = 0,
  currentAssetIndex = 0,
  onPrevAsset,
  onNextAsset,
  currentUserEmail,
}) => {
  const [annotations, setAnnotations] = useState<ReviewAnnotation[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [history, setHistory] = useState<ReviewAnnotation[][]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const selectedAnnotation = annotations[selectedIndex];
  const title = taskType === 'NER'
    ? 'NER Annotation'
    : taskType === 'SENTIMENT_ANALYSIS'
    ? 'Sentiment Annotation'
    : taskType === 'TEXT_CLASSIFICATION'
    ? 'Text Classification'
    : 'Relation Extraction';
  const analysisLevel = analysis?.raw_result?.analysis_level || 'document';
  const analysisLevelLabel = analysisLevel.charAt(0).toUpperCase() + analysisLevel.slice(1) + '-Level';

  useEffect(() => {
    const initial = analysis?.annotations || [];
    setAnnotations(initial);
    setHistory([initial]);
    setHistoryIndex(0);
    setSelectedIndex(0);
    setIsSubmitted(false);
  }, [analysis, textAsset?.id]);

  const pushHistory = (next: ReviewAnnotation[]) => {
    const branch = history.slice(0, historyIndex + 1);
    setHistory([...branch, next]);
    setHistoryIndex(branch.length);
    setAnnotations(next);
  };

  const updateAnnotation = (update: (annotation: ReviewAnnotation) => ReviewAnnotation) => {
    pushHistory(annotations.map((annotation, index) => index === selectedIndex ? update(annotation) : annotation));
  };

  const handleUndo = () => {
    if (historyIndex <= 0) return onToast('Nothing to undo');
    const nextIndex = historyIndex - 1;
    setHistoryIndex(nextIndex);
    setAnnotations(history[nextIndex]);
  };

  const handleRedo = () => {
    if (historyIndex >= history.length - 1) return onToast('Nothing to redo');
    const nextIndex = historyIndex + 1;
    setHistoryIndex(nextIndex);
    setAnnotations(history[nextIndex]);
  };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'z') return;
      const target = event.target as HTMLElement | null;
      if (target?.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target?.tagName || '')) return;
      event.preventDefault();
      event.shiftKey ? handleRedo() : handleUndo();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  const setReviewStatus = (status: 'APPROVED' | 'REJECTED') => {
    updateAnnotation((annotation) => ({ ...annotation, review_status: status }));
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      await onSubmit(annotations);
      setIsSubmitted(true);
      onToast('Human-reviewed result submitted for quality audit.');
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Failed to submit the human review.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div id="text-annotation-workspace-hitl" className="flex-1 min-w-0 overflow-y-auto bg-[#F6F2EA]">
      {onToggleSidebar && (
        <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2 lg:hidden">
          <button onClick={onToggleSidebar} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Toggle navigation">
            <Menu className="h-5 w-5" />
          </button>
          <span className="text-xs font-bold text-slate-800">{title}</span>
          <span className="w-5" />
        </div>
      )}
      <main className="mx-auto w-full max-w-[1700px] space-y-4 p-3 sm:p-5 lg:p-6">
        <header className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-2xs">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-rose-100 bg-rose-50 text-[#E31837]">
              <UserCheck className="h-4 w-4" />
            </div>
            <div>
              <h1 className="text-base font-bold text-slate-900">{title}</h1>
              <span className="text-[10px] font-semibold uppercase tracking-wide text-blue-700">{analysisLevelLabel}</span>
              <p className="text-xs text-slate-500">Human review · {project?.name || 'Selected project'}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-600">
            <FileText className="h-4 w-4" />
            <span>{textAsset?.filename || textAsset?.id || 'No queued text asset'}</span>
            <span className="font-mono text-slate-400">{totalAssets ? `${currentAssetIndex + 1} / ${totalAssets}` : '0 / 0'}</span>
          </div>
        </header>

        <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-12">
          <section className="space-y-4 xl:col-span-8">
            <TextAIViewer
              selectedEntityId={selectedAnnotation?.id || null}
              onSelectEntity={(id) => {
                const index = annotations.findIndex((annotation, itemIndex) => (annotation.id || `annotation-${itemIndex}`) === id);
                if (index >= 0) setSelectedIndex(index);
              }}
              onToast={onToast}
              taskType={title}
              analysisLevel={analysisLevel as 'document' | 'page' | 'paragraph' | 'sentence'}
              text={analysis?.text}
              annotations={annotations}
            />
            <div className="flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white p-2 shadow-2xs">
              <button type="button" onClick={handleUndo} disabled={historyIndex <= 0} className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-3 py-1.5 text-xs font-semibold disabled:opacity-40">
                <Undo2 className="h-3.5 w-3.5" /> Undo
              </button>
              <button type="button" onClick={handleRedo} disabled={historyIndex >= history.length - 1} className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-3 py-1.5 text-xs font-semibold disabled:opacity-40">
                <Redo2 className="h-3.5 w-3.5" /> Redo
              </button>
            </div>
            <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3 shadow-2xs">
              <button onClick={onPrevAsset} disabled={!onPrevAsset || currentAssetIndex <= 0} className="rounded-md border border-slate-200 px-3 py-1.5 text-xs disabled:opacity-40">Previous</button>
              <span className="text-xs font-semibold text-slate-600">{currentUserEmail || 'Human Annotator'}</span>
              <button onClick={onNextAsset} disabled={!onNextAsset || currentAssetIndex >= totalAssets - 1} className="rounded-md border border-slate-200 px-3 py-1.5 text-xs disabled:opacity-40">Next</button>
            </div>
          </section>

          <aside className="space-y-4 xl:col-span-4">
            <TextAIPredictions
              selectedEntityId={selectedAnnotation?.id || null}
              onSelectEntity={(id) => {
                const index = annotations.findIndex((annotation, itemIndex) => (annotation.id || `annotation-${itemIndex}`) === id);
                if (index >= 0) setSelectedIndex(index);
              }}
              analysis={analysis ? { ...analysis, annotations } : null}
            />
            <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-2xs">
              <h2 className="text-xs font-bold text-slate-900">Correct selected result</h2>
              {!selectedAnnotation ? (
                <p className="text-xs text-slate-500">No matching persisted predictions are available for this queued task.</p>
              ) : taskType === 'TEXT_CLASSIFICATION' || taskType === 'NER' || taskType === 'SENTIMENT_ANALYSIS' ? (
                <label className="block text-xs font-medium text-slate-600">
                  {taskType === 'NER' ? 'Entity label' : taskType === 'SENTIMENT_ANALYSIS' ? 'Sentiment label' : 'Classification label'}
                  {taskType === 'SENTIMENT_ANALYSIS' ? (
                    <select
                      value={selectedAnnotation.label || ''}
                      onChange={(event) => updateAnnotation((annotation) => ({ ...annotation, label: event.target.value, review_status: 'EDITED' }))}
                      className="mt-1.5 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none focus:border-rose-500"
                    >
                      <option value="">Select sentiment</option>
                      <option value="POSITIVE">Positive</option>
                      <option value="NEGATIVE">Negative</option>
                      <option value="NEUTRAL">Neutral</option>
                    </select>
                  ) : <input
                    value={selectedAnnotation.label || ''}
                    onChange={(event) => updateAnnotation((annotation) => ({ ...annotation, label: event.target.value, review_status: 'EDITED' }))}
                    className="mt-1.5 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none focus:border-rose-500"
                  />}
                  {taskType !== 'TEXT_CLASSIFICATION' && (
                    <textarea
                      value={selectedAnnotation.text_span?.text || selectedAnnotation.geometry?.text || ''}
                      onChange={(event) => updateAnnotation((annotation) => ({
                        ...annotation,
                        geometry: { ...annotation.geometry, text: event.target.value },
                        text_span: { ...annotation.text_span, text: event.target.value },
                        review_status: 'EDITED',
                      }))}
                      rows={2}
                      placeholder="Supporting text"
                      className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none focus:border-rose-500"
                    />
                  )}
                </label>
              ) : (
                <div className="space-y-2">
                  {(['source', 'relation', 'target'] as const).map((field) => (
                    <label key={field} className="block text-xs font-medium capitalize text-slate-600">
                      {field}
                      <input
                        value={selectedAnnotation.geometry?.[field] || ''}
                        onChange={(event) => updateAnnotation((annotation) => ({
                          ...annotation,
                          geometry: { ...annotation.geometry, [field]: event.target.value },
                        }))}
                        className="mt-1.5 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none focus:border-rose-500"
                      />
                    </label>
                  ))}
                  <label className="block text-xs font-medium text-slate-600">
                    Supporting evidence
                    <textarea
                      value={selectedAnnotation.geometry?.evidence || ''}
                      onChange={(event) => updateAnnotation((annotation) => ({
                        ...annotation,
                        geometry: { ...annotation.geometry, evidence: event.target.value, text: event.target.value },
                        text_span: { ...annotation.text_span, text: event.target.value },
                        review_status: 'EDITED',
                      }))}
                      rows={3}
                      className="mt-1.5 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none focus:border-rose-500"
                    />
                  </label>
                  <div className="flex gap-2">
                    <button type="button" onClick={() => setReviewStatus('APPROVED')} className="rounded-md border border-emerald-200 px-3 py-1.5 text-xs font-semibold text-emerald-700">Approve</button>
                    <button type="button" onClick={() => setReviewStatus('REJECTED')} className="rounded-md border border-rose-200 px-3 py-1.5 text-xs font-semibold text-rose-700">Reject</button>
                    <span className="ml-auto self-center text-[10px] font-semibold uppercase text-slate-500">{selectedAnnotation.review_status || 'PENDING'}</span>
                  </div>
                </div>
              )}
              <button
                onClick={handleSubmit}
                disabled={annotations.length === 0 || isSubmitting || isSubmitted}
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-[#E31837] px-4 py-2.5 text-xs font-bold text-white hover:bg-[#C9142E] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Send className="h-3.5 w-3.5" />
                {isSubmitted ? 'Submitted for quality audit' : isSubmitting ? 'Submitting review...' : 'Submit human review'}
              </button>
            </section>
          </aside>
        </div>
      </main>
    </div>
  );
};
