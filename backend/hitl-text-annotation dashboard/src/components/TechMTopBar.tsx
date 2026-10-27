import React, { useState } from 'react';
import {
  Layers,
  ChevronDown,
  Download,
  HelpCircle,
  CheckCircle2,
} from 'lucide-react';
import { ProjectOption } from '../types';

interface TechMTopBarProps {
  projects: ProjectOption[];
  selectedProject: ProjectOption;
  onSelectProject: (p: ProjectOption) => void;
  onOpenExportModal: () => void;
  onOpenCalibrationGuide: () => void;
}

export const TechMTopBar: React.FC<TechMTopBarProps> = ({
  projects,
  selectedProject,
  onSelectProject,
  onOpenExportModal,
  onOpenCalibrationGuide,
}) => {
  const [projectOpen, setProjectOpen] = useState(false);

  return (
    <header className="bg-white border-b border-[#E5DFD3] sticky top-0 z-30 shadow-xs">
      {/* Top Application Shell Container */}
      <div className="max-w-[1720px] mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16 gap-4">
          
          {/* Brand Zone (Tech Mahindra Red Lozenge + Wordmark + Product Name) */}
          <div className="flex items-center gap-4 shrink-0">
            {/* Tech Mahindra Lozenge Mark (45-degree tilted Rise beam diamond) */}
            <div className="flex items-center gap-2.5">
              <div
                className="w-7 h-7 bg-[#E31837] rounded-sm transform rotate-45 flex items-center justify-center shadow-xs"
                title="Tech Mahindra"
              >
                <div className="w-2.5 h-2.5 bg-white rounded-xs transform -rotate-45" />
              </div>
              <div className="flex flex-col">
                <span className="text-base font-bold tracking-tight text-[#29251D] leading-tight">
                  Tech Mahindra
                </span>
                <span className="text-[11px] font-medium text-[#4D4D4F] leading-tight">
                  HITL Annotation &amp; Model Alignment Studio
                </span>
              </div>
            </div>
          </div>

          {/* Dynamic Active Text Project Selector & Live Backend Status */}
          <div className="flex items-center gap-3">
            {/* Dynamic Project Selector */}
            <div className="relative">
              <button
                type="button"
                id="hitl-text-project-selector"
                onClick={() => setProjectOpen(!projectOpen)}
                className="flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold bg-[#F6F2EA] hover:bg-[#E5DFD3]/70 text-[#29251D] border border-[#E5DFD3] rounded-lg transition-colors cursor-pointer shadow-2xs"
                title="Switch active text annotation project"
              >
                <Layers className="w-3.5 h-3.5 text-[#E31837] shrink-0" />
                <span className="max-w-[240px] truncate">{selectedProject?.name || 'Select Text Project'}</span>
                <ChevronDown className="w-3.5 h-3.5 text-[#4D4D4F] shrink-0" />
              </button>

              {projectOpen && (
                <div
                  id="hitl-text-project-dropdown"
                  className="absolute left-0 mt-1.5 w-72 bg-white border border-[#E5DFD3] rounded-xl shadow-xl py-2 z-50 animate-in fade-in zoom-in-95 duration-100"
                >
                  <div className="px-3.5 py-1 text-[11px] font-bold text-[#8A5200] uppercase tracking-wider border-b border-[#E5DFD3]/60 mb-1">
                    Text Annotation Projects ({projects.length})
                  </div>
                  <div className="max-h-64 overflow-y-auto divide-y divide-[#E5DFD3]/40">
                    {projects.map((proj) => (
                      <button
                        key={proj.id}
                        type="button"
                        onClick={() => {
                          onSelectProject(proj);
                          setProjectOpen(false);
                        }}
                        className={`w-full text-left px-3.5 py-2 text-xs flex items-center justify-between hover:bg-[#F6F2EA] transition cursor-pointer ${
                          proj.id === selectedProject?.id ? 'text-[#E31837] font-bold bg-[#F8B4A3]/20' : 'text-[#29251D]'
                        }`}
                      >
                        <div className="truncate pr-2">
                          <div className="truncate font-semibold">{proj.name}</div>
                          <div className="text-[10px] text-[#4D4D4F] truncate">{proj.domain}</div>
                        </div>
                        {proj.id === selectedProject?.id && <CheckCircle2 className="w-4 h-4 text-[#E31837] shrink-0" />}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Live Pipeline Status Pill */}
            <span className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Live HITL Pipeline
            </span>
          </div>

          {/* Right Actions: Export Queue + Guidance */}
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              id="export-hitl-queue-button"
              onClick={onOpenExportModal}
              className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-bold bg-[#E31837] hover:bg-[#5F0229] text-white rounded-lg transition-colors shadow-xs cursor-pointer"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export Queue</span>
            </button>

            <button
              type="button"
              onClick={onOpenCalibrationGuide}
              className="p-1.5 text-[#4D4D4F] hover:text-[#29251D] hover:bg-[#F6F2EA] rounded-lg transition-colors cursor-pointer"
              title="Calibration &amp; Triage Documentation"
              aria-label="Calibration &amp; Triage Documentation"
            >
              <HelpCircle className="w-4 h-4" />
            </button>
          </div>

        </div>
      </div>
    </header>
  );
};
