import React, { useState } from 'react';
import {
  Bot,
  Sparkles,
  User,
  ShieldCheck,
  AlertCircle,
  Save,
  CheckCircle2,
  ChevronRight,
} from 'lucide-react';

export interface PredictionRow {
  id: string;
  objectName: string;
  label: string;
  confidence: number | null;
  dotColor: string;
  barColor: string;
}

export interface ImageErrorCategoryItem {
  id: string;
  name: string;
  subcategories: string[];
}

const IMAGE_ERROR_CATEGORIES: ImageErrorCategoryItem[] = [
  {
    id: 'object-detection',
    name: 'Object Detection',
    subcategories: ['Missing Object', 'Partial Detection'],
  },
  {
    id: 'labeling-error',
    name: 'Labeling Error',
    subcategories: ['Wrong Label', 'Incorrect Class'],
  },
  {
    id: 'bounding-box-error',
    name: 'Bounding Box Error',
    subcategories: ['Incorrect Box', 'Unecessary box'],
  },
  {
    id: 'duplicate-overlap-error',
    name: 'Duplicate / Overlap Error',
    subcategories: ['Duplicate Object', 'Duplicate Box'],
  },
];

interface AIPredictionsPanelProps {
  mode?: 'Object Detection & Labeling' | 'PII Masking' | 'Detection' | 'PII';
  selectedId: string | null;
  onSelect: (id: string) => void;
  isQuality?: boolean;
  onToast?: (msg: string) => void;
  confidenceScore?: number;
  onConfidenceChange?: (score: number) => void;
  predictions?: PredictionRow[];
  processingTime?: string;
  objectsDetected?: number;
  overallConfidence?: number | null;
}

