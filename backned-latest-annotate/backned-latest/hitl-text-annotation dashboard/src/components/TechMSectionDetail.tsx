import React, { useState } from 'react';
import {
  FileText,
  Tag,
  Smile,
  Network,
  FolderTree,
  TrendingUp,
  TrendingDown,
  Minus,
  CheckCircle2,
  AlertTriangle,
  Info,
  Calendar,
  Sparkles,
  Search
} from 'lucide-react';
import { AnnotationType, AnnotationSectionConfig } from '../types';
import type { AnnotationComparisonRow } from './TechMAnnotationComparisonChart';

export interface AreaIdentificationRow {
  area_name: string;
  category: string;
  ai_confidence: number | null;
  identification_rate: number;
  trend_direction: string;
  trend_change: string;
  sample_identified: string;
  volume: number;
}
import { ANNOTATION_SECTIONS_MAP } from '../data/mockData';

interface TechMSectionDetailProps {
  data: AnnotationComparisonRow[];
  areas: AreaIdentificationRow[];
  activeSection: AnnotationType;
  onChangeSection: (type: AnnotationType) => void;
}

export const TechMSectionDetail: React.FC<TechMSectionDetailProps> = ({
  data,
  areas,
  activeSection,
  onChangeSection
}) => {
  const [searchQuery, setSearchQuery] = useState('');

  const currentConfig: AnnotationSectionConfig = ANNOTATION_SECTIONS_MAP[activeSection];
  const breakdownIds: Record<string, string[]> = {
    text_extraction: ['text_extraction', 'ocr'],
    ner: ['ner', 'ner_annotation', 'entity_extraction'],
    sentiment: ['sentiment', 'sentiment_analysis'],
    relation: ['relation', 'relation_extraction'],
    classification: ['classification', 'text_classification'],
  };
  const currentBreakdown = data.find((row) => breakdownIds[activeSection]?.includes(row.id));
  const totalDocs = currentBreakdown?.total_docs ?? 0;
  const aiProcessedDocs = currentBreakdown?.ai_processed_docs ?? 0;
  const aiProcessedRate = currentBreakdown?.ai_processed_pct ?? 0;
  const hitlDocs = currentBreakdown?.hitl_docs ?? 0;
  const hitlRate = currentBreakdown?.hitl_pct ?? 0;
  const accuracy = currentBreakdown?.accuracy == null ? 'N/A' : `${currentBreakdown.accuracy}%`;
  const costSaved = currentBreakdown?.cost_saved_dollars == null ? 'N/A' : `$${currentBreakdown.cost_saved_dollars.toLocaleString()}`;

  const sectionTabs: { id: AnnotationType; label: string; icon: React.FC<{ className?: string }> }[] = [
    { id: 'text_extraction', label: '2. Text Extraction', icon: FileText },
    { id: 'ner', label: '3. NER Annotation', icon: Tag },
    { id: 'sentiment', label: '4. Sentiment Analysis', icon: Smile },
    { id: 'relation', label: '5. Relation Extraction', icon: Network },
    { id: 'classification', label: '6. Text Classification', icon: FolderTree }
  ];

  const filteredAreas = areas.filter(
    (a) => {
      const cat = (a.category || '').toLowerCase().trim();
      const name = (a.area_name || '').toLowerCase().trim();
      // Strictly exclude image vision detection labels & bounding box geometry
      if (['box', 'bounding_box', 'bbox', 'polygon', 'polyline', 'point', 'circle', 'detection'].includes(cat)) return false;
      if (['auto-rickshaw', 'bicycle', 'bus', 'car', 'motorcycle', 'road object', 'traffic light', 'traffic sign', 'truck', 'pedestrian', 'person', 'vehicle'].includes(name)) return false;
      return (
        name.includes(searchQuery.toLowerCase()) ||
        cat.includes(searchQuery.toLowerCase()) ||
        (a.sample_identified || '').toLowerCase().includes(searchQuery.toLowerCase())
      );
    }
  );

  return (
    <section className="bg-white border border-[#E5DFD3] rounded-lg p-5 mb-5 shadow-xs">
      
      {/* 5 Section Tabs Switcher */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-3 mb-5 border-b border-[#E5DFD3]">
        {sectionTabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeSection === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onChangeSection(tab.id)}
              className={`flex items-center gap-2 px-3.5 py-2 text-xs font-medium rounded-md transition-all whitespace-nowrap ${
                isActive
                  ? 'bg-[#E31837] text-white shadow-xs font-semibold'
                  : 'bg-[#F6F2EA] text-[#29251D] hover:bg-[#E5DFD3]/60'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Section Title & Description */}
      <div className="mb-4">
        <h3 className="text-base font-bold text-[#29251D]">
          {currentConfig.title} — Analytics & Area Identification
        </h3>
        <p className="text-xs text-[#4D4D4F] mt-0.5">
          {currentConfig.description}
        </p>
      </div>

      {/* DEDICATED SCORECARD FOR ACTIVE ANNOTATION TYPE */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-6">
        
        <div className="bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg p-3">
          <div className="text-[11px] font-medium text-[#4D4D4F]">Total Ingested Docs</div>
          <div className="text-xl font-bold font-mono text-[#29251D] mt-0.5 tabular-nums">
            {totalDocs.toLocaleString()}
          </div>
          <div className="text-[10px] text-[#4D4D4F] mt-1 font-mono">100% of modality volume</div>
        </div>

        <div className="bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg p-3 border-t-2 border-t-[#247153]">
          <div className="text-[11px] font-medium text-[#4D4D4F]">Processed Through AI</div>
          <div className="text-xl font-bold font-mono text-[#247153] mt-0.5 tabular-nums">
            {aiProcessedDocs.toLocaleString()} ({aiProcessedRate}%)
          </div>
          <div className="text-[10px] text-[#247153] mt-1">Directly Auto-Approved</div>
        </div>

        <div className="bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg p-3 border-t-2 border-t-[#8A5200]">
          <div className="text-[11px] font-medium text-[#4D4D4F]">Moved to HITL</div>
          <div className="text-xl font-bold font-mono text-[#8A5200] mt-0.5 tabular-nums">
            {hitlDocs.toLocaleString()} ({hitlRate}%)
          </div>
          <div className="text-[10px] text-[#8A5200] mt-1">Human Lead Review Queue</div>
        </div>

        <div className="bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg p-3">
          <div className="text-[11px] font-medium text-[#4D4D4F]">AI Identification Accuracy</div>
          <div className="text-xl font-bold font-mono text-[#29251D] mt-0.5 tabular-nums">
            {accuracy}
          </div>
          <div className="text-[10px] text-[#4D4D4F] mt-1">Across verified spans</div>
        </div>

        <div className="bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg p-3 border-t-2 border-t-[#E31837]">
          <div className="text-[11px] font-medium text-[#4D4D4F]">Cost Saved in Modality</div>
          <div className="text-xl font-bold font-mono text-[#E31837] mt-0.5 tabular-nums">
            {costSaved}
          </div>
          <div className="text-[10px] text-[#4D4D4F] mt-1">vs 100% manual review</div>
        </div>

      </div>

      {/* TREND IN WHAT AREA AI IS ABLE TO IDENTIFY */}
      <div>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 mb-3 border-b border-[#E5DFD3] gap-2">
          <div>
            <h4 className="text-sm font-semibold text-[#29251D]">
              Area Identification Performance & Trends
            </h4>
            <p className="text-xs text-[#4D4D4F]">
              Breakdown of specific clinical areas, fields, or concepts identified by the AI model
            </p>
          </div>

          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-[#4D4D4F]" />
            <input
              type="text"
              placeholder="Search area or concept..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-[#F6F2EA] border border-[#E5DFD3] rounded-md pl-8 pr-3 py-1.5 text-xs text-[#29251D] placeholder-[#4D4D4F] focus:outline-none w-56"
            />
          </div>
        </div>

        {/* Areas Identification Table / Cards */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-[#E5DFD3] bg-[#F6F2EA] text-[#4D4D4F] font-medium">
                <th className="py-2.5 px-3">Area / Entity Concept</th>
                <th className="py-2.5 px-3">Category</th>
                <th className="py-2.5 px-3 text-right">AI Confidence</th>
                <th className="py-2.5 px-3 text-right">Identification Rate</th>
                <th className="py-2.5 px-3">Trend Direction</th>
                <th className="py-2.5 px-3">Sample AI Identification</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E5DFD3]">
              {filteredAreas.map((area, idx) => {
                const isUp = area.trend_direction === 'up';
                const isDown = area.trend_direction === 'down';

                return (
                  <tr key={idx} className="hover:bg-[#F6F2EA]/60 transition-colors">
                    {/* Area Name */}
                    <td className="py-3 px-3 font-semibold text-[#29251D]">
                      <div>{area.area_name}</div>
                    </td>

                    {/* Category */}
                    <td className="py-3 px-3 text-[#4D4D4F]">
                      <span className="bg-[#F6F2EA] px-2 py-0.5 rounded border border-[#E5DFD3] font-medium text-[11px]">
                        {area.category}
                      </span>
                    </td>

                    {/* AI Confidence */}
                    <td className="py-3 px-3 text-right font-mono font-bold tabular-nums">
                      <span className={area.ai_confidence != null && area.ai_confidence >= 90 ? 'text-[#247153]' : 'text-[#8A5200]'}>
                        {area.ai_confidence == null ? 'N/A' : `${area.ai_confidence}%`}
                      </span>
                    </td>

                    {/* Identification Rate */}
                    <td className="py-3 px-3 text-right font-mono font-bold tabular-nums text-[#29251D]">
                      {area.identification_rate}%
                    </td>

                    {/* Trend */}
                    <td className="py-3 px-3">
                      <div className="flex items-center gap-1 text-[11px] font-medium">
                        {isUp && (
                          <span className="flex items-center gap-1 text-[#247153]">
                            <TrendingUp className="w-3.5 h-3.5" />
                            <span>{area.trend_change}</span>
                          </span>
                        )}
                        {isDown && (
                          <span className="flex items-center gap-1 text-[#9C1936]">
                            <TrendingDown className="w-3.5 h-3.5" />
                            <span>{area.trend_change}</span>
                          </span>
                        )}
                        {!isUp && !isDown && (
                          <span className="flex items-center gap-1 text-[#4D4D4F]">
                            <Minus className="w-3.5 h-3.5" />
                            <span>{area.trend_change}</span>
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Sample */}
                    <td className="py-3 px-3">
                      <div className="font-mono text-[11px] text-[#29251D] bg-[#F6F2EA] p-1.5 rounded border border-[#E5DFD3] max-w-sm truncate" title={area.sample_identified}>
                        {area.sample_identified}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Weekly Volume Trend */}
        <div className="mt-4 pt-4 border-t border-[#E5DFD3] flex flex-col sm:flex-row items-center justify-between text-xs text-[#4D4D4F] gap-2">
          <div className="flex items-center gap-2">
            <Calendar className="w-3.5 h-3.5 text-[#E31837]" />
            <span>Current project auto-approval rate: <strong>{aiProcessedRate}%</strong></span>
          </div>

        </div>

      </div>

    </section>
  );
};
