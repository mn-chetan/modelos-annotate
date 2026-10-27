import React from 'react';
import {
  Tag,
  Scissors,
  Layers,
  Split,
  FileText,
  ChevronDown,
  Sparkles,
} from 'lucide-react';
import { AssetResponse, TextAnalysisResponse } from '../../services/api';

interface EntityLabelOption {
  id: string;
  name: string;
  color: string;
  bgClass: string;
  borderClass: string;
  textClass: string;
  dotColor: string;
  active: boolean;
}

interface LeftToolPanelProps {
  activeToolTab: 'NER' | 'Sentiment' | 'Classification';
  onChangeToolTab: (tab: 'NER' | 'Sentiment' | 'Classification') => void;
  selectedEntity?: string;
  onSelectEntity?: (id: string) => void;
  onQuickAction?: (action: string) => void;
  textAsset?: AssetResponse | null;
  analysis?: TextAnalysisResponse | null;
}

export const LeftToolPanel: React.FC<LeftToolPanelProps> = ({
  activeToolTab,
  onChangeToolTab,
  selectedEntity,
  onSelectEntity,
  onQuickAction,
  textAsset,
  analysis,
}) => {
  const entityLabels: EntityLabelOption[] = [
    {
      id: 'person',
      name: 'Person',
      color: '#3b82f6',
      bgClass: 'bg-blue-50',
      borderClass: 'border-blue-200',
      textClass: 'text-blue-700',
      dotColor: '#3b82f6',
      active: true,
    },
    {
      id: 'organization',
      name: 'Organization',
      color: '#22c55e',
      bgClass: 'bg-emerald-50',
      borderClass: 'border-emerald-200',
      textClass: 'text-emerald-700',
      dotColor: '#22c55e',
      active: true,
    },
    {
      id: 'location',
      name: 'Location',
      color: '#f59e0b',
      bgClass: 'bg-amber-50',
      borderClass: 'border-amber-200',
      textClass: 'text-amber-700',
      dotColor: '#f59e0b',
      active: true,
    },
    {
      id: 'date',
      name: 'Date',
      color: '#8b5cf6',
      bgClass: 'bg-purple-50',
      borderClass: 'border-purple-200',
      textClass: 'text-purple-700',
      dotColor: '#8b5cf6',
      active: true,
    },
    {
      id: 'money',
      name: 'Money',
      color: '#eab308',
      bgClass: 'bg-yellow-50',
      borderClass: 'border-yellow-200',
      textClass: 'text-yellow-800',
      dotColor: '#eab308',
      active: true,
    },
    {
      id: 'product',
      name: 'Product',
      color: '#14b8a6',
      bgClass: 'bg-teal-50',
      borderClass: 'border-teal-200',
      textClass: 'text-teal-700',
      dotColor: '#14b8a6',
      active: true,
    },
    {
      id: 'event',
      name: 'Event',
      color: '#ec4899',
      bgClass: 'bg-pink-50',
      borderClass: 'border-pink-200',
      textClass: 'text-pink-700',
      dotColor: '#ec4899',
      active: true,
    },
    {
      id: 'custom',
      name: 'Custom',
      color: '#64748b',
      bgClass: 'bg-slate-50',
      borderClass: 'border-slate-200',
      textClass: 'text-slate-700',
      dotColor: '#64748b',
      active: true,
    },
  ];

  return (
    <div id="text-left-tools-panel" className="space-y-4">
      {/* Annotation Tools Box */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2.5">
          Annotation Tools
        </h3>
        <div className="flex items-center gap-1.5 flex-wrap">
          {(['NER', 'Sentiment', 'Classification'] as const).map((tab) => (
            <button
              key={tab}
              id={`tool-tab-${tab.toLowerCase()}`}
              onClick={() => onChangeToolTab(tab)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition cursor-pointer ${
                activeToolTab === tab
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
              }`}
            >
              {tab}
            </button>
          ))}
          <button
            onClick={() => onQuickAction?.('more_tools')}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 hover:bg-slate-50 transition cursor-pointer"
            title="More Options"
          >
            ···
          </button>
        </div>
      </div>

      {/* Entity Labels Box */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2.5">
          Entity Labels
        </h3>
        <div className="grid grid-cols-2 gap-2">
          {entityLabels.map((item) => {
            const isSelected = selectedEntity === item.id;
            return (
              <button
                key={item.id}
                id={`entity-label-btn-${item.id}`}
                onClick={() => onSelectEntity?.(item.id)}
                className={`flex items-center gap-2 rounded-lg border px-2.5 py-2 text-xs font-semibold transition cursor-pointer text-left ${
                  isSelected
                    ? `${item.bgClass} ${item.borderClass} ${item.textClass} ring-2 ring-blue-500/20`
                    : 'border-slate-200/90 bg-white text-slate-700 hover:bg-slate-50/80'
                }`}
              >
                <span
                  className="flex h-4 w-4 shrink-0 items-center justify-center rounded text-[10px] font-bold text-white shadow-2xs"
                  style={{ backgroundColor: item.color }}
                >
                  ✓
                </span>
                <span className="truncate">{item.name}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2.5">
          Quick Actions
        </h3>
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => onQuickAction?.('add_label')}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white py-2 px-2 text-xs font-medium text-slate-700 hover:bg-slate-50 transition cursor-pointer"
          >
            <Tag className="h-3.5 w-3.5 text-slate-500" />
            <span>Add Label</span>
          </button>
          <button
            onClick={() => onQuickAction?.('remove_label')}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white py-2 px-2 text-xs font-medium text-slate-700 hover:bg-slate-50 transition cursor-pointer"
          >
            <Scissors className="h-3.5 w-3.5 text-slate-500" />
            <span>Remove Label</span>
          </button>
          <button
            onClick={() => onQuickAction?.('merge_spans')}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white py-2 px-2 text-xs font-medium text-slate-700 hover:bg-slate-50 transition cursor-pointer"
          >
            <Layers className="h-3.5 w-3.5 text-slate-500" />
            <span>Merge Spans</span>
          </button>
          <button
            onClick={() => onQuickAction?.('split_span')}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white py-2 px-2 text-xs font-medium text-slate-700 hover:bg-slate-50 transition cursor-pointer"
          >
            <Split className="h-3.5 w-3.5 text-slate-500" />
            <span>Split Span</span>
          </button>
        </div>
      </div>

      {/* Document View */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
          Document View
        </h3>
        <div className="relative">
          <div className="flex w-full items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-800 shadow-2xs">
            <div className="flex items-center gap-2">
              <FileText className="h-3.5 w-3.5 text-slate-500" />
              <span>Text View</span>
            </div>
            <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
          </div>
        </div>
      </div>

      {/* File Info */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs space-y-2.5 text-xs">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
          File Info
        </h3>
        <div className="flex items-center justify-between text-slate-600">
          <span className="text-slate-400">File Name</span>
          <span className="font-semibold text-slate-900 font-mono">
            {textAsset ? (textAsset.filename || textAsset.id) : 'N/A'}
          </span>
        </div>
        <div className="flex items-center justify-between text-slate-600">
          <span className="text-slate-400">Size</span>
          <span className="font-semibold text-slate-800">
            {textAsset?.byte_size ? `${(textAsset.byte_size / 1024).toFixed(1)} KB` : 'N/A'}
          </span>
        </div>
        <div className="flex items-center justify-between text-slate-600">
          <span className="text-slate-400">Format</span>
          <span className="font-semibold text-slate-800">
            {textAsset?.filename ? textAsset.filename.split('.').pop()?.toUpperCase() || 'TXT' : 'TXT'}
          </span>
        </div>
        <div className="flex items-center justify-between text-slate-600">
          <span className="text-slate-400">Characters</span>
          <span className="font-semibold text-slate-800">
            {analysis?.text ? analysis.text.length.toLocaleString() : 'N/A'}
          </span>
        </div>
        <div className="flex items-center justify-between text-slate-600">
          <span className="text-slate-400">Lines</span>
          <span className="font-semibold text-slate-800">
            {analysis?.text ? analysis.text.split('\n').length.toLocaleString() : 'N/A'}
          </span>
        </div>
      </div>
    </div>
  );
};
