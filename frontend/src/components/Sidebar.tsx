import React, { useState, useEffect } from 'react';
import { BrandLockup } from '../brand/BrandLockup';
import {
  Home,
  FolderClosed,
  Sparkles,
  ClipboardCheck,
  ShieldCheck,
  Users,
  Sliders,
  ChevronDown,
  ChevronUp,
  ChevronRight,
  Image as ImageIcon,
  Scan,
  EyeOff,
  FileText,
  Tag,
  Smile,
  X,
  FileBarChart,
  UserCheck,
} from 'lucide-react';

interface SidebarProps {
  currentProject: string;
  isOpen?: boolean;
  onClose?: () => void;
  activeItem?: string;
  onSelectItem?: (item: string) => void;
  userEmail?: string;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentProject,
  isOpen = false,
  onClose,
  activeItem = 'AI Results',
  onSelectItem,
  userEmail = '',
}) => {
  const [isDashboardOpen, setIsDashboardOpen] = useState(false);
  const [isAIResultsOpen, setIsAIResultsOpen] = useState(false);
  const [isImageAnnotationOpen, setIsImageAnnotationOpen] = useState(false);
  const [isTextAnnotationOpen, setIsTextAnnotationOpen] = useState(false);
  const [isHumanReviewOpen, setIsHumanReviewOpen] = useState(false);
  const [isHitlImageOpen, setIsHitlImageOpen] = useState(false);
  const [isHitlTextOpen, setIsHitlTextOpen] = useState(false);
  const [isQualityOpen, setIsQualityOpen] = useState(false);
  const [isQualityImageOpen, setIsQualityImageOpen] = useState(false);
  const [isQualityTextOpen, setIsQualityTextOpen] = useState(false);

  useEffect(() => {
    if (
      activeItem === 'Image Annotation HITL' ||
      activeItem === 'HITL - Object Detection & Labeling' ||
      activeItem === 'HITL - Object Detection' ||
      activeItem === 'HITL - PII Masking' ||
      activeItem === 'Text Annotation HITL' ||
      activeItem === 'HITL - NER Annotation' ||
      activeItem === 'HITL - NER' ||
      activeItem === 'HITL - Sentiment Annotation' ||
      activeItem === 'HITL - Sentiment' ||
      activeItem === 'HITL - Text Classification' ||
      activeItem === 'HITL - Relation Extraction' ||
      activeItem === 'Human Review' ||
      activeItem === 'Human Annotator'
    ) {
      setIsHumanReviewOpen(true);
      if (
        activeItem === 'Image Annotation HITL' ||
        activeItem === 'HITL - Object Detection & Labeling' ||
        activeItem === 'HITL - Object Detection' ||
        activeItem === 'HITL - PII Masking'
      ) {
        setIsHitlImageOpen(true);
      }
      if (
        activeItem === 'Text Annotation HITL' ||
        activeItem === 'HITL - NER Annotation' ||
        activeItem === 'HITL - NER' ||
        activeItem === 'HITL - Sentiment Annotation' ||
        activeItem === 'HITL - Sentiment' ||
        activeItem === 'HITL - Text Classification' ||
        activeItem === 'HITL - Relation Extraction'
      ) {
        setIsHitlTextOpen(true);
      }
    }

    if (
      activeItem === 'Object Detection & Labeling' ||
      activeItem === 'PII Masking' ||
      activeItem === 'Image Annotation' ||
      activeItem === 'Text Annotation' ||
      activeItem === 'All Text Features' ||
      activeItem === 'NER Annotation' ||
      activeItem === 'Sentiment Annotation' ||
      activeItem === 'AI Results' ||
      activeItem === 'AI Processed result'
    ) {
      setIsAIResultsOpen(true);
      if (
        activeItem === 'Object Detection & Labeling' ||
        activeItem === 'PII Masking' ||
        activeItem === 'Image Annotation'
      ) {
        setIsImageAnnotationOpen(true);
      }
      if (
        activeItem === 'Text Annotation' ||
        activeItem === 'All Text Features' ||
        activeItem === 'NER Annotation' ||
        activeItem === 'Sentiment Annotation'
      ) {
        setIsTextAnnotationOpen(true);
      }
    }

    if (
      activeItem === 'Quality' ||
      activeItem === 'Quality Check' ||
      activeItem === 'Quality - Image' ||
      activeItem === 'Quality Image' ||
      activeItem === 'Quality - Object Detection' ||
      activeItem === 'Quality - Object Detection & Labeling' ||
      activeItem === 'Quality - PII Masking' ||
      activeItem === 'Quality - Text' ||
      activeItem === 'Quality Text' ||
      activeItem === 'Quality - NER Annotation' ||
      activeItem === 'Quality - NER' ||
      activeItem === 'Quality - Sentiment Annotation' ||
      activeItem === 'Quality - Sentiment' ||
      activeItem === 'Quality - Text Classification' ||
      activeItem === 'Quality - Relation Extraction'
    ) {
      setIsQualityOpen(true);
      if (
        activeItem === 'Quality - Image' ||
        activeItem === 'Quality Image' ||
        activeItem === 'Quality - Object Detection' ||
        activeItem === 'Quality - Object Detection & Labeling' ||
        activeItem === 'Quality - PII Masking'
      ) {
        setIsQualityImageOpen(true);
      }
      if (
        activeItem === 'Quality - Text' ||
        activeItem === 'Quality Text' ||
        activeItem === 'Quality - NER Annotation' ||
        activeItem === 'Quality - NER' ||
        activeItem === 'Quality - Sentiment Annotation' ||
        activeItem === 'Quality - Sentiment' ||
        activeItem === 'Quality - Text Classification' ||
        activeItem === 'Quality - Relation Extraction'
      ) {
        setIsQualityTextOpen(true);
      }
    }
  }, [activeItem]);

  const navItems = [
    { id: 'Dashboard', label: 'Dashboard', icon: Home },
    { id: 'Projects', label: 'Projects', icon: FolderClosed },
    {
      id: 'AI Results',
      label: 'AI Processed result',
      icon: Sparkles,
      alias: 'Image Annotation',
    },
    {
      id: 'Human Review',
      label: 'Human Annotator',
      icon: ClipboardCheck,
      alias: 'Text Annotation',
    },
    { id: 'Quality', label: 'Quality Check', icon: ShieldCheck },
    { id: 'Administration', label: 'Administration', icon: Sliders },
  ];

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          id="sidebar-backdrop"
          onClick={onClose}
          className="fixed inset-0 z-40 bg-slate-950/60 backdrop-blur-xs lg:hidden"
        />
      )}

      <aside
        id="main-sidebar"
        className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col bg-white text-slate-700 transition-transform duration-200 ease-in-out lg:static lg:translate-x-0 ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        } border-r border-[#E2DDD5] shadow-xl lg:shadow-none select-none`}
      >
        {/* Brand Header */}
        <div className="flex h-20 items-center justify-between px-5 border-b border-[#E2DDD5] bg-white">
          <BrandLockup size="sm" stacked />

          {/* Close button for mobile */}
          <button
            id="close-mobile-sidebar-btn"
            onClick={onClose}
            className="p-1.5 rounded-md text-slate-400 hover:text-slate-800 lg:hidden hover:bg-slate-100"
            aria-label="Close sidebar"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation Items */}
        <nav className="flex-1 space-y-1 px-3 py-4 overflow-y-auto bg-white">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isAIResults = item.id === 'AI Results';
            const isAIChildActive =
              activeItem === 'Image Annotation' ||
              activeItem === 'Object Detection & Labeling' ||
              activeItem === 'PII Masking' ||
              activeItem === 'Text Annotation' ||
              activeItem === 'All Text Features' ||
              activeItem === 'NER Annotation' ||
              activeItem === 'Sentiment Annotation' ||
              activeItem === 'AI Results' ||
              activeItem === 'AI Processed result';

            const isImageAnnotationChildActive =
              activeItem === 'Image Annotation' ||
              activeItem === 'Object Detection & Labeling' ||
              activeItem === 'PII Masking';

            const isTextAnnotationChildActive =
              activeItem === 'Text Annotation' ||
              activeItem === 'All Text Features' ||
              activeItem === 'NER Annotation' ||
              activeItem === 'Sentiment Annotation';

            const isHumanReview = item.id === 'Human Review';
            const isHRChildActive =
              activeItem === 'Image Annotation HITL' ||
              activeItem === 'HITL - Object Detection & Labeling' ||
              activeItem === 'HITL - Object Detection' ||
              activeItem === 'HITL - PII Masking' ||
              activeItem === 'Text Annotation HITL' ||
              activeItem === 'HITL - NER Annotation' ||
              activeItem === 'HITL - NER' ||
              activeItem === 'HITL - Sentiment Annotation' ||
              activeItem === 'HITL - Sentiment' ||
              activeItem === 'Human Review' ||
              activeItem === 'Human Annotator';

            const isQuality = item.id === 'Quality';
            const isQualityImageChildActive =
              activeItem === 'Quality - Image' ||
              activeItem === 'Quality Image' ||
              activeItem === 'Quality - Object Detection' ||
              activeItem === 'Quality - Object Detection & Labeling' ||
              activeItem === 'Quality - PII Masking';

            const isQualityImageDirectActive =
              activeItem === 'Quality - Image' ||
              activeItem === 'Quality Image';

            const isQualityTextChildActive =
              activeItem === 'Quality - Text' ||
              activeItem === 'Quality Text' ||
              activeItem === 'Quality - NER Annotation' ||
              activeItem === 'Quality - NER' ||
              activeItem === 'Quality - Sentiment Annotation' ||
              activeItem === 'Quality - Sentiment' ||
              activeItem === 'Quality - Text Classification' ||
              activeItem === 'Quality - Relation Extraction';

            const isQualityTextDirectActive =
              activeItem === 'Quality - Text' ||
              activeItem === 'Quality Text';

            const isQualityChildActive =
              activeItem === 'Quality' ||
              activeItem === 'Quality Check' ||
              isQualityImageChildActive ||
              isQualityTextChildActive;

            const isDashboard = item.id === 'Dashboard';
            const isDashboardChildActive =
              activeItem === 'Dashboard' ||
              activeItem === 'Production Report' ||
              activeItem === 'Production report' ||
              activeItem === 'HITL Report' ||
              activeItem === 'HITL report' ||
              activeItem === 'Quality Report' ||
              activeItem === 'Quality report' ||
              activeItem === 'Text HITL Dashboard';

            const isActive =
              !isDashboard &&
              !isAIResults &&
              !isHumanReview &&
              !isQuality &&
              activeItem === item.id;

            if (isDashboard) {
              return (
                <div key={item.id} id="nav-item-dashboard-section" className="w-full space-y-1">
                  <button
                    id="nav-item-dashboard"
                    onClick={() => {
                      setIsDashboardOpen((prev) => !prev);
                      if (!isDashboardChildActive) {
                        onSelectItem?.('Production report');
                      }
                    }}
                    className={`group flex w-full items-center justify-between rounded-lg px-3.5 py-2 text-xs font-semibold transition-all cursor-pointer ${
                      isDashboardChildActive
                        ? 'bg-red-50 text-[#E31837] ring-1 ring-[#E31837]/25 font-bold'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <Icon
                        className={`h-4 w-4 transition-colors ${
                          isDashboardChildActive ? 'text-[#E31837]' : 'text-slate-500 group-hover:text-slate-800'
                        }`}
                      />
                      <span>{item.label}</span>
                    </div>

                    {isDashboardOpen ? (
                      <ChevronDown className="h-3.5 w-3.5 text-slate-400 group-hover:text-slate-600 transition-colors" />
                    ) : (
                      <ChevronUp className="h-3.5 w-3.5 text-slate-400 group-hover:text-slate-600 transition-colors" />
                    )}
                  </button>

                  {/* 3 Sub-categories under Dashboard */}
                  {isDashboardOpen && (
                    <div
                      id="dashboard-subcategories"
                      className="ml-3 pl-3.5 border-l border-[#E2DDD5] space-y-1 py-0.5"
                    >
                      {/* Sub-item 1: Production report */}
                      <button
                        id="nav-subitem-production-report"
                        onClick={() => {
                          onSelectItem?.('Production report');
                          onClose?.();
                        }}
                        className={`group flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-xs font-medium transition-all cursor-pointer ${
                          activeItem === 'Production report' || activeItem === 'Production Report' || activeItem === 'Dashboard'
                            ? 'bg-[#E31837] text-white font-semibold shadow-xs'
                            : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                        }`}
                      >
                        <div className="flex items-center gap-2.5">
                          <FileBarChart className="h-3.5 w-3.5 shrink-0" />
                          <span>Image Production Report (AI + HITL)</span>
                        </div>
                        <span
                          className={`flex h-4 min-w-4 items-center justify-center rounded-full px-1.5 text-[9px] font-bold ${
                            activeItem === 'Production report' || activeItem === 'Production Report' || activeItem === 'Dashboard'
                              ? 'bg-white/20 text-white'
                              : 'bg-slate-100 text-slate-600 border border-slate-200'
                          }`}
                        >
                          Run
                        </span>
                      </button>

                      <button
                        id="nav-subitem-text-hitl-dashboard"
                        onClick={() => {
                          onSelectItem?.('Text HITL Dashboard');
                          onClose?.();
                        }}
                        className={`group flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-xs font-medium transition-all cursor-pointer ${
                          activeItem === 'Text HITL Dashboard'
                            ? 'bg-violet-600 text-white font-semibold shadow-xs'
                            : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                        }`}
                      >
                        <div className="flex items-center gap-2.5">
                          <FileText className="h-3.5 w-3.5 shrink-0" />
                          <span>Text Production Report (AI + HITL)</span>
                        </div>
                      </button>

                    </div>
                  )}
                </div>
              );
            }

            if (isAIResults) {
              return (
                <div
                  key={item.id}
                  id="nav-item-image-annotation"
                  className="w-full space-y-1"
                >
                  <button
                    id="nav-item-ai-results"
                    onClick={() => {
                      setIsAIResultsOpen((prev) => !prev);
                      if (!isAIChildActive) {
                        onSelectItem?.('Object Detection & Labeling');
                        setIsImageAnnotationOpen(true);
                      }
                    }}
                    className={`group flex w-full items-center justify-between rounded-lg px-3.5 py-2 text-xs font-semibold transition-all cursor-pointer ${
                      isAIChildActive
                        ? 'bg-red-50 text-[#E31837] ring-1 ring-[#E31837]/25 font-bold'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <Icon
                        className={`h-4 w-4 transition-colors ${
                          isAIChildActive
                            ? 'text-[#E31837]'
                            : 'text-slate-500 group-hover:text-slate-800'
                        }`}
                      />
                      <span>{item.label}</span>
                    </div>

                    <div className="flex items-center gap-2">
                      {isAIResultsOpen ? (
                        <ChevronDown
                          className={`h-3.5 w-3.5 transition-colors ${
                            isAIChildActive
                              ? 'text-[#E31837]'
                              : 'text-slate-400 group-hover:text-slate-600'
                          }`}
                        />
                      ) : (
                        <ChevronUp
                          className={`h-3.5 w-3.5 transition-colors ${
                            isAIChildActive
                              ? 'text-[#E31837]'
                              : 'text-slate-400 group-hover:text-slate-600'
                          }`}
                        />
                      )}
                    </div>
                  </button>

                  {/* Sub-sections under AI Results */}
                  {isAIResultsOpen && (
                    <div
                      id="ai-results-subsections"
                      className="ml-3 pl-3.5 border-l border-[#E2DDD5] space-y-1 py-0.5"
                    >
                      {/* Sub-section: Image Annotation */}
                      <button
                        id="nav-subitem-image-annotation"
                        onClick={() => {
                          setIsImageAnnotationOpen((prev) => !prev);
                          if (!isImageAnnotationChildActive) {
                            onSelectItem?.('Object Detection & Labeling');
                          }
                        }}
                        className={`group flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-xs font-medium transition-all cursor-pointer ${
                          isImageAnnotationChildActive
                            ? 'bg-red-50 text-[#E31837] font-semibold ring-1 ring-[#E31837]/25'
                            : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                        }`}
                      >
                        <div className="flex items-center gap-2.5">
                          <ImageIcon
                            className={`h-3.5 w-3.5 shrink-0 ${
                              isImageAnnotationChildActive
                                ? 'text-[#E31837]'
                                : 'text-slate-500'
                            }`}
                          />
                          <span>Image Annotation</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {isImageAnnotationOpen ? (
                            <ChevronDown
                              className={`h-3 w-3 ${
                                isImageAnnotationChildActive
                                  ? 'text-[#E31837]'
                                  : 'text-slate-500'
                              }`}
                            />
                          ) : (
                            <ChevronUp
                              className={`h-3 w-3 ${
                                isImageAnnotationChildActive
                                  ? 'text-[#E31837]'
                                  : 'text-slate-500'
                              }`}
                            />
                          )}
                        </div>
                      </button>

                      {/* Nested Sub-sections under Image Annotation: Object Detection & Labeling & PII Masking */}
                      {isImageAnnotationOpen && (
                        <div
                          id="image-annotation-subsections"
                          className="ml-3 pl-3 border-l border-[#E2DDD5] space-y-1 py-0.5"
                        >
                          {/* Sub-section: Object Detection & Labeling */}
                          <button
                            id="nav-subitem-object-detection"
                            onClick={() => {
                              onSelectItem?.('Object Detection & Labeling');
                              onClose?.();
                            }}
                            className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${
                              activeItem === 'Object Detection & Labeling'
                                ? 'bg-red-50 text-[#E31837] font-semibold ring-1 ring-[#E31837]/25'
                                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <Scan
                                className={`h-3 w-3 shrink-0 ${
                                  activeItem === 'Object Detection & Labeling'
                                    ? 'text-[#E31837]'
                                    : 'text-slate-500'
                                }`}
                              />
                              <span className="truncate">Object Detection & Labeling</span>
                            </div>
                          </button>

                          {/* Sub-section: PII Masking */}
                          <button
                            id="nav-subitem-pii-masking"
                            onClick={() => {
                              onSelectItem?.('PII Masking');
                              onClose?.();
                            }}
                            className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${
                              activeItem === 'PII Masking'
                                ? 'bg-amber-50 text-amber-800 font-semibold ring-1 ring-amber-200'
                                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <EyeOff
                                className={`h-3 w-3 shrink-0 ${
                                  activeItem === 'PII Masking'
                                    ? 'text-amber-600'
                                    : 'text-slate-500'
                                }`}
                              />
                              <span className="truncate">PII Masking</span>
                            </div>
                          </button>

                        </div>
                      )}

                      {/* Sub-section: Text Annotation */}
                      <button
                        id="nav-subitem-text-annotation"
                        onClick={() => {
                          setIsTextAnnotationOpen((prev) => !prev);
                          if (!isTextAnnotationChildActive) {
                            onSelectItem?.('NER Annotation');
                          }
                        }}
                        className={`group flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-xs font-medium transition-all cursor-pointer ${
                          isTextAnnotationChildActive
                            ? 'bg-red-50 text-[#E31837] font-semibold ring-1 ring-[#E31837]/25'
                            : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                        }`}
                      >
                        <div className="flex items-center gap-2.5">
                          <FileText
                            className={`h-3.5 w-3.5 shrink-0 ${
                              isTextAnnotationChildActive
                                ? 'text-[#E31837]'
                                : 'text-slate-500'
                            }`}
                          />
                          <span>Text Annotation</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {isTextAnnotationOpen ? (
                            <ChevronDown
                              className={`h-3 w-3 ${
                                isTextAnnotationChildActive
                                  ? 'text-[#E31837]'
                                  : 'text-slate-500'
                              }`}
                            />
                          ) : (
                            <ChevronUp
                              className={`h-3 w-3 ${
                                isTextAnnotationChildActive
                                  ? 'text-[#E31837]'
                                  : 'text-slate-500'
                              }`}
                            />
                          )}
                        </div>
                      </button>

                      {/* Nested Sub-sections under Text Annotation */}
                      {isTextAnnotationOpen && (
                        <div
                          id="text-annotation-subsections"
                          className="ml-3 pl-3 border-l border-[#E2DDD5] space-y-1 py-0.5"
                        >
                          {/* Sub-section: NER Annotation */}
                          <button
                            id="nav-subitem-ner-annotation"
                            onClick={() => {
                              onSelectItem?.('NER Annotation');
                              onClose?.();
                            }}
                            className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${
                              activeItem === 'NER Annotation'
                                ? 'bg-red-50 text-[#E31837] font-semibold ring-1 ring-[#E31837]/25'
                                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <Tag
                                className={`h-3 w-3 shrink-0 ${
                                  activeItem === 'NER Annotation'
                                    ? 'text-[#E31837]'
                                    : 'text-slate-500'
                                }`}
                              />
                              <span>NER Annotation</span>
                            </div>
                          </button>

                          {/* Sub-section: Sentiment Annotation */}
                          <button
                            id="nav-subitem-sentiment-annotation"
                            onClick={() => {
                              onSelectItem?.('Sentiment Annotation');
                              onClose?.();
                            }}
                            className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${
                              activeItem === 'Sentiment Annotation'
                                ? 'bg-emerald-50 text-emerald-800 font-semibold ring-1 ring-emerald-200'
                                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <Smile
                                className={`h-3 w-3 shrink-0 ${
                                  activeItem === 'Sentiment Annotation'
                                    ? 'text-[#247153]'
                                    : 'text-slate-500'
                                }`}
                              />
                              <span>Sentiment Annotation</span>
                            </div>
                          </button>

                          {/* Sub-section: Text Classification */}
                          <button
                            id="nav-subitem-text-classification"
                            onClick={() => {
                              onSelectItem?.('Text Classification');
                              onClose?.();
                            }}
                            className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${
                              activeItem === 'Text Classification'
                                ? 'bg-purple-50 text-purple-800 font-semibold ring-1 ring-purple-200'
                                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <FileText
                                className={`h-3 w-3 shrink-0 ${
                                  activeItem === 'Text Classification'
                                    ? 'text-purple-600'
                                    : 'text-slate-500'
                                }`}
                              />
                              <span>Text Classification</span>
                            </div>
                          </button>

                          {/* Sub-section: Relation Extraction */}
                          <button
                            id="nav-subitem-relation-extraction"
                            onClick={() => {
                              onSelectItem?.('Relation Extraction');
                              onClose?.();
                            }}
                            className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${
                              activeItem === 'Relation Extraction'
                                ? 'bg-amber-50 text-amber-800 font-semibold ring-1 ring-amber-200'
                                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <Sliders
                                className={`h-3 w-3 shrink-0 ${
                                  activeItem === 'Relation Extraction'
                                    ? 'text-amber-600'
                                    : 'text-slate-500'
                                }`}
                              />
                              <span>Relation Extraction</span>
                            </div>
                          </button>

                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            }

            if (isHumanReview) {
              const isHitlImageChildActive =
                activeItem === 'HITL - Object Detection & Labeling' ||
                activeItem === 'HITL - Object Detection' ||
                activeItem === 'HITL - PII Masking';

              const isHitlTextChildActive =
                activeItem === 'HITL - NER Annotation' ||
                activeItem === 'HITL - NER' ||
                activeItem === 'HITL - Sentiment Annotation' ||
                activeItem === 'HITL - Sentiment' ||
                activeItem === 'HITL - Text Classification' ||
                activeItem === 'HITL - Relation Extraction';

              const isHRChildActive =
                activeItem === 'Image Annotation HITL' ||
                isHitlImageChildActive ||
                activeItem === 'Text Annotation HITL' ||
                isHitlTextChildActive ||
                activeItem === 'Human Review' ||
                activeItem === 'Human Annotator';

              return (
                <div
                  key={item.id}
                  id="nav-item-human-review-container"
                  className="w-full space-y-1"
                >
                  <button
                    id="nav-item-human-review"
                    onClick={() => {
                      setIsHumanReviewOpen((prev) => !prev);
                      if (!isHRChildActive) {
                        onSelectItem?.('Image Annotation HITL');
                        setIsHitlImageOpen(true);
                      }
                    }}
                    className={`group flex w-full items-center justify-between rounded-lg px-3.5 py-2 text-xs font-semibold transition-all cursor-pointer ${
                      isHRChildActive
                        ? 'bg-red-50 text-[#E31837] ring-1 ring-[#E31837]/25 font-bold'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <Icon
                        className={`h-4 w-4 transition-colors ${
                          isHRChildActive ? 'text-[#E31837]' : 'text-slate-500 group-hover:text-slate-800'
                        }`}
                      />
                      <span>{item.label}</span>
                    </div>

                    <div className="flex items-center gap-2">
                      {isHumanReviewOpen ? (
                        <ChevronDown className="h-3.5 w-3.5 text-slate-400 group-hover:text-slate-600 transition-colors" />
                      ) : (
                        <ChevronUp className="h-3.5 w-3.5 text-slate-400 group-hover:text-slate-600 transition-colors" />
                      )}
                    </div>
                  </button>

                  {/* Sub-sections under Human Review */}
                  {isHumanReviewOpen && (
                    <div
                      id="human-review-subsections"
                      className="ml-3 pl-3.5 border-l border-[#E2DDD5] space-y-1 py-0.5"
                    >
                      {/* Sub-section: Image Annotation HITL */}
                      <button
                        id="nav-subitem-image-annotation-hitl"
                        onClick={() => {
                          setIsHitlImageOpen((prev) => !prev);
                          onSelectItem?.('Image Annotation HITL');
                        }}
                        className={`group flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-xs font-medium transition-all cursor-pointer ${
                          activeItem === 'Image Annotation HITL'
                            ? 'bg-[#E31837] text-white font-semibold shadow-xs'
                            : isHitlImageChildActive
                            ? 'bg-red-50 text-[#E31837] font-semibold ring-1 ring-[#E31837]/25'
                            : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                        }`}
                      >
                        <div className="flex items-center gap-2.5">
                          <ImageIcon
                            className={`h-3.5 w-3.5 shrink-0 ${
                              activeItem === 'Image Annotation HITL'
                                ? 'text-white'
                                : isHitlImageChildActive
                                ? 'text-[#E31837]'
                                : 'text-slate-500'
                            }`}
                          />
                          <span>Image Annotation HITL</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {isHitlImageOpen ? (
                            <ChevronDown
                              className={`h-3 w-3 ${
                                activeItem === 'Image Annotation HITL'
                                  ? 'text-white'
                                  : isHitlImageChildActive
                                  ? 'text-[#E31837]'
                                  : 'text-slate-500'
                              }`}
                            />
                          ) : (
                            <ChevronUp
                              className={`h-3 w-3 ${
                                activeItem === 'Image Annotation HITL'
                                  ? 'text-white'
                                  : isHitlImageChildActive
                                  ? 'text-[#E31837]'
                                  : 'text-slate-500'
                              }`}
                            />
                          )}
                        </div>
                      </button>

                      {/* Nested Sub-sections under Image Annotation HITL: Object Detection & Labeling & PII Masking */}
                      {isHitlImageOpen && (
                        <div
                          id="hitl-image-annotation-subsections"
                          className="ml-3 pl-3 border-l border-[#E2DDD5] space-y-1 py-0.5"
                        >
                          {/* Sub-section: Object Detection & Labeling */}
                          <button
                            id="nav-subitem-hitl-object-detection"
                            onClick={() => {
                              onSelectItem?.('HITL - Object Detection & Labeling');
                              onClose?.();
                            }}
                            className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${
                              activeItem === 'HITL - Object Detection & Labeling' ||
                              activeItem === 'HITL - Object Detection'
                                ? 'bg-red-50 text-[#E31837] font-semibold ring-1 ring-[#E31837]/25'
                                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <Scan
                                className={`h-3 w-3 shrink-0 ${
                                  activeItem === 'HITL - Object Detection & Labeling' ||
                                  activeItem === 'HITL - Object Detection'
                                    ? 'text-[#E31837]'
                                    : 'text-slate-500'
                                }`}
                              />
                              <span className="truncate">Object Detection & Labeling</span>
                            </div>
                          </button>

                          {/* Sub-section: PII Masking */}
                          <button
                            id="nav-subitem-hitl-pii-masking"
                            onClick={() => {
                              onSelectItem?.('HITL - PII Masking');
                              onClose?.();
                            }}
                            className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${
                              activeItem === 'HITL - PII Masking'
                                ? 'bg-amber-50 text-amber-800 font-semibold ring-1 ring-amber-200'
                                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <EyeOff
                                className={`h-3 w-3 shrink-0 ${
                                  activeItem === 'HITL - PII Masking'
                                    ? 'text-amber-600'
                                    : 'text-slate-500'
                                }`}
                              />
                              <span className="truncate">PII Masking</span>
                            </div>
                          </button>
                        </div>
                      )}

                      {/* Sub-section: Text Annotation HITL */}
                      <button
                        id="nav-subitem-text-annotation-hitl"
                        onClick={() => {
                          setIsHitlTextOpen((prev) => !prev);
                          if (!isHitlTextChildActive && activeItem !== 'Text Annotation HITL') {
                            onSelectItem?.('Text Annotation HITL');
                          }
                        }}
                        className={`group flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-xs font-medium transition-all cursor-pointer ${
                          activeItem === 'Text Annotation HITL'
                            ? 'bg-[#E31837] text-white font-semibold shadow-xs'
                            : isHitlTextChildActive
                            ? 'bg-red-50 text-[#E31837] font-semibold ring-1 ring-[#E31837]/25'
                            : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                        }`}
                      >
                        <div className="flex items-center gap-2.5">
                          <FileText
                            className={`h-3.5 w-3.5 shrink-0 ${
                              activeItem === 'Text Annotation HITL'
                                ? 'text-white'
                                : isHitlTextChildActive
                                ? 'text-[#E31837]'
                                : 'text-slate-500'
                            }`}
                          />
                          <span>Text Annotation HITL</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {isHitlTextOpen ? (
                            <ChevronDown
                              className={`h-3 w-3 ${
                                activeItem === 'Text Annotation HITL'
                                  ? 'text-white'
                                  : isHitlTextChildActive
                                  ? 'text-[#E31837]'
                                  : 'text-slate-500'
                              }`}
                            />
                          ) : (
                            <ChevronUp
                              className={`h-3 w-3 ${
                                activeItem === 'Text Annotation HITL'
                                  ? 'text-white'
                                  : isHitlTextChildActive
                                  ? 'text-[#E31837]'
                                  : 'text-slate-500'
                              }`}
                            />
                          )}
                        </div>
                      </button>

                      {/* Nested Sub-sections under Text Annotation HITL */}
                      {isHitlTextOpen && (
                        <div
                          id="hitl-text-annotation-subsections"
                          className="ml-3 pl-3 border-l border-[#E2DDD5] space-y-1 py-0.5"
                        >
                          {/* Sub-section: NER Annotation */}
                          <button
                            id="nav-subitem-hitl-ner-annotation"
                            onClick={() => {
                              onSelectItem?.('HITL - NER Annotation');
                              onClose?.();
                            }}
                            className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${
                              activeItem === 'HITL - NER Annotation' ||
                              activeItem === 'HITL - NER' ||
                              activeItem === 'Text Annotation HITL'
                                ? 'bg-red-50 text-[#E31837] font-semibold ring-1 ring-[#E31837]/25'
                                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <Tag
                                className={`h-3 w-3 shrink-0 ${
                                  activeItem === 'HITL - NER Annotation' ||
                                  activeItem === 'HITL - NER' ||
                                  activeItem === 'Text Annotation HITL'
                                    ? 'text-[#E31837]'
                                    : 'text-slate-500'
                                }`}
                              />
                              <span className="truncate">NER Annotation</span>
                            </div>
                          </button>

                          {/* Sub-section: Sentiment Annotation */}
                          <button
                            id="nav-subitem-hitl-sentiment-annotation"
                            onClick={() => {
                              onSelectItem?.('HITL - Sentiment Annotation');
                              onClose?.();
                            }}
                            className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${
                              activeItem === 'HITL - Sentiment Annotation' ||
                              activeItem === 'HITL - Sentiment'
                                ? 'bg-emerald-50 text-emerald-800 font-semibold ring-1 ring-emerald-200'
                                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <Smile
                                className={`h-3 w-3 shrink-0 ${
                                  activeItem === 'HITL - Sentiment Annotation' ||
                                  activeItem === 'HITL - Sentiment'
                                    ? 'text-[#247153]'
                                    : 'text-slate-500'
                                }`}
                              />
                              <span className="truncate">Sentiment Annotation</span>
                            </div>
                          </button>

                          {/* Sub-section: Text Classification */}
                          <button
                            id="nav-subitem-hitl-text-classification"
                            onClick={() => {
                              onSelectItem?.('HITL - Text Classification');
                              onClose?.();
                            }}
                            className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${
                              activeItem === 'HITL - Text Classification'
                                ? 'bg-red-50 text-[#E31837] font-semibold ring-1 ring-[#E31837]/25'
                                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <FileText
                                className={`h-3 w-3 shrink-0 ${
                                  activeItem === 'HITL - Text Classification'
                                    ? 'text-[#E31837]'
                                    : 'text-slate-500'
                                }`}
                              />
                              <span className="truncate">Text Classification</span>
                            </div>
                          </button>

                          {/* Sub-section: Relation Extraction */}
                          <button
                            id="nav-subitem-hitl-relation-extraction"
                            onClick={() => {
                              onSelectItem?.('HITL - Relation Extraction');
                              onClose?.();
                            }}
                            className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${
                              activeItem === 'HITL - Relation Extraction'
                                ? 'bg-red-50 text-[#E31837] font-semibold ring-1 ring-[#E31837]/25'
                                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <Sliders
                                className={`h-3 w-3 shrink-0 ${
                                  activeItem === 'HITL - Relation Extraction'
                                    ? 'text-[#E31837]'
                                    : 'text-slate-500'
                                }`}
                              />
                              <span className="truncate">Relation Extraction</span>
                            </div>
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            }

            if (isQuality) {
              return (
                <div
                  key={item.id}
                  id="nav-item-quality-container"
                  className="w-full space-y-1"
                >
                  <button
                    id="nav-item-quality"
                    onClick={() => {
                      setIsQualityOpen((prev) => !prev);
                      if (!isQualityChildActive) {
                        onSelectItem?.('Quality - Object Detection');
                        setIsQualityImageOpen(true);
                      }
                    }}
                    className={`group flex w-full items-center justify-between rounded-lg px-3.5 py-2 text-xs font-semibold transition-all cursor-pointer ${
                      isQualityChildActive
                        ? 'bg-red-50 text-[#E31837] ring-1 ring-[#E31837]/25 font-bold'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <Icon
                        className={`h-4 w-4 transition-colors ${
                          isQualityChildActive ? 'text-[#E31837]' : 'text-slate-500 group-hover:text-slate-800'
                        }`}
                      />
                      <span>{item.label}</span>
                    </div>

                    <div className="flex items-center gap-2">
                      {isQualityOpen ? (
                        <ChevronDown className="h-3.5 w-3.5 text-slate-400 group-hover:text-slate-600 transition-colors" />
                      ) : (
                        <ChevronUp className="h-3.5 w-3.5 text-slate-400 group-hover:text-slate-600 transition-colors" />
                      )}
                    </div>
                  </button>

                  {/* Sub-sections under Quality Check: Image and Text */}
                  {isQualityOpen && (
                    <div
                      id="quality-check-subsections"
                      className="ml-3 pl-3.5 border-l border-[#E2DDD5] space-y-1 py-0.5"
                    >
                      {/* Sub-section: Image */}
                      <button
                        id="nav-subitem-quality-image"
                        onClick={() => {
                          setIsQualityImageOpen((prev) => !prev);
                          if (!isQualityImageChildActive) {
                            onSelectItem?.('Quality - Object Detection');
                          }
                        }}
                        className={`group flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-xs font-medium transition-all cursor-pointer ${
                          isQualityImageChildActive
                            ? 'bg-red-50 text-[#E31837] font-semibold ring-1 ring-[#E31837]/25'
                            : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                        }`}
                      >
                        <div className="flex items-center gap-2.5">
                          <ImageIcon
                            className={`h-3.5 w-3.5 shrink-0 ${
                              isQualityImageChildActive ? 'text-[#E31837]' : 'text-slate-500'
                            }`}
                          />
                          <span>Image</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {isQualityImageOpen ? (
                            <ChevronDown
                              className={`h-3 w-3 ${
                                isQualityImageChildActive ? 'text-[#E31837]' : 'text-slate-500'
                              }`}
                            />
                          ) : (
                            <ChevronUp
                              className={`h-3 w-3 ${
                                isQualityImageChildActive ? 'text-[#E31837]' : 'text-slate-500'
                              }`}
                            />
                          )}
                        </div>
                      </button>

                      {/* Nested Sub-sections under Quality Check -> Image: Object Detection & Labeling & PII Masking */}
                      {isQualityImageOpen && (
                        <div
                          id="quality-image-subsections"
                          className="ml-3 pl-3 border-l border-[#E2DDD5] space-y-1 py-0.5"
                        >
                          {/* Sub-section: Object Detection & Labeling */}
                          <button
                            id="nav-subitem-quality-object-detection"
                            onClick={() => {
                              onSelectItem?.('Quality - Object Detection');
                              onClose?.();
                            }}
                            className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${
                              activeItem === 'Quality - Object Detection' ||
                              activeItem === 'Quality - Object Detection & Labeling'
                                ? 'bg-red-50 text-[#E31837] font-semibold ring-1 ring-[#E31837]/25'
                                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <Scan
                                className={`h-3 w-3 shrink-0 ${
                                  activeItem === 'Quality - Object Detection' ||
                                  activeItem === 'Quality - Object Detection & Labeling'
                                    ? 'text-[#E31837]'
                                    : 'text-slate-500'
                                }`}
                              />
                              <span className="truncate">Object Detection & Labeling</span>
                            </div>
                          </button>

                          {/* Sub-section: PII Masking */}
                          <button
                            id="nav-subitem-quality-pii-masking"
                            onClick={() => {
                              onSelectItem?.('Quality - PII Masking');
                              onClose?.();
                            }}
                            className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${
                              activeItem === 'Quality - PII Masking' ||
                              activeItem === 'Quality PII Masking'
                                ? 'bg-amber-50 text-amber-900 font-semibold ring-1 ring-amber-300'
                                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <EyeOff
                                className={`h-3 w-3 shrink-0 ${
                                  activeItem === 'Quality - PII Masking' ||
                                  activeItem === 'Quality PII Masking'
                                    ? 'text-amber-600'
                                    : 'text-slate-500'
                                }`}
                              />
                              <span className="truncate">PII Masking</span>
                            </div>
                          </button>
                        </div>
                      )}

                      {/* Sub-section: Text */}
                      <button
                        id="nav-subitem-quality-text"
                        onClick={() => {
                          setIsQualityTextOpen((prev) => !prev);
                          if (!isQualityTextChildActive) {
                            onSelectItem?.('Quality - NER Annotation');
                          }
                        }}
                        className={`group flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-xs font-medium transition-all cursor-pointer ${
                          isQualityTextChildActive
                            ? 'bg-red-50 text-[#E31837] font-semibold ring-1 ring-[#E31837]/25'
                            : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                        }`}
                      >
                        <div className="flex items-center gap-2.5">
                          <FileText
                            className={`h-3.5 w-3.5 shrink-0 ${
                              isQualityTextChildActive ? 'text-[#E31837]' : 'text-slate-500'
                            }`}
                          />
                          <span>Text</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {isQualityTextOpen ? (
                            <ChevronDown
                              className={`h-3 w-3 ${
                                isQualityTextChildActive ? 'text-[#E31837]' : 'text-slate-500'
                              }`}
                            />
                          ) : (
                            <ChevronUp
                              className={`h-3 w-3 ${
                                isQualityTextChildActive ? 'text-[#E31837]' : 'text-slate-500'
                              }`}
                            />
                          )}
                        </div>
                      </button>

                      {/* Nested Sub-sections under Quality Check -> Text: NER Annotation & Sentiment Annotation */}
                      {isQualityTextOpen && (
                        <div
                          id="quality-text-subsections"
                          className="ml-3 pl-3 border-l border-[#E2DDD5] space-y-1 py-0.5"
                        >
                          {/* Sub-section: NER Annotation */}
                          <button
                            id="nav-subitem-quality-ner"
                            onClick={() => {
                              onSelectItem?.('Quality - NER Annotation');
                              onClose?.();
                            }}
                            className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${
                              activeItem === 'Quality - NER Annotation' ||
                              activeItem === 'Quality - NER'
                                ? 'bg-[#E31837] text-white font-semibold shadow-xs'
                                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <Tag
                                className={`h-3 w-3 shrink-0 ${
                                  activeItem === 'Quality - NER Annotation' ||
                                  activeItem === 'Quality - NER'
                                    ? 'text-white'
                                    : 'text-[#E31837]'
                                }`}
                              />
                              <span className="truncate">NER Annotation</span>
                            </div>
                          </button>

                          {/* Sub-section: Sentiment Annotation */}
                          <button
                            id="nav-subitem-quality-sentiment"
                            onClick={() => {
                              onSelectItem?.('Quality - Sentiment Annotation');
                              onClose?.();
                            }}
                            className={`group flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${
                              activeItem === 'Quality - Sentiment Annotation' ||
                              activeItem === 'Quality - Sentiment'
                                ? 'bg-emerald-50 text-emerald-800 font-semibold ring-1 ring-emerald-200'
                                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <Smile className="h-3 w-3 shrink-0 text-[#247153]" />
                              <span className="truncate">Sentiment Annotation</span>
                            </div>
                          </button>

                          <button id="nav-subitem-quality-classification" onClick={() => { onSelectItem?.('Quality - Text Classification'); onClose?.(); }} className={`group flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${activeItem === 'Quality - Text Classification' ? 'bg-blue-50 text-blue-800 font-semibold ring-1 ring-blue-200' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'}`}>
                            <FileText className="h-3 w-3 shrink-0 text-blue-600" /><span className="truncate">Text Classification</span>
                          </button>

                          <button id="nav-subitem-quality-relation" onClick={() => { onSelectItem?.('Quality - Relation Extraction'); onClose?.(); }} className={`group flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all cursor-pointer ${activeItem === 'Quality - Relation Extraction' ? 'bg-violet-50 text-violet-800 font-semibold ring-1 ring-violet-200' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'}`}>
                            <Tag className="h-3 w-3 shrink-0 text-violet-600" /><span className="truncate">Relation Extraction</span>
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            }

            return (
              <div key={item.id} className="w-full">
                <button
                  id={`nav-item-${item.id.toLowerCase().replace(/\s+/g, '-')}`}
                  onClick={() => {
                    onSelectItem?.(item.id);
                    onClose?.();
                  }}
                  className={`group flex w-full items-center justify-between rounded-lg px-3.5 py-2 text-xs font-semibold transition-all cursor-pointer ${
                    isActive
                      ? 'bg-[#E31837] text-white shadow-xs'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Icon
                      className={`h-4 w-4 transition-colors ${
                        isActive ? 'text-white' : 'text-slate-500 group-hover:text-slate-800'
                      }`}
                    />
                    <span>{item.label}</span>
                  </div>
                </button>
              </div>
            );
          })}
        </nav>

      </aside>
    </>
  );
};
