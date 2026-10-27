import React from 'react';
import { X, Sliders } from 'lucide-react';

interface CalibrationGuideModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const CalibrationGuideModal: React.FC<CalibrationGuideModalProps> = ({
  isOpen,
  onClose
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#29251D]/60 backdrop-blur-xs">
      <div className="bg-white border border-[#E5DFD3] rounded-lg max-w-xl w-full shadow-xl flex flex-col overflow-hidden">
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#E5DFD3] bg-[#F6F2EA]">
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4 text-[#E31837]" />
            <h3 className="text-sm font-semibold text-[#29251D]">
              Tech Mahindra HITL Calibration Architecture
            </h3>
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
        <div className="p-5 space-y-3.5 text-xs text-[#29251D] leading-relaxed">
          <div className="p-3 bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg">
            <div className="font-semibold text-[#29251D] mb-1">
              Confidence Threshold (τ = 0.90)
            </div>
            <p className="text-[#4D4D4F]">
              Spans and documents where the model posterior probability exceeds 0.90 are automatically approved, yielding 64.2% automated throughput across standard EHR templates.
            </p>
          </div>

          <div className="p-3 bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg">
            <div className="font-semibold text-[#29251D] mb-1">
              Human-in-the-Loop Safeguard Triage
            </div>
            <p className="text-[#4D4D4F]">
              Items below threshold or containing high clinical risk indications (such as drug contraindications or low review velocity) are triaged to certified clinical annotators and lead arbiters.
            </p>
          </div>

          <div className="p-3 bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg">
            <div className="font-semibold text-[#29251D] mb-1">
              Active Learning Closed-Loop Retraining
            </div>
            <p className="text-[#4D4D4F]">
              Human interventions and boundary corrections are automatically serialized for weekly model fine-tuning checkpoints.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-[#E5DFD3] bg-[#F6F2EA] flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-xs bg-[#29251D] hover:bg-[#4A453D] text-white rounded transition-colors"
          >
            Close
          </button>
        </div>

      </div>
    </div>
  );
};
