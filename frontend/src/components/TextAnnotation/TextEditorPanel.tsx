import React, { useState } from 'react';
import {
  FileText,
  Maximize2,
  Minimize2,
  Sparkles,
  CheckCircle2,
} from 'lucide-react';

export interface TextEntity {
  id: string;
  text: string;
  label: 'ORGANIZATION' | 'PERSON' | 'DATE' | 'PRODUCT' | 'LOCATION';
  confidence: number;
  color: string;
  badgeBg: string;
  textColor: string;
  borderColor: string;
  tagColor: string;
}

interface TextEditorPanelProps {
  selectedEntityId: string | null;
  onSelectEntity: (id: string) => void;
  onDeleteEntity: (id: string) => void;
}

export const TextEditorPanel: React.FC<TextEditorPanelProps> = ({
  selectedEntityId,
  onSelectEntity,
  onDeleteEntity,
}) => {
  const [viewMode, setViewMode] = useState<'text' | 'raw'>('text');
  const [isExpanded, setIsExpanded] = useState<boolean>(false);

  const entitiesList: TextEntity[] = [
    {
      id: 'org-1',
      text: "Amazon'",
      label: 'ORGANIZATION',
      confidence: 0.92,
      color: '#10b981',
      badgeBg: 'bg-emerald-50',
      textColor: 'text-emerald-900',
      borderColor: 'border-emerald-300',
      tagColor: 'text-emerald-600',
    },
    {
      id: 'person-1',
      text: 'Sarah Johnson',
      label: 'PERSON',
      confidence: 0.88,
      color: '#3b82f6',
      badgeBg: 'bg-blue-50',
      textColor: 'text-blue-900',
      borderColor: 'border-blue-300',
      tagColor: 'text-blue-600',
    },
    {
      id: 'date-1',
      text: '24 hours',
      label: 'DATE',
      confidence: 0.81,
      color: '#8b5cf6',
      badgeBg: 'bg-purple-50',
      textColor: 'text-purple-900',
      borderColor: 'border-purple-300',
      tagColor: 'text-purple-600',
    },
    {
      id: 'prod-1',
      text: 'wireless earbuds',
      label: 'PRODUCT',
      confidence: 0.76,
      color: '#14b8a6',
      badgeBg: 'bg-teal-50',
      textColor: 'text-teal-900',
      borderColor: 'border-teal-300',
      tagColor: 'text-teal-600',
    },
    {
      id: 'loc-1',
      text: 'San Francisco',
      label: 'LOCATION',
      confidence: 0.73,
      color: '#f59e0b',
      badgeBg: 'bg-amber-50',
      textColor: 'text-amber-900',
      borderColor: 'border-amber-300',
      tagColor: 'text-amber-600',
    },
  ];

  return (
    <div id="text-editor-panel" className="space-y-5">
      {/* Main Text Editor Card */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-2xs overflow-hidden">
        {/* Card Header */}
        <div className="flex items-center justify-between border-b border-slate-200/90 bg-white px-5 py-3.5">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-blue-600" />
            <h3 className="text-sm font-bold text-slate-900">Text Editor</h3>
          </div>

          <div className="flex items-center gap-2">
            {/* Text / Raw Toggle */}
            <div className="flex items-center rounded-lg border border-slate-200 p-0.5 bg-slate-50">
              <button
                id="btn-view-text-mode"
                onClick={() => setViewMode('text')}
                className={`rounded-md px-3 py-1 text-xs font-semibold transition cursor-pointer ${
                  viewMode === 'text'
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Text
              </button>
              <button
                id="btn-view-raw-mode"
                onClick={() => setViewMode('raw')}
                className={`rounded-md px-3 py-1 text-xs font-semibold transition cursor-pointer ${
                  viewMode === 'raw'
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Raw
              </button>
            </div>

            {/* Maximize Button */}
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="p-1.5 rounded-lg border border-slate-200 text-slate-500 hover:text-slate-900 hover:bg-slate-50 transition cursor-pointer"
              title={isExpanded ? 'Minimize' : 'Expand full width'}
            >
              {isExpanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {/* Card Body with Annotated Text */}
        <div className="p-6 md:p-8 text-[15px] md:text-base leading-[2.6] md:leading-[2.8] text-slate-800 tracking-normal select-text">
          {viewMode === 'raw' ? (
            <pre className="font-mono text-xs text-slate-700 bg-slate-50 p-4 rounded-lg overflow-x-auto leading-relaxed whitespace-pre-wrap">
              {`I recently had an excellent experience with Amazon' customer support team. I spoke with Sarah Johnson who was very helpful and resolved my issue within 24 hours. The product I purchased, a wireless earbuds set, stopped working, and she guided me through the return process. I am based in San Francisco so I was worried about the shipping time, but it was surprisingly fast. Overall, I'm very satisfied with the service and would recommend Amazon to anyone.`}
            </pre>
          ) : (
            <div className="space-y-4">
              <p>
                I recently had an excellent experience with{' '}
                {/* Organization 1 */}
                <span
                  id="entity-org-1"
                  onClick={() => onSelectEntity('org-1')}
                  className={`relative inline-flex flex-col items-start rounded-md border border-emerald-300 bg-emerald-50/90 px-2.5 py-0.5 align-baseline cursor-pointer transition-all hover:ring-2 hover:ring-emerald-400 ${
                    selectedEntityId === 'org-1' ? 'ring-2 ring-emerald-500 shadow-xs' : ''
                  }`}
                >
                  <span className="text-[9px] font-black tracking-widest text-emerald-600 uppercase leading-none pb-0.5">
                    ORGANIZATION
                  </span>
                  <span className="font-medium text-emerald-950 leading-tight">Amazon&#39;</span>
                </span>{' '}
                customer support team. I spoke with{' '}
                {/* Person 1 */}
                <span
                  id="entity-person-1"
                  onClick={() => onSelectEntity('person-1')}
                  className={`relative inline-flex flex-col items-start rounded-md border border-blue-300 bg-blue-50/90 px-2.5 py-0.5 align-baseline cursor-pointer transition-all hover:ring-2 hover:ring-blue-400 ${
                    selectedEntityId === 'person-1' ? 'ring-2 ring-blue-500 shadow-xs' : ''
                  }`}
                >
                  <span className="text-[9px] font-black tracking-widest text-blue-600 uppercase leading-none pb-0.5">
                    PERSON
                  </span>
                  <span className="font-medium text-blue-950 leading-tight">Sarah Johnson</span>
                </span>{' '}
                who was very helpful and resolved my issue within{' '}
                {/* Date 1 */}
                <span
                  id="entity-date-1"
                  onClick={() => onSelectEntity('date-1')}
                  className={`relative inline-flex flex-col items-start rounded-md border border-purple-300 bg-purple-50/90 px-2.5 py-0.5 align-baseline cursor-pointer transition-all hover:ring-2 hover:ring-purple-400 ${
                    selectedEntityId === 'date-1' ? 'ring-2 ring-purple-500 shadow-xs' : ''
                  }`}
                >
                  <span className="text-[9px] font-black tracking-widest text-purple-600 uppercase leading-none pb-0.5">
                    DATE
                  </span>
                  <span className="font-medium text-purple-950 leading-tight">24 hours</span>
                </span>{' '}
                The product I purchased, a{' '}
                {/* Product 1 */}
                <span
                  id="entity-prod-1"
                  onClick={() => onSelectEntity('prod-1')}
                  className={`relative inline-flex flex-col items-start rounded-md border border-teal-300 bg-teal-50/90 px-2.5 py-0.5 align-baseline cursor-pointer transition-all hover:ring-2 hover:ring-teal-400 ${
                    selectedEntityId === 'prod-1' ? 'ring-2 ring-teal-500 shadow-xs' : ''
                  }`}
                >
                  <span className="text-[9px] font-black tracking-widest text-teal-600 uppercase leading-none pb-0.5">
                    PRODUCT
                  </span>
                  <span className="font-medium text-teal-950 leading-tight">wireless earbuds</span>
                </span>{' '}
                set, stopped working, and she guided me through the return process. I am based in{' '}
                {/* Location 1 */}
                <span
                  id="entity-loc-1"
                  onClick={() => onSelectEntity('loc-1')}
                  className={`relative inline-flex flex-col items-start rounded-md border border-amber-300 bg-amber-50/90 px-2.5 py-0.5 align-baseline cursor-pointer transition-all hover:ring-2 hover:ring-amber-400 ${
                    selectedEntityId === 'loc-1' ? 'ring-2 ring-amber-500 shadow-xs' : ''
                  }`}
                >
                  <span className="text-[9px] font-black tracking-widest text-amber-600 uppercase leading-none pb-0.5">
                    LOCATION
                  </span>
                  <span className="font-medium text-amber-950 leading-tight">San Francisco</span>
                </span>{' '}
                so I was worried about the shipping time, but it was surprisingly fast. Overall, I&#39;m
                very satisfied with the service and would recommend{' '}
                {/* Organization 2 */}
                <span
                  id="entity-org-2"
                  onClick={() => onSelectEntity('org-1')}
                  className={`relative inline-flex flex-col items-start rounded-md border border-emerald-300 bg-emerald-50/90 px-2.5 py-0.5 align-baseline cursor-pointer transition-all hover:ring-2 hover:ring-emerald-400 ${
                    selectedEntityId === 'org-1' ? 'ring-2 ring-emerald-500 shadow-xs' : ''
                  }`}
                >
                  <span className="text-[9px] font-black tracking-widest text-emerald-600 uppercase leading-none pb-0.5">
                    ORGANIZATION
                  </span>
                  <span className="font-medium text-emerald-950 leading-tight">Amazon</span>
                </span>{' '}
                to anyone.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* AI Prediction Box underneath Text Editor */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs">
        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-blue-600" />
            <h3 className="text-sm font-bold text-slate-900">AI Prediction</h3>
          </div>

          <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-blue-700 border border-blue-100">
            Confidence: 0.87
          </span>
        </div>

        {/* Detected Entities List */}
        <div className="mt-3 divide-y divide-slate-100">
          {entitiesList.map((item) => (
            <div
              key={item.id}
              onClick={() => onSelectEntity(item.id)}
              className={`flex items-center justify-between py-2.5 px-3 rounded-lg cursor-pointer transition ${
                selectedEntityId === item.id ? 'bg-blue-50/70 font-semibold' : 'hover:bg-slate-50'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-600">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                </span>
                <span className="text-xs font-bold text-slate-900">{item.text}</span>
                <span
                  className="rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
                  style={{
                    backgroundColor: `${item.color}15`,
                    color: item.color,
                  }}
                >
                  {item.label}
                </span>
              </div>

              <span className="text-xs font-semibold text-slate-700">
                {Math.round(item.confidence * 100)}%
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
