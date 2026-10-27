import React, { useState } from 'react';
import { AnnotationItem } from '../../types';
import {
  AlertOctagon,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';

interface RightReviewPanelProps {
  annotations: AnnotationItem[];
  selectedAnnotationId: number | null;
  onSelectAnnotation: (id: number) => void;
  onAcceptSuggestedFix: () => void;
  onSaveDraft?: () => void;
  onRequestSecondReview?: () => void;
  onSubmitReview?: () => void;
}

export const RightReviewPanel: React.FC<RightReviewPanelProps> = ({
  annotations,
  selectedAnnotationId,
  onSelectAnnotation,
  onAcceptSuggestedFix,
}) => {
  const [activeTab, setActiveTab] = useState<'AI Prediction' | 'Human Review'>('AI Prediction');

  // Checkbox reasons
  const [failureReasons, setFailureReasons] = useState<Record<string, boolean>>({
    missing_object: true,
    low_confidence: true,
    incorrect_label: false,
    invalid_geometry: false,
    other: false,
  });

  const toggleReason = (key: string) => {
    setFailureReasons((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div
      id="right-review-panel"
      className="flex flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-2xs space-y-5"
    >
      {/* Top Tab Bar */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-2">
        <div className="flex items-center gap-6">
          <button
            id="tab-ai-prediction"
            onClick={() => setActiveTab('AI Prediction')}
            className={`relative pb-2 text-sm font-bold transition cursor-pointer ${
              activeTab === 'AI Prediction'
                ? 'text-blue-600 after:absolute after:bottom-0 after:left-0 after:h-0.5 after:w-full after:bg-blue-600'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            AI Prediction
          </button>

          <button
            id="tab-human-review"
            onClick={() => setActiveTab('Human Review')}
            className={`relative flex items-center gap-1.5 pb-2 text-sm font-bold transition cursor-pointer ${
              activeTab === 'Human Review'
                ? 'text-blue-600 after:absolute after:bottom-0 after:left-0 after:h-0.5 after:w-full after:bg-blue-600'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            <span>Human Review</span>
            <span className="flex h-4 w-4 items-center justify-center rounded-full bg-rose-500 text-[10px] font-bold text-white">
              3
            </span>
          </button>
        </div>
      </div>

      {/* Warning Box */}
      <div
        id="review-required-warning-box"
        className="flex items-start gap-3 rounded-lg border border-rose-200 bg-rose-50/70 p-3.5"
      >
        <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-rose-100 text-rose-600 mt-0.5">
          <AlertOctagon className="h-4 w-4" />
        </div>
        <div>
          <h4 className="text-xs font-bold text-rose-900">Review Required</h4>
          <p className="text-[11px] text-rose-700 mt-0.5 font-medium">
            Reason: Low confidence (0.76) | Missing object (bicycle)
          </p>
        </div>
      </div>

      {/* 1. AI Detected Objects */}
      <div>
        <h4 className="text-xs font-bold text-slate-900 mb-2">1. AI Detected Objects</h4>
        <div className="overflow-x-auto rounded-lg border border-slate-100">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="bg-slate-50/70 text-[11px] font-semibold text-slate-500 border-b border-slate-100">
                <th className="py-2 px-2.5">Object</th>
                <th className="py-2 px-2.5">Label</th>
                <th className="py-2 px-2.5">Confidence</th>
                <th className="py-2 px-2.5">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {annotations.map((item) => {
                const isSelected = selectedAnnotationId === item.id;
                const isApproved = item.status === 'Approved';

                return (
                  <tr
                    key={item.id}
                    onClick={() => onSelectAnnotation(item.id)}
                    className={`cursor-pointer transition-colors ${
                      isSelected ? 'bg-blue-50/70 font-semibold' : 'hover:bg-slate-50/60'
                    }`}
                  >
                    <td className="py-2 px-2.5">
                      <div className="flex items-center gap-1.5">
                        <span
                          className="h-2 w-2 rounded-full shrink-0"
                          style={{ backgroundColor: item.color }}
                        />
                        <span className="text-slate-700">{item.label}</span>
                      </div>
                    </td>
                    <td className="py-2 px-2.5 text-slate-600">{item.label}</td>
                    <td className="py-2 px-2.5 text-slate-800 font-medium">
                      {item.confidence.toFixed(2)}
                    </td>
                    <td className="py-2 px-2.5">
                      {isApproved ? (
                        <span className="inline-flex items-center gap-1 font-semibold text-emerald-600 text-[11px]">
                          <CheckCircle2 className="h-3 w-3" />
                          <span>Approved</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded bg-rose-50 px-1.5 py-0.5 text-[10px] font-semibold text-rose-600 border border-rose-100">
                          <AlertCircle className="h-2.5 w-2.5" />
                          <span>Needs Review</span>
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 2. Why did AI fail? */}
      <div>
        <h4 className="text-xs font-bold text-slate-900 mb-2">2. Why did AI fail?</h4>
        <div className="space-y-2 text-xs">
          {[
            { id: 'missing_object', label: 'Missing object (bicycle)' },
            { id: 'low_confidence', label: 'Low confidence (0.76)' },
            { id: 'incorrect_label', label: 'Incorrect label' },
            { id: 'invalid_geometry', label: 'Invalid geometry' },
            { id: 'other', label: 'Other' },
          ].map((option) => (
            <label
              key={option.id}
              className="flex items-center gap-2 cursor-pointer select-none text-slate-700 hover:text-slate-900"
            >
              <input
                type="checkbox"
                checked={failureReasons[option.id] || false}
                onChange={() => toggleReason(option.id)}
                className="h-3.5 w-3.5 rounded border-slate-300 text-blue-600 focus:ring-blue-500 accent-blue-600"
              />
              <span className="text-[12px]">{option.label}</span>
            </label>
          ))}
        </div>
      </div>

      {/* 3. Suggested Fix */}
      <div>
        <h4 className="text-xs font-bold text-slate-900 mb-2">3. Suggested Fix</h4>
        <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50/50 p-3">
          <div className="flex items-center gap-2.5">
            {/* Bicycle crop thumbnail */}
            <div className="relative h-10 w-10 shrink-0 overflow-hidden rounded-md border border-slate-200 bg-slate-200">
              <svg className="h-full w-full object-cover" viewBox="0 0 40 40">
                <rect width="40" height="40" fill="#cbd5e1" />
                {/* Cyclist person */}
                <circle cx="20" cy="12" r="5" fill="#475569" />
                <path d="M15 17h10l-2 10h-6z" fill="#334155" />
                {/* Bike wheels */}
                <circle cx="12" cy="32" r="5" stroke="#9333ea" strokeWidth="2" fill="none" />
                <circle cx="28" cy="32" r="5" stroke="#9333ea" strokeWidth="2" fill="none" />
                <path d="M12 32l8-10 8 10" stroke="#9333ea" strokeWidth="2" />
              </svg>
            </div>
            <div>
              <span className="text-[11px] text-slate-500 block">AI suggested:</span>
              <span className="text-xs font-bold text-slate-800">bicycle (0.76)</span>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              id="btn-accept-fix"
              onClick={onAcceptSuggestedFix}
              className="rounded-md bg-emerald-600 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-emerald-700 shadow-2xs transition cursor-pointer"
            >
              Accept
            </button>
            <button
              id="btn-edit-fix"
              className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 transition cursor-pointer"
            >
              Edit
            </button>
            <button
              id="btn-reject-fix"
              className="rounded-md border border-rose-200 bg-white px-2.5 py-1.5 text-[11px] font-semibold text-rose-600 hover:bg-rose-50 transition cursor-pointer"
            >
              Reject
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
