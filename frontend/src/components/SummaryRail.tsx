import React from 'react';
import { IntakeFormData } from '../types';
import {
  FileText,
  Lightbulb,
  Headphones,
  Calendar,
  Layers,
  CheckCircle2,
  HelpCircle,
} from 'lucide-react';

interface SummaryRailProps {
  formData: IntakeFormData;
  onEdit?: () => void;
  onViewDocs: () => void;
  onContactSupport: () => void;
}

export const SummaryRail: React.FC<SummaryRailProps> = ({
  formData,
  onViewDocs,
  onContactSupport,
}) => {
  // Format media data string, e.g. "50 video files (MP4)"
  const mediaExtension =
    formData.mediaFormat === 'Video'
      ? 'MP4'
      : formData.mediaFormat === 'Image'
      ? 'JPG/PNG'
      : formData.mediaFormat;
  const selectedImageUploads = (formData.uploadedFiles || [])
    .map((item) => item.file)
    .filter((file): file is File => file instanceof File);
  const formatBytes = (size: number) =>
    size < 1024 * 1024
      ? `${size.toLocaleString()} B`
      : `${(size / (1024 * 1024)).toFixed(2)} MB`;
  const dataLabel =
    formData.dataType === 'Input Text Field'
      ? formData.inputText
        ? `Text (${(formData.inputText || '').trim().split(/\s+/).filter(Boolean).length} words)`
        : 'Direct Input Text'
      : formData.dataType === 'Cloud Storage'
      ? formData.cloudStorageUrl
        ? `Cloud: ${formData.cloudStorageUrl.replace(/^https?:\/\//, '').substring(0, 24)}...`
        : 'Cloud Storage Bucket'
      : formData.dataType === 'Files Upload' && (formData.uploadedFiles || []).length > 0
      ? (formData.uploadedFiles || []).length === 1
        ? `${formData.uploadedFiles![0].name} (${formatBytes(formData.uploadedFiles![0].file?.size || 0)})`
        : `${(formData.uploadedFiles || []).length} uploaded files`
      : formData.numberOfFiles && formData.numberOfFiles > 0
      ? `${formData.numberOfFiles} project assets`
      : formData.dataType === 'Files Upload'
      ? 'No files selected'
      : formData.dataType || '—';

  const visibleAnnotationTypes = formData.annotationTypes.slice(0, 2);
  const remainingAnnotationCount = formData.annotationTypes.length - visibleAnnotationTypes.length;

  return (
    <div id="project-summary-rail" className="flex flex-col gap-6">
      {/* Card 1: Project Summary */}
      <div
        id="card-project-summary"
        className="rounded-xl border border-[#E2DDD5] bg-white p-5 shadow-xs transition hover:shadow-sm"
      >
        <div className="flex items-center gap-2.5 pb-4 border-b border-[#F0EBE3]">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-[#E31837]/10 text-[#E31837]">
            <svg
              className="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M9 3v18" />
              <path d="M14 9h4" />
              <path d="M14 15h4" />
            </svg>
          </div>
          <h3 className="font-bold text-slate-900 text-base">Project Summary</h3>
        </div>

        <div className="mt-4 space-y-3.5 text-xs sm:text-sm">
          {/* Project Name */}
          <div className="flex items-start justify-between gap-2">
            <span className="text-slate-500 font-normal">Project Name</span>
            <span className="text-right font-medium text-slate-800 max-w-[65%] truncate">
              {formData.projectName || '—'}
            </span>
          </div>

          {/* Project Type */}
          <div className="flex items-center justify-between gap-2">
            <span className="text-slate-500 font-normal">Project Type</span>
            <span className="text-right font-medium text-slate-800">
              {formData.projectType || '—'}
            </span>
          </div>

          {/* Annotation Types */}
          <div className="flex items-center justify-between gap-2">
            <span className="text-slate-500 font-normal">Annotation Types</span>
            <div className="flex items-center gap-1.5 flex-wrap justify-end">
              {visibleAnnotationTypes.map((type) => (
                <span
                  key={type}
                  className="rounded-md bg-[#E31837]/10 px-2 py-0.5 text-[11px] font-medium text-[#E31837] border border-[#E31837]/20"
                >
                  {type}
                </span>
              ))}
              {remainingAnnotationCount > 0 && (
                <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">
                  +{remainingAnnotationCount}
                </span>
              )}
              {formData.annotationTypes.length === 0 && (
                <span className="text-xs text-slate-400 italic">None selected</span>
              )}
            </div>
          </div>

          {/* Data */}
          <div className="flex items-center justify-between gap-2">
            <span className="text-slate-500 font-normal">Data</span>
            <span className="text-right font-medium text-slate-800">{dataLabel}</span>
          </div>

          {/* Format */}
          <div className="flex items-center justify-between gap-2">
            <span className="text-slate-500 font-normal">Format</span>
            <span className="text-right font-medium text-slate-800">
              {formData.expectedOutputFormat || '—'}
            </span>
          </div>

          {/* Technique */}
          {formData.projectType !== 'Text Annotation' &&
            (formData.visionTechniques?.length || formData.visionTechnique) && (
            <div className="flex items-center justify-between gap-2">
              <span className="text-slate-500 font-normal">Technique</span>
              <span className="text-right font-medium text-slate-800">
                {(formData.visionTechniques?.length
                  ? formData.visionTechniques
                  : [formData.visionTechnique]
                ).filter(Boolean).join(', ')}
              </span>
            </div>
          )}

          {/* Target Classes */}
          {formData.targetClasses && formData.targetClasses.length > 0 && (
            <div className="flex items-start justify-between gap-2">
              <span className="text-slate-500 font-normal">
                {formData.projectType === 'Text Annotation' ? 'Target Objects' : 'Classes'} ({formData.targetClasses.length})
              </span>
              <div className="flex flex-wrap gap-1 justify-end max-w-[65%]">
                {formData.targetClasses.slice(0, 3).map((cls) => (
                  <span
                    key={cls.id}
                    className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium bg-slate-50 text-slate-700 border border-slate-200"
                  >
                    <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: cls.color }} />
                    {cls.name}
                  </span>
                ))}
                {formData.targetClasses.length > 3 && (
                  <span className="text-[10px] text-slate-400 self-center">
                    +{formData.targetClasses.length - 3}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Card 2: Quick Tips */}
      <div
        id="card-quick-tips"
        className="rounded-xl border border-[#E2DDD5] bg-white p-5 shadow-xs"
      >
        <div className="flex items-center gap-2.5 pb-3 border-b border-[#F0EBE3]">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-amber-50 text-amber-600">
            <Lightbulb className="h-4 w-4 text-amber-600" />
          </div>
          <h3 className="font-bold text-slate-900 text-base">Quick Tips</h3>
        </div>

        <ul className="mt-3.5 space-y-2.5 text-xs sm:text-sm text-slate-600 leading-relaxed list-disc list-outside pl-4">
          <li className="pl-0.5">Use clear and descriptive project names.</li>
          <li className="pl-0.5">Choose the right annotation types based on your use case.</li>
          <li className="pl-0.5">You can always edit the settings before submission.</li>
          <li className="pl-0.5">For large datasets, consider using cloud storage.</li>
        </ul>
      </div>

      {/* Card 3: Need Help? */}
      <div
        id="card-need-help"
        className="rounded-xl border border-[#E2DDD5] bg-white p-5 shadow-xs"
      >
        <div className="flex items-center gap-2.5 pb-3">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-[#E31837]/10 text-[#E31837]">
            <Headphones className="h-4 w-4 text-[#E31837]" />
          </div>
          <h3 className="font-bold text-slate-900 text-base">Need Help?</h3>
        </div>

        <p className="mt-1 text-xs sm:text-sm text-slate-600 leading-relaxed">
          <button
            onClick={onViewDocs}
            className="text-[#E31837] underline font-medium hover:text-[#C1122C] cursor-pointer"
          >
            Check our documentation
          </button>{' '}
          or contact support if you need assistance.
        </p>

        <div className="mt-4 flex flex-col sm:flex-row items-center gap-2.5">
          <button
            id="view-docs-btn"
            onClick={onViewDocs}
            className="w-full flex-1 rounded-lg border border-[#D0C9BE] bg-white py-2 px-3 text-xs font-semibold text-slate-700 hover:bg-[#FBF9F5] transition cursor-pointer text-center"
          >
            View Documentation
          </button>

          <button
            id="contact-support-btn"
            onClick={onContactSupport}
            className="w-full flex-1 rounded-lg bg-[#E31837] py-2 px-3 text-xs font-semibold text-white hover:bg-[#C1122C] shadow-sm transition cursor-pointer text-center"
          >
            Contact Support
          </button>
        </div>
      </div>
    </div>
  );
};
