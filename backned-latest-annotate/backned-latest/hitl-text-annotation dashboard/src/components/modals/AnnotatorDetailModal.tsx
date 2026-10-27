import React, { useState } from 'react';
import {
  X,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Award,
  ShieldAlert,
  BookOpen
} from 'lucide-react';
import { AnnotatorRecord } from '../../types';

interface AnnotatorDetailModalProps {
  annotator: AnnotatorRecord | null;
  onClose: () => void;
  onActionComplete: (msg: string) => void;
}

export const AnnotatorDetailModal: React.FC<AnnotatorDetailModalProps> = ({
  annotator,
  onClose,
  onActionComplete
}) => {
  if (!annotator) return null;

  const isFlagged = annotator.status === 'flagged';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#29251D]/60 backdrop-blur-xs">
      <div className="bg-white border border-[#E5DFD3] rounded-lg max-w-2xl w-full shadow-xl flex flex-col max-h-[90vh] overflow-hidden">
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#E5DFD3] bg-[#F6F2EA]">
          <div className="flex items-center gap-3">
            <div
              className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm ${
                isFlagged
                  ? 'bg-[#9C1936] text-white'
                  : 'bg-[#29251D] text-white'
              }`}
            >
              {annotator.avatarSeed}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-[#29251D]">{annotator.name}</h3>
                {isFlagged && (
                  <span className="text-[10px] bg-[#9C1936]/10 text-[#9C1936] px-2 py-0.5 rounded-xs font-semibold border border-[#9C1936]/30">
                    Rubber-Stamping Alert
                  </span>
                )}
              </div>
              <p className="text-xs text-[#4D4D4F]">
                {annotator.role} · {annotator.email}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 text-[#4D4D4F] hover:text-[#29251D] rounded hover:bg-[#E5DFD3]/60 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 overflow-y-auto space-y-4">
          
          {/* Flag Callout */}
          {annotator.flagReason && (
            <div className="p-3 bg-[#9C1936]/10 border border-[#9C1936]/30 rounded-lg text-xs text-[#9C1936] flex items-start gap-2.5">
              <ShieldAlert className="w-4 h-4 text-[#9C1936] shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold">Safeguard Heuristic Triggered:</span>
                <p className="text-[#29251D] mt-0.5 leading-relaxed">
                  {annotator.flagReason}
                </p>
              </div>
            </div>
          )}

          {/* Key Metrics Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
            <div className="p-3 bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg">
              <div className="text-[11px] text-[#4D4D4F]">Avg Review Time</div>
              <div
                className={`text-lg font-bold font-mono mt-0.5 ${
                  annotator.avgTimeSec < 20 ? 'text-[#9C1936]' : 'text-[#29251D]'
                }`}
              >
                {annotator.avgTimeSec}s
              </div>
              <div className="text-[10px] text-[#4D4D4F]">Team avg: 54s</div>
            </div>

            <div className="p-3 bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg">
              <div className="text-[11px] text-[#4D4D4F]">AI Edit Rate</div>
              <div
                className={`text-lg font-bold font-mono mt-0.5 ${
                  annotator.aiEditRate < 2 ? 'text-[#9C1936]' : 'text-[#247153]'
                }`}
              >
                {annotator.aiEditRate}%
              </div>
              <div className="text-[10px] text-[#4D4D4F]">Team avg: 14.8%</div>
            </div>

            <div className="p-3 bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg">
              <div className="text-[11px] text-[#4D4D4F]">Audit Pass Rate</div>
              <div
                className={`text-lg font-bold font-mono mt-0.5 ${
                  annotator.auditPassRate < 80 ? 'text-[#9C1936]' : 'text-[#247153]'
                }`}
              >
                {annotator.auditPassRate}%
              </div>
              <div className="text-[10px] text-[#4D4D4F]">Threshold: 90%</div>
            </div>

            <div className="p-3 bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg">
              <div className="text-[11px] text-[#4D4D4F]">Total Throughput</div>
              <div className="text-lg font-bold font-mono text-[#29251D] mt-0.5">
                {annotator.completedDocs}
              </div>
              <div className="text-[10px] text-[#4D4D4F]">docs completed</div>
            </div>
          </div>

          {/* Recent Audits */}
          <div>
            <div className="text-xs font-semibold text-[#29251D] mb-2">
              Recent Lead Auditor Spot-Checks
            </div>
            <div className="space-y-2">
              {annotator.recentAudits.map((aud) => (
                <div
                  key={aud.id}
                  className="p-3 bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg text-xs"
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-[#29251D]">{aud.docId}</span>
                      <span className="text-[11px] text-[#4D4D4F]">· {aud.date}</span>
                    </div>
                    {aud.result === 'pass' ? (
                      <span className="flex items-center gap-1 text-[#247153] font-mono text-[11px] font-semibold">
                        <CheckCircle2 className="w-3.5 h-3.5" /> Pass
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-[#9C1936] font-mono text-[11px] font-bold">
                        <XCircle className="w-3.5 h-3.5" /> QA Fail
                      </span>
                    )}
                  </div>
                  <p className="text-[#4D4D4F]">{aud.notes}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Lead Actions */}
          <div className="pt-2 border-t border-[#E5DFD3]">
            <div className="text-xs font-semibold text-[#29251D] mb-2">
              Intervention Management
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <button
                type="button"
                onClick={() => {
                  onActionComplete(`Issued clinical guideline calibration quiz to ${annotator.name}`);
                  onClose();
                }}
                className="p-2.5 bg-white hover:bg-[#F6F2EA] border border-[#E5DFD3] text-[#29251D] rounded-lg text-xs flex items-center justify-center gap-2 transition-colors font-medium shadow-xs"
              >
                <BookOpen className="w-3.5 h-3.5 text-[#185F8D]" />
                <span>Issue Calibration Quiz</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  onActionComplete(`Adjusted ${annotator.name}'s queue quota with mandatory shadow review`);
                  onClose();
                }}
                className="p-2.5 bg-white hover:bg-[#F6F2EA] border border-[#E5DFD3] text-[#29251D] rounded-lg text-xs flex items-center justify-center gap-2 transition-colors font-medium shadow-xs"
              >
                <Clock className="w-3.5 h-3.5 text-[#8A5200]" />
                <span>Cap Quota & Shadow Review</span>
              </button>
            </div>
          </div>

        </div>

        {/* Footer */}
        <div className="p-4 border-t border-[#E5DFD3] bg-[#F6F2EA] flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-xs bg-[#29251D] hover:bg-[#4A453D] text-white rounded transition-colors"
          >
            Dismiss
          </button>
        </div>

      </div>
    </div>
  );
};
