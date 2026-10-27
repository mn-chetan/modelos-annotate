import React from 'react';
import { StepId, StepItem } from '../types';
import { Check } from 'lucide-react';

interface StepperProps {
  currentStep: StepId;
  onSelectStep: (step: StepId) => void;
}

export const Stepper: React.FC<StepperProps> = ({ currentStep, onSelectStep }) => {
  const steps: StepItem[] = [
    { id: 1, label: 'Project Details' },
    { id: 2, label: 'Annotation Settings' },
    { id: 3, label: 'Tool Technique' },
    { id: 4, label: 'Data & Media' },
  ];

  return (
    <div id="intake-stepper" className="w-full py-4 overflow-x-auto">
      <div className="flex min-w-[580px] items-center justify-between">
        {steps.map((step, idx) => {
          const isActive = currentStep === step.id;
          const isCompleted = currentStep > step.id;

          return (
            <React.Fragment key={step.id}>
              {/* Step indicator */}
              <button
                id={`stepper-step-${step.id}`}
                onClick={() => onSelectStep(step.id)}
                className="group flex items-center gap-2.5 cursor-pointer text-left focus:outline-none"
              >
                <div
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-all ${
                    isActive
                      ? 'bg-[#E31837] text-white shadow-sm ring-4 ring-[#E31837]/15'
                      : isCompleted
                      ? 'bg-[#E31837]/10 text-[#E31837] font-bold'
                      : 'bg-slate-100 text-slate-500 group-hover:bg-slate-200'
                  }`}
                >
                  {isCompleted ? <Check className="h-3.5 w-3.5 stroke-[2.5]" /> : step.id}
                </div>

                <span
                  className={`text-xs sm:text-sm font-medium transition-colors ${
                    isActive
                      ? 'font-semibold text-[#E31837]'
                      : isCompleted
                      ? 'text-slate-700'
                      : 'text-slate-500 group-hover:text-slate-700'
                  }`}
                >
                  {step.label}
                </span>
              </button>

              {/* Connecting line */}
              {idx < steps.length - 1 && (
                <div
                  className={`mx-2 sm:mx-4 h-0.5 flex-1 transition-colors ${
                    currentStep > idx + 1 ? 'bg-[#E31837]' : 'bg-[#E2DDD5]'
                  }`}
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};