export const AIPredictionsPanel: React.FC<AIPredictionsPanelProps> = ({
  mode = 'Detection',
  selectedId,
  onSelect,
  isQuality = false,
  onToast = () => {},
  confidenceScore,
  onConfidenceChange,
  predictions: customPredictions,
  processingTime,
  objectsDetected,
  overallConfidence,
}) => {
  const isPII = mode === 'PII Masking' || mode === 'PII';
  const predictions = customPredictions !== undefined ? customPredictions : [];

  // Prefer the persisted backend confidence whenever it is available. The
  // local confidence state is only a fallback for legacy/manual preview data;
  // it must not make a low-confidence backend result appear to pass 95%.
  // Never show the legacy local preview score when the backend has no
  // persisted AI confidence. N/A must also render an empty/neutral meter.
  const currentConfidence = overallConfidence != null
    ? Math.round(overallConfidence * 100)
    : 0;
  const isConfidencePass = currentConfidence >= 95;

  // Quality Audit state
  const [selectedErrors, setSelectedErrors] = useState<string[]>([]);
  const [selectedSubcategories, setSelectedSubcategories] = useState<Record<string, string[]>>({});
  const [expandedSubcategoryMap, setExpandedSubcategoryMap] = useState<Record<string, boolean>>({
    'Object Detection': false,
    'Labeling Error': false,
    'Bounding Box Error': false,
    'Duplicate / Overlap Error': false,
  });

  const [auditResult, setAuditResult] = useState<'No Issue' | 'Issues Found' | 'Critical Issue'>('Issues Found');
  const [reworkInstruction, setReworkInstruction] = useState<string>('');

  const toggleError = (categoryName: string) => {
    setSelectedErrors((prev) => {
      const willBeChecked = !prev.includes(categoryName);
      if (willBeChecked) {
        setExpandedSubcategoryMap((m) => ({ ...m, [categoryName]: true }));
        return [...prev, categoryName];
      } else {
        return prev.filter((item) => item !== categoryName);
      }
    });
  };

  const toggleSubcategory = (categoryName: string, subcat: string) => {
    setSelectedSubcategories((prev) => {
      const list = prev[categoryName] || [];
      const updated = list.includes(subcat)
        ? list.filter((s) => s !== subcat)
        : [...list, subcat];
      return { ...prev, [categoryName]: updated };
    });
    if (!selectedErrors.includes(categoryName)) {
      setSelectedErrors((prev) => [...prev, categoryName]);
    }
  };

  const toggleSubcategoryExpand = (categoryName: string) => {
    setExpandedSubcategoryMap((prev) => ({
      ...prev,
      [categoryName]: !prev[categoryName],
    }));
  };

  const handleSaveDraft = () => {
    const errorCount = selectedErrors.length;
    onToast(`Draft saved: ${errorCount} error categories marked, result "${auditResult}".`);
  };

  const handleLgtmSubmit = () => {
    onToast(`Quality audit submitted successfully as "${auditResult}"!`);
  };

  const handleNext = () => {
    onToast('Advancing to next quality audit task...');
  };

  const totalObjectsCount = objectsDetected !== undefined ? objectsDetected : predictions.length;

  const summaryCard = (
    <div
      id="ai-prediction-summary-card"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs space-y-4"
    >
      {/* Header matching NER Annotation TextAISummary */}
      <div className="flex items-center gap-2.5 pb-3 border-b border-slate-100">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50 text-blue-600 border border-blue-100">
          <Sparkles className="h-4 w-4" />
        </div>
        <h3 className="text-xs font-bold text-slate-900 tracking-tight">AI Prediction Summary</h3>
      </div>

      <div className="space-y-4 pt-1">
        {/* Result Details */}
        <div className="space-y-2">
          <h4 className="text-xs font-bold text-slate-800 mb-2.5">Result Details</h4>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between items-center">
              <span className="text-slate-400">Processing Time</span>
              <span className="font-semibold text-slate-800">
                {processingTime || 'N/A'}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-400">
                {isPII ? 'PII Items Masked' : 'Objects Detected'}
              </span>
              <span className="font-semibold text-slate-800">
                {totalObjectsCount}
              </span>
            </div>
          </div>
        </div>

        {/* Confidence */}
        <div className="pt-3 border-t border-slate-100 space-y-2">
          <h4 className="text-xs font-bold text-slate-800 mb-2">Confidence</h4>
          <div className="space-y-1.5 text-xs">
            <span className="text-slate-500 font-medium">Overall AI Confidence</span>
            <div className="space-y-1.5">
              <span className="font-bold text-slate-900 text-sm font-mono block">
                {overallConfidence != null ? overallConfidence.toFixed(2) : 'N/A'}
              </span>
              <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-300 ${
                    isConfidencePass ? 'bg-[#00A86B]' : 'bg-[#E31837]'
                  }`}
                  style={{ width: `${Math.max(0, Math.min(100, currentConfidence))}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const predictionsCard = (
    <div
      id="ai-predictions-table-card"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs space-y-4"
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50 text-blue-600 border border-blue-100">
            <Bot className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-slate-900 tracking-tight">AI Predictions</h3>
          </div>
        </div>
      </div>

      {/* Predictions Table */}
      <div className="overflow-x-auto">
        {predictions.length > 0 ? (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[11px] font-semibold text-slate-500 border-b border-slate-100">
                <th className="text-left pb-2 font-medium">Object</th>
                <th className="text-left pb-2 font-medium">Label</th>
                <th className="text-right pb-2 font-medium">Confidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {predictions.map((row) => {
                const isSelected = selectedId === row.id;
                return (
                  <tr
                    key={row.id}
                    onClick={() => onSelect(row.id)}
                    className={`cursor-pointer transition-colors ${
                      isSelected ? 'bg-blue-50/70 font-semibold' : 'hover:bg-slate-50'
                    }`}
                  >
                    <td className="py-2.5 flex items-center gap-2">
                      <span
                        className="h-2.5 w-2.5 rounded-full shrink-0"
                        style={{ backgroundColor: row.dotColor || '#ef4444' }}
                      />
                      <span className="text-slate-800">{row.objectName}</span>
                    </td>
                    <td className="py-2.5">
                      <span className="inline-block px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 text-[11px] font-mono font-medium">
                        {row.label}
                      </span>
                    </td>
                    <td className="py-2.5 text-right">
                      <div className="flex items-center justify-end gap-2.5">
                        <div className="w-16 bg-slate-100 rounded-full h-1.5 hidden sm:block overflow-hidden">
                          <div
                            className={`h-1.5 rounded-full ${row.barColor || 'bg-emerald-500'}`}
                            style={{ width: `${row.confidence == null ? 0 : Math.max(0, Math.min(100, row.confidence * 100))}%` }}
                          />
                        </div>
                        <span className="font-mono text-slate-700 text-[11.5px] tabular-nums">
                          {row.confidence == null ? 'N/A' : `${(row.confidence * 100).toFixed(0)}%`}
                        </span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="text-xs text-slate-400 italic py-4 text-center">
            No predictions available for this asset.
          </div>
        )}
      </div>
    </div>
  );

  // --- QUALITY AUDIT VIEW ---
  const qualityAuditorDetailsCard = (
    <div
      id="ai-predictions-table-card"
      className="rounded-xl border border-[#E2DDD5] bg-white p-4 shadow-2xs space-y-3"
    >
      <div className="flex items-center gap-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#E31837]/10 text-[#E31837] border border-[#E31837]/20 shrink-0">
          <User className="h-4 w-4 text-[#E31837]" />
        </div>
        <h2 className="text-xs font-bold text-slate-900">Quality Auditor Details</h2>
      </div>

      <div className="pt-2 border-t border-[#F0EBE3] space-y-1 text-xs">
        <div className="text-xs font-bold text-slate-900">Quality Auditor</div>
        <div className="space-y-0.5 text-[11px] text-slate-600">
          <div>
            <span className="text-slate-400 font-medium">Role: </span>
            <span className="font-semibold text-slate-800">Quality Auditor</span>
          </div>
        </div>
      </div>
    </div>
  );

  const qualityAuditCard = (
    <div
      id="ai-prediction-summary-card"
      className="rounded-xl border border-[#E2DDD5] bg-white p-5 shadow-2xs space-y-5"
    >
      <div className="flex items-center justify-between pb-3 border-b border-[#F0EBE3]">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white shadow-2xs shrink-0">
            <ShieldCheck className="h-4.5 w-4.5" />
          </div>
          <h2 className="text-sm font-bold text-slate-900">Quality Audit</h2>
        </div>
      </div>

      <div id="qa-mark-errors-section" className="space-y-2.5">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold text-slate-900">Root Cause Error Category</h3>
        </div>

        <div className="space-y-2 text-xs pt-1">
          {IMAGE_ERROR_CATEGORIES.map((category) => {
            const err = category.name;
            const isChecked = selectedErrors.includes(err);
            const isSubExpanded = !!expandedSubcategoryMap[err];
            const currentSubcategories = selectedSubcategories[err] || [];

            return (
              <div
                key={category.id}
                id={`mark-error-${category.id}`}
                className={`rounded-lg border p-2.5 transition-colors ${
                  isSubExpanded
                    ? 'border-blue-400/60 bg-blue-50/40 shadow-2xs'
                    : isChecked
                    ? 'border-blue-300/80 bg-blue-50/20'
                    : 'border-[#E2DDD5] bg-[#FBF9F5]/50 hover:border-[#D0C9BE]'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <label className="flex items-center gap-2.5 cursor-pointer select-none group min-w-0 flex-1">
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleError(err)}
                      className="h-3.5 w-3.5 rounded border-[#D0C9BE] text-blue-600 focus:ring-blue-500 cursor-pointer shrink-0 accent-blue-600"
                    />
                    <span
                      className={`text-[12px] transition-colors ${
                        isChecked
                          ? 'font-semibold text-slate-900'
                          : 'text-slate-700 group-hover:text-slate-900'
                      }`}
                    >
                      {err}
                    </span>
                  </label>

                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      toggleSubcategoryExpand(err);
                    }}
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded text-xs font-bold transition-all cursor-pointer ${
                      isSubExpanded
                        ? 'bg-blue-600 text-white shadow-2xs'
                        : 'text-slate-500 hover:bg-slate-200/70 hover:text-slate-900'
                    }`}
                    title={isSubExpanded ? 'Hide subcategories' : 'Show subcategories'}
                    aria-label={`Toggle subcategories for ${err}`}
                  >
                    <span className="font-mono text-xs leading-none font-bold select-none">^</span>
                  </button>
                </div>

                {isSubExpanded && (
                  <div className="mt-2.5 pl-6 pt-2 border-t border-[#E2DDD5] space-y-1.5 animate-in fade-in duration-150">
                    <div className="space-y-1.5">
                      {category.subcategories.map((subcat) => {
                        const isSubSelected = currentSubcategories.includes(subcat);
                        return (
                          <label
                            key={subcat}
                            className="flex items-center gap-2 cursor-pointer select-none group/sub text-slate-700 hover:text-slate-900 py-0.5"
                          >
                            <input
                              type="checkbox"
                              checked={isSubSelected}
                              onChange={() => toggleSubcategory(err, subcat)}
                              className="h-3.5 w-3.5 rounded border-[#D0C9BE] text-blue-600 focus:ring-blue-500 cursor-pointer shrink-0 accent-blue-600"
                            />
                            <span
                              className={`text-[11.5px] ${
                                isSubSelected
                                  ? 'font-medium text-slate-900'
                                  : 'text-slate-700'
                              }`}
                            >
                              {subcat}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div id="qa-audit-result-section" className="space-y-2 pt-1 border-t border-[#F0EBE3]">
        <h3 className="text-xs font-bold text-slate-900">Audit Result</h3>
        <div className="grid grid-cols-3 gap-2 text-xs">
          <button
            type="button"
            onClick={() => setAuditResult('No Issue')}
            className={`flex items-center justify-center gap-1.5 p-2 rounded-lg border text-xs font-semibold transition cursor-pointer ${
              auditResult === 'No Issue'
                ? 'border-emerald-500 bg-emerald-50 text-emerald-700 ring-1 ring-emerald-500'
                : 'border-[#E2DDD5] bg-white text-slate-700 hover:bg-[#FBF9F5]'
            }`}
          >
            <span>No Issue</span>
          </button>

          <button
            type="button"
            onClick={() => setAuditResult('Issues Found')}
            className={`flex items-center justify-center gap-1.5 p-2 rounded-lg border text-xs font-semibold transition cursor-pointer ${
              auditResult === 'Issues Found'
                ? 'border-rose-300 bg-rose-50 text-rose-700 ring-1 ring-rose-300'
                : 'border-[#E2DDD5] bg-white text-slate-700 hover:bg-[#FBF9F5]'
            }`}
          >
            <AlertCircle className="h-3.5 w-3.5 text-rose-600" />
            <span>Issues Found</span>
          </button>

          <button
            type="button"
            onClick={() => setAuditResult('Critical Issue')}
            className={`flex items-center justify-center gap-1.5 p-2 rounded-lg border text-xs font-semibold transition cursor-pointer ${
              auditResult === 'Critical Issue'
                ? 'border-rose-600 bg-rose-100 text-rose-900 ring-1 ring-rose-600'
                : 'border-[#E2DDD5] bg-white text-slate-700 hover:bg-[#FBF9F5]'
            }`}
          >
            <span>Critical Issue</span>
          </button>
        </div>
      </div>

      <div id="qa-rework-instruction-section" className="space-y-1.5 pt-1 border-t border-[#F0EBE3]">
        <h3 className="text-xs font-bold text-slate-900">Reviewer audit comment</h3>
        <div className="relative">
          <textarea
            rows={3}
            value={reworkInstruction}
            onChange={(e) => setReworkInstruction(e.target.value.slice(0, 500))}
            placeholder="Provide specific reviewer audit comments..."
            className="w-full rounded-lg border border-[#E2DDD5] p-2.5 text-xs text-slate-800 placeholder-slate-400 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-hidden transition resize-y bg-[#FBF9F5]"
          />
          <span className="absolute bottom-2 right-2 text-[10px] text-slate-400 font-mono">
            {reworkInstruction.length}/500
          </span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2.5 pt-1">
        <button
          id="btn-save-draft"
          type="button"
          onClick={handleSaveDraft}
          className="py-2.5 px-2 rounded-lg border border-[#D0C9BE] bg-white hover:bg-[#FBF9F5] text-slate-700 font-semibold text-xs flex items-center justify-center gap-1.5 shadow-2xs transition-all cursor-pointer hover:border-slate-400"
        >
          <Save className="h-3.5 w-3.5 text-slate-500" />
          <span>Save Draft</span>
        </button>

        <button
          id="btn-save-send-to-rework"
          type="button"
          onClick={handleLgtmSubmit}
          className="py-2.5 px-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs flex items-center justify-center gap-1.5 shadow-xs transition-all cursor-pointer hover:shadow-md"
        >
          <CheckCircle2 className="h-3.5 w-3.5" />
          <span>LGTM & submit</span>
        </button>

        <button
          id="btn-next-audit"
          type="button"
          onClick={handleNext}
          className="py-2.5 px-2 rounded-lg border border-[#D0C9BE] bg-white hover:bg-[#FBF9F5] text-slate-700 font-semibold text-xs flex items-center justify-center gap-1.5 shadow-2xs transition-all cursor-pointer hover:border-slate-400"
        >
          <span>Next</span>
          <ChevronRight className="h-3.5 w-3.5 text-slate-500" />
        </button>
      </div>
    </div>
  );

  return (
    <div id="ai-predictions-panel" className="space-y-4">
      {!isQuality ? (
        <>
          {summaryCard}
          {predictionsCard}
        </>
      ) : (
        <>
          {qualityAuditorDetailsCard}
          {qualityAuditCard}
        </>
      )}
    </div>
  );
};
