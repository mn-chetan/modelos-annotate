import React, { useState } from 'react';
import {
  X,
  Users2,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  ArrowLeft,
  Clock,
  Sparkles
} from 'lucide-react';
import { DisputedItem } from '../../types';

interface DisputeResolutionModalProps {
  isOpen: boolean;
  onClose: () => void;
  disputedItems: DisputedItem[];
  onResolveDispute: (itemId: string, chosenResolution: string) => void;
}

export const DisputeResolutionModal: React.FC<DisputeResolutionModalProps> = ({
  isOpen,
  onClose,
  disputedItems,
  onResolveDispute
}) => {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [resolutionNotice, setResolutionNotice] = useState<string | null>(null);

  if (!isOpen) return null;

  const currentItem = disputedItems[currentIndex];

  const handleResolve = (choice: 'A' | 'B' | 'Model') => {
    if (!currentItem) return;
    let text = '';
    if (choice === 'A') {
      text = `Accepted Annotator A (${currentItem.annotatorA.name}): "${currentItem.annotatorA.spanText}" [${currentItem.annotatorA.label}]`;
    } else if (choice === 'B') {
      text = `Accepted Annotator B (${currentItem.annotatorB.name}): "${currentItem.annotatorB.spanText}" [${currentItem.annotatorB.label}]`;
    } else {
      text = `Accepted Model Baseline: "${currentItem.modelPrediction.spanText}" [${currentItem.modelPrediction.label}]`;
    }

    onResolveDispute(currentItem.id, text);
    setResolutionNotice(text);
    setTimeout(() => {
      setResolutionNotice(null);
      if (currentIndex < disputedItems.length - 1) {
        setCurrentIndex((prev) => prev + 1);
      }
    }, 1200);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#29251D]/60 backdrop-blur-xs">
      <div className="bg-white border border-[#E5DFD3] rounded-lg max-w-3xl w-full shadow-xl flex flex-col max-h-[90vh] overflow-hidden">
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#E5DFD3] bg-[#F6F2EA]">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-md bg-[#E31837] text-white flex items-center justify-center">
              <Users2 className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-[#29251D]">
                Dispute Resolution Arbitration Console
              </h3>
              <p className="text-xs text-[#4D4D4F]">
                Item {currentIndex + 1} of {disputedItems.length} · Doc ID: {currentItem?.docId}
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

        {/* Body */}
        <div className="p-5 overflow-y-auto space-y-4">
          {resolutionNotice && (
            <div className="p-3 bg-[#247153]/10 border border-[#247153]/30 rounded-md text-xs text-[#247153] flex items-center gap-2 font-medium">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{resolutionNotice}</span>
            </div>
          )}

          {currentItem ? (
            <>
              {/* Context */}
              <div className="flex items-center justify-between text-xs text-[#4D4D4F]">
                <span className="font-medium text-[#29251D]">{currentItem.context}</span>
                <span className="font-mono text-[11px] bg-[#F6F2EA] px-2 py-0.5 rounded border border-[#E5DFD3]">{currentItem.sourceSlice}</span>
              </div>

              {/* Text Snippet */}
              <div className="p-3.5 bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg">
                <div className="text-[11px] font-semibold text-[#4D4D4F] uppercase tracking-wider mb-1">
                  Clinical Narrative Snippet
                </div>
                <div className="text-sm font-mono text-[#29251D] leading-relaxed bg-white p-3 rounded border border-[#E5DFD3]">
                  {currentItem.textSnippet}
                </div>
              </div>

              {/* Disagreement Breakdown: Side by Side */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                
                {/* Annotator A Card */}
                <div className="p-3.5 bg-white border border-[#E5DFD3] rounded-lg flex flex-col justify-between shadow-xs">
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold text-[#29251D]">
                        Annotator A: {currentItem.annotatorA.name}
                      </span>
                      <span className="text-[11px] font-mono text-[#4D4D4F] flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {currentItem.annotatorA.timeSpentSec}s
                      </span>
                    </div>

                    <div className="mb-2 p-2 bg-[#F6F2EA] border border-[#E5DFD3] rounded">
                      <div className="text-xs font-mono font-bold text-[#E31837]">
                        "{currentItem.annotatorA.spanText}"
                      </div>
                      <div className="text-[11px] text-[#4D4D4F] font-mono mt-0.5">
                        Tag: [{currentItem.annotatorA.label}]
                      </div>
                    </div>

                    <div className="text-[11px] text-[#4D4D4F]">
                      Offsets: [{currentItem.annotatorA.startIndex}..{currentItem.annotatorA.endIndex}] ·
                      Confidence: {(currentItem.annotatorA.confidence * 100).toFixed(0)}%
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleResolve('A')}
                    className="mt-3 w-full py-1.5 px-3 bg-[#E31837] hover:bg-[#5F0229] text-white font-semibold text-xs rounded transition-colors"
                  >
                    Accept Annotator A
                  </button>
                </div>

                {/* Annotator B Card */}
                <div className="p-3.5 bg-white border border-[#E5DFD3] rounded-lg flex flex-col justify-between shadow-xs">
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold text-[#29251D]">
                        Annotator B: {currentItem.annotatorB.name}
                      </span>
                      <span className="text-[11px] font-mono text-[#4D4D4F] flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {currentItem.annotatorB.timeSpentSec}s
                      </span>
                    </div>

                    <div className="mb-2 p-2 bg-[#F6F2EA] border border-[#E5DFD3] rounded">
                      <div className="text-xs font-mono font-bold text-[#247153]">
                        "{currentItem.annotatorB.spanText}"
                      </div>
                      <div className="text-[11px] text-[#4D4D4F] font-mono mt-0.5">
                        Tag: [{currentItem.annotatorB.label}]
                      </div>
                    </div>

                    <div className="text-[11px] text-[#4D4D4F]">
                      Offsets: [{currentItem.annotatorB.startIndex}..{currentItem.annotatorB.endIndex}] ·
                      Confidence: {(currentItem.annotatorB.confidence * 100).toFixed(0)}%
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleResolve('B')}
                    className="mt-3 w-full py-1.5 px-3 bg-[#247153] hover:bg-[#247153]/90 text-white font-semibold text-xs rounded transition-colors"
                  >
                    Accept Annotator B
                  </button>
                </div>

              </div>

              {/* Model Baseline Reference */}
              <div className="p-3 bg-[#F6F2EA] border border-[#E5DFD3] rounded-lg flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs text-[#29251D]">
                  <Sparkles className="w-3.5 h-3.5 text-[#185F8D]" />
                  <span>
                    Model Baseline: <span className="font-mono text-[#185F8D] font-semibold">"{currentItem.modelPrediction.spanText}"</span> [{currentItem.modelPrediction.label}]
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => handleResolve('Model')}
                  className="px-2.5 py-1 text-[11px] bg-white hover:bg-[#E5DFD3]/60 text-[#29251D] border border-[#E5DFD3] rounded transition-colors font-medium"
                >
                  Accept Model
                </button>
              </div>
            </>
          ) : (
            <div className="text-center py-8 text-[#4D4D4F]">
              All disputed items resolved for this batch!
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-[#E5DFD3] bg-[#F6F2EA] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={currentIndex === 0}
              onClick={() => setCurrentIndex((prev) => Math.max(0, prev - 1))}
              className="px-3 py-1.5 text-xs bg-white disabled:opacity-40 text-[#29251D] border border-[#E5DFD3] rounded flex items-center gap-1 hover:bg-[#F6F2EA] transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Previous</span>
            </button>
            <button
              type="button"
              disabled={currentIndex >= disputedItems.length - 1}
              onClick={() => setCurrentIndex((prev) => Math.min(disputedItems.length - 1, prev + 1))}
              className="px-3 py-1.5 text-xs bg-white disabled:opacity-40 text-[#29251D] border border-[#E5DFD3] rounded flex items-center gap-1 hover:bg-[#F6F2EA] transition-colors"
            >
              <span>Next</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-xs bg-[#29251D] hover:bg-[#4A453D] text-white rounded transition-colors"
          >
            Close Arbiter
          </button>
        </div>

      </div>
    </div>
  );
};
