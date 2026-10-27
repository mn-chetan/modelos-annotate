import React, { useState } from 'react';
import {
  X,
  ShieldAlert,
  Clock,
  AlertTriangle,
  UserCheck,
  CheckCircle2,
  Send
} from 'lucide-react';
import { LOW_LATENCY_SUBMISSIONS } from '../../data/mockData';

interface LeadAuditModalProps {
  isOpen: boolean;
  onClose: () => void;
  onDispatchAudit: (details: { sampleSize: number; leadAuditor: string; targetAnnotator: string }) => void;
}

export const LeadAuditModal: React.FC<LeadAuditModalProps> = ({
  isOpen,
  onClose,
  onDispatchAudit
}) => {
  const [sampleSize, setSampleSize] = useState(50);
  const [leadAuditor, setLeadAuditor] = useState('Dr. Aris Thorne');
  const [targetAnnotator, setTargetAnnotator] = useState('Devon Vance');
  const [dispatched, setDispatched] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setDispatched(true);
    setTimeout(() => {
      onDispatchAudit({ sampleSize, leadAuditor, targetAnnotator });
      setDispatched(false);
      onClose();
    }, 1000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#29251D]/60 backdrop-blur-xs">
      <div className="bg-white border border-[#E5DFD3] rounded-lg max-w-2xl w-full shadow-xl flex flex-col max-h-[90vh] overflow-hidden">
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#E5DFD3] bg-[#F6F2EA]">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-md bg-[#9C1936] text-white flex items-center justify-center">
              <ShieldAlert className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-[#29251D]">
                Trigger Lead Auditor Safeguard Re-check
              </h3>
              <p className="text-xs text-[#4D4D4F]">
                89 low-latency submissions flagged by heuristic safeguard rules
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
        <form onSubmit={handleSubmit} className="p-5 overflow-y-auto space-y-4">
          
          {/* Warning Banner */}
          <div className="p-3 bg-[#9C1936]/10 border border-[#9C1936]/30 rounded-lg text-xs text-[#9C1936] flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-[#9C1936] shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold">Rubber-Stamping Safeguard Heuristic Active:</span>
              <p className="text-[#29251D] mt-0.5 leading-relaxed">
                Review sessions taking less than 15 seconds with 0 modifications on complex clinical discharge notes indicate rapid button clicking without manual review.
              </p>
            </div>
          </div>

          {/* Sample Flagged Submissions preview */}
          <div>
            <div className="text-xs font-semibold text-[#29251D] mb-2 flex items-center justify-between">
              <span>Recent Flagged Telemetry Sessions</span>
              <span className="text-[11px] font-mono text-[#4D4D4F]">Heuristic: &lt;15s latency</span>
            </div>

            <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
              {LOW_LATENCY_SUBMISSIONS.map((sub) => (
                <div
                  key={sub.id}
                  className="p-2 bg-[#F6F2EA] border border-[#E5DFD3] rounded flex items-center justify-between text-xs"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-semibold text-[#29251D]">{sub.docId}</span>
                    <span className="text-[#4D4D4F]">· {sub.annotatorName}</span>
                  </div>
                  <div className="flex items-center gap-3 font-mono">
                    <span className="text-[#9C1936] font-bold flex items-center gap-1">
                      <Clock className="w-3 h-3" /> {sub.elapsedSec}s
                    </span>
                    <span className="text-[#4D4D4F] text-[11px]">{sub.editsMade} edits</span>
                    <span className="text-[10px] bg-[#9C1936]/10 text-[#9C1936] px-1.5 py-0.2 rounded font-semibold border border-[#9C1936]/20">
                      {sub.riskLevel}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Audit Configuration */}
          <div className="space-y-3 pt-2 border-t border-[#E5DFD3]">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-[#29251D] mb-1">
                  Target Annotator Queue
                </label>
                <select
                  value={targetAnnotator}
                  onChange={(e) => setTargetAnnotator(e.target.value)}
                  className="w-full bg-[#F6F2EA] border border-[#E5DFD3] rounded-md p-2 text-xs text-[#29251D] focus:outline-none"
                >
                  <option value="Devon Vance">Devon Vance (Flagged - 11s avg)</option>
                  <option value="Carlos Mendez">Carlos Mendez (44s avg)</option>
                  <option value="Priya Sen">Priya Sen (In Calibration)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#29251D] mb-1">
                  Assign Lead Reviewer
                </label>
                <select
                  value={leadAuditor}
                  onChange={(e) => setLeadAuditor(e.target.value)}
                  className="w-full bg-[#F6F2EA] border border-[#E5DFD3] rounded-md p-2 text-xs text-[#29251D] focus:outline-none"
                >
                  <option value="Dr. Aris Thorne">Dr. Aris Thorne (Lead Clinical Reviewer)</option>
                  <option value="Elena Rostova">Elena Rostova (Senior BioNLP)</option>
                  <option value="Marcus Brody">Marcus Brody (QA Auditor)</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-[#29251D] mb-1">
                Audit Sample Size (Random Stratified Sampling)
              </label>
              <div className="flex items-center gap-3">
                {[25, 50, 89].map((size) => (
                  <button
                    key={size}
                    type="button"
                    onClick={() => setSampleSize(size)}
                    className={`px-3 py-1.5 text-xs rounded border transition-colors ${
                      sampleSize === size
                        ? 'bg-[#E31837] text-white border-[#E31837] font-semibold'
                        : 'bg-[#F6F2EA] text-[#29251D] border-[#E5DFD3] hover:bg-[#E5DFD3]'
                    }`}
                  >
                    {size === 89 ? 'All 89 Flagged' : `${size} Documents`}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Action button */}
          <div className="pt-3">
            <button
              type="submit"
              disabled={dispatched}
              className="w-full py-2.5 px-4 bg-[#E31837] hover:bg-[#5F0229] disabled:opacity-50 text-white font-semibold text-xs rounded-lg flex items-center justify-center gap-2 transition-colors shadow-xs"
            >
              {dispatched ? (
                <>
                  <CheckCircle2 className="w-4 h-4 animate-spin" />
                  <span>Dispatching Audit Task...</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>Dispatch Urgent Audit ({sampleSize} Docs to {leadAuditor})</span>
                </>
              )}
            </button>
          </div>

        </form>

      </div>
    </div>
  );
};
