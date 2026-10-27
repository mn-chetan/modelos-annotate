import React, { useState } from 'react';
import {
  X,
  Sparkles,
  Download,
  Copy,
  CheckCircle2
} from 'lucide-react';
import { ACTIVE_LEARNING_ITEMS } from '../../data/mockData';

interface ActiveLearningExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onExportSuccess: (format: string, count: number) => void;
}

export const ActiveLearningExportModal: React.FC<ActiveLearningExportModalProps> = ({
  isOpen,
  onClose,
  onExportSuccess
}) => {
  const [format, setFormat] = useState<'jsonl' | 'hf' | 'conll'>('jsonl');
  const [targetUri, setTargetUri] = useState('s3://mednlp-models-store/active_learning/run_v15_candidate.jsonl');
  const [isExporting, setIsExporting] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const handleExport = () => {
    setIsExporting(true);
    setTimeout(() => {
      setIsExporting(false);
      onExportSuccess(format.toUpperCase(), 350);
      onClose();
    }, 1100);
  };

  const sampleJsonl = `{"id":"DOC-AL-8821","tokens":["Patient","reports","intermittent","orthostatic","lightheadedness","following","titrating","hydralazine","to","50mg","TID","."],"ner_tags":["O","O","O","B-SYMPTOM","I-SYMPTOM","O","O","B-MED","O","B-DOSAGE","I-DOSAGE","O"],"epistemic_entropy":1.84,"sampling_strategy":"margin_uncertainty"}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#29251D]/60 backdrop-blur-xs">
      <div className="bg-white border border-[#E5DFD3] rounded-lg max-w-2xl w-full shadow-xl flex flex-col max-h-[90vh] overflow-hidden">
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#E5DFD3] bg-[#F6F2EA]">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-md bg-[#29251D] text-white flex items-center justify-center">
              <Download className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-[#29251D]">
                Export Active Learning Queue to Retraining
              </h3>
              <p className="text-xs text-[#4D4D4F]">
                350 high-uncertainty edge cases curated from recent human interventions
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
          
          {/* Format Selection */}
          <div>
            <label className="block text-xs font-semibold text-[#29251D] mb-2">
              Export Serialization Format
            </label>
            <div className="grid grid-cols-3 gap-2.5">
              <button
                type="button"
                onClick={() => setFormat('jsonl')}
                className={`p-3 rounded-lg border text-left transition-all ${
                  format === 'jsonl'
                    ? 'bg-[#F6F2EA] border-[#E31837] text-[#29251D] ring-1 ring-[#E31837]/30'
                    : 'bg-white border-[#E5DFD3] text-[#4D4D4F] hover:bg-[#F6F2EA]/60'
                }`}
              >
                <div className="text-xs font-bold font-mono text-[#29251D]">JSONL (vLLM)</div>
                <div className="text-[10px] text-[#4D4D4F] mt-0.5">Token spans + offsets</div>
              </button>

              <button
                type="button"
                onClick={() => setFormat('hf')}
                className={`p-3 rounded-lg border text-left transition-all ${
                  format === 'hf'
                    ? 'bg-[#F6F2EA] border-[#E31837] text-[#29251D] ring-1 ring-[#E31837]/30'
                    : 'bg-white border-[#E5DFD3] text-[#4D4D4F] hover:bg-[#F6F2EA]/60'
                }`}
              >
                <div className="text-xs font-bold font-mono text-[#29251D]">HuggingFace Parquet</div>
                <div className="text-[10px] text-[#4D4D4F] mt-0.5">Dataset features format</div>
              </button>

              <button
                type="button"
                onClick={() => setFormat('conll')}
                className={`p-3 rounded-lg border text-left transition-all ${
                  format === 'conll'
                    ? 'bg-[#F6F2EA] border-[#E31837] text-[#29251D] ring-1 ring-[#E31837]/30'
                    : 'bg-white border-[#E5DFD3] text-[#4D4D4F] hover:bg-[#F6F2EA]/60'
                }`}
              >
                <div className="text-xs font-bold font-mono text-[#29251D]">CoNLL-2003 (BIO)</div>
                <div className="text-[10px] text-[#4D4D4F] mt-0.5">Tab-separated tokens</div>
              </button>
            </div>
          </div>

          {/* Target Bucket Destination */}
          <div>
            <label className="block text-xs font-semibold text-[#29251D] mb-1">
              Storage Target URI
            </label>
            <input
              type="text"
              value={targetUri}
              onChange={(e) => setTargetUri(e.target.value)}
              className="w-full bg-[#F6F2EA] border border-[#E5DFD3] rounded-md px-3 py-1.5 text-xs font-mono text-[#29251D] focus:outline-none"
            />
          </div>

          {/* Sample Edge Cases preview */}
          <div>
            <div className="text-xs font-semibold text-[#29251D] mb-1.5 flex items-center justify-between">
              <span>Candidate Edge Case Samples (Entropy &gt; 1.6)</span>
              <span className="text-[11px] font-mono text-[#247153] font-medium">350 items ready</span>
            </div>
            <div className="space-y-2">
              {ACTIVE_LEARNING_ITEMS.map((item) => (
                <div
                  key={item.id}
                  className="p-2.5 bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg text-xs"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono font-bold text-[#29251D]">{item.docId}</span>
                    <span className="font-mono text-[#247153] text-[11px] font-semibold">
                      Uncertainty: {item.uncertaintyScore} · Entropy: {item.entropy}
                    </span>
                  </div>
                  <div className="text-[#29251D] font-mono text-[11px] mb-1">
                    "{item.snippet}"
                  </div>
                  <div className="text-[10px] text-[#4D4D4F]">
                    Reason: {item.suggestedAction}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Sample Payload Preview */}
          <div className="bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg p-3">
            <div className="flex items-center justify-between text-[11px] text-[#4D4D4F] mb-1">
              <span className="font-mono font-medium">Payload Preview (Row 1):</span>
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard?.writeText(sampleJsonl);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1500);
                }}
                className="text-[#4D4D4F] hover:text-[#29251D] flex items-center gap-1 text-[10px]"
              >
                <Copy className="w-3 h-3" />
                <span>{copied ? 'Copied' : 'Copy Row'}</span>
              </button>
            </div>
            <pre className="text-[11px] font-mono text-[#29251D] overflow-x-auto whitespace-pre-wrap leading-tight bg-white p-2 rounded border border-[#E5DFD3]">
              {sampleJsonl}
            </pre>
          </div>

        </div>

        {/* Footer */}
        <div className="p-4 border-t border-[#E5DFD3] bg-[#F6F2EA] flex items-center justify-between">
          <div className="text-xs text-[#4D4D4F]">
            Will trigger LoRA candidate run v1.5
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 text-xs bg-white border border-[#E5DFD3] hover:bg-[#F6F2EA] text-[#29251D] rounded transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={isExporting}
              onClick={handleExport}
              className="px-4 py-1.5 text-xs bg-[#E31837] hover:bg-[#5F0229] disabled:opacity-50 text-white font-semibold rounded flex items-center gap-1.5 transition-colors shadow-xs"
            >
              {isExporting ? (
                <>
                  <CheckCircle2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Transferring 350 docs...</span>
                </>
              ) : (
                <>
                  <Download className="w-3.5 h-3.5" />
                  <span>Execute Export (350 Docs)</span>
                </>
              )}
            </button>
          </div>
        </div>

      </div>
    </div>
  );
};
