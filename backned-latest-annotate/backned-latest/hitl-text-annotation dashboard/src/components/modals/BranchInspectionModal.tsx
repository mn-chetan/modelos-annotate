import React from 'react';
import { X, GitFork, CheckCircle2, User, Users2, ShieldCheck } from 'lucide-react';

interface BranchInspectionModalProps {
  branch: 'auto' | 'single' | 'dual' | null;
  onClose: () => void;
  threshold: number;
}

export const BranchInspectionModal: React.FC<BranchInspectionModalProps> = ({
  branch,
  onClose,
  threshold
}) => {
  if (!branch) return null;

  const branchData = {
    auto: {
      title: 'Branch A: Auto-Approved Stream (Score ≥ ' + threshold.toFixed(2) + ')',
      icon: CheckCircle2,
      color: 'text-emerald-400',
      bgColor: 'bg-emerald-500/20',
      description: 'Documents with high token probability and low entropy bypass human review. Verified against clinical safety policy.',
      samples: [
        {
          id: 'DOC-99102',
          text: 'Patient was prescribed oral atorvastatin 40mg daily for hyperlipidemia.',
          confidence: 0.97,
          entities: ['atorvastatin [MEDICINE]', '40mg [DOSAGE]', 'hyperlipidemia [DIAGNOSIS]']
        },
        {
          id: 'DOC-99144',
          text: 'Echocardiogram demonstrated normal left ventricular systolic function with ejection fraction 60-65%.',
          confidence: 0.94,
          entities: ['normal left ventricular systolic function [DIAGNOSIS]']
        }
      ]
    },
    single: {
      title: 'Branch B: Single Human Review Queue (0.65 – ' + threshold.toFixed(2) + ')',
      icon: User,
      color: 'text-amber-400',
      bgColor: 'bg-amber-500/20',
      description: 'Sent to a single certified annotator to verify token boundaries or resolve minor class ambiguities.',
      samples: [
        {
          id: 'DOC-88310',
          text: 'Surgical consult evaluated questionable acute appendicitis vs mesenteric adenitis in right lower quadrant.',
          confidence: 0.78,
          entities: ['acute appendicitis [DIAGNOSIS]', 'mesenteric adenitis [DIAGNOSIS]', 'right lower quadrant [ANATOMY]']
        },
        {
          id: 'DOC-88392',
          text: 'Administered 2 units of packed red blood cells for acute blood loss anemia following revision arthroplasty.',
          confidence: 0.81,
          entities: ['packed red blood cells [PROCEDURE]', 'acute blood loss anemia [DIAGNOSIS]']
        }
      ]
    },
    dual: {
      title: 'Branch C: Dual Blind Consensus Queue (< 0.65)',
      icon: Users2,
      color: 'text-rose-400',
      bgColor: 'bg-rose-500/20',
      description: 'Low-confidence or out-of-distribution clinical notes require two independent blind annotators.',
      samples: [
        {
          id: 'DOC-77201',
          text: 'Possible Stevens-Johnson syndrome secondary to recent initiation of allopurinol for chronic tophaceous gout.',
          confidence: 0.58,
          entities: ['Stevens-Johnson syndrome [DIAGNOSIS]', 'allopurinol [MEDICINE]', 'chronic tophaceous gout [DIAGNOSIS]']
        },
        {
          id: 'DOC-77249',
          text: 'Extracorporeal membrane oxygenation (ECMO) cannulation performed emergently for refractory hypoxemic respiratory failure.',
          confidence: 0.61,
          entities: ['ECMO [PROCEDURE]', 'refractory hypoxemic respiratory failure [DIAGNOSIS]']
        }
      ]
    }
  }[branch];

  const Icon = branchData.icon;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-2xl w-full shadow-2xl flex flex-col overflow-hidden">
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-950/50">
          <div className="flex items-center gap-2.5">
            <div className={`w-8 h-8 rounded-lg ${branchData.bgColor} ${branchData.color} flex items-center justify-center`}>
              <Icon className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white">
                {branchData.title}
              </h3>
              <p className="text-xs text-slate-400">
                Live stream telemetry inspection
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4 text-xs">
          <p className="text-slate-300 leading-relaxed">
            {branchData.description}
          </p>

          <div className="space-y-3">
            <div className="font-semibold text-slate-200 text-xs">
              Live Document Partition Samples:
            </div>
            {branchData.samples.map((s) => (
              <div key={s.id} className="p-3 bg-slate-950 border border-slate-800 rounded-lg space-y-2">
                <div className="flex justify-between items-center text-[11px]">
                  <span className="font-mono text-indigo-400">{s.id}</span>
                  <span className="font-mono text-slate-300">
                    Model Conf: {(s.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="font-mono text-slate-200 bg-slate-900/60 p-2 rounded border border-slate-800/80">
                  "{s.text}"
                </div>
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {s.entities.map((e, idx) => (
                    <span
                      key={idx}
                      className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700"
                    >
                      {e}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-slate-800 bg-slate-950/50 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-white rounded transition-colors"
          >
            Dismiss
          </button>
        </div>

      </div>
    </div>
  );
};
