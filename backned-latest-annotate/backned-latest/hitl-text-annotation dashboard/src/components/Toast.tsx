import React, { useEffect } from 'react';
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';

export interface ToastMessage {
  id: string;
  type: 'success' | 'warning' | 'info';
  title: string;
  message?: string;
}

interface ToastProps {
  toast: ToastMessage | null;
  onDismiss: () => void;
}

export const Toast: React.FC<ToastProps> = ({ toast, onDismiss }) => {
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => {
      onDismiss();
    }, 4500);
    return () => clearTimeout(timer);
  }, [toast, onDismiss]);

  if (!toast) return null;

  const icons = {
    success: CheckCircle2,
    warning: AlertCircle,
    info: Info
  };

  const colors = {
    success: 'border-[#247153] bg-white text-[#247153]',
    warning: 'border-[#8A5200] bg-white text-[#8A5200]',
    info: 'border-[#185F8D] bg-white text-[#185F8D]'
  };

  const Icon = icons[toast.type];

  return (
    <div className="fixed bottom-5 right-5 z-50 max-w-md shadow-lg">
      <div
        className={`p-4 rounded-lg border-2 flex items-start gap-3 ${colors[toast.type]}`}
      >
        <Icon className="w-5 h-5 shrink-0 mt-0.5" />
        <div className="flex-1">
          <div className="text-xs font-bold text-[#29251D]">{toast.title}</div>
          {toast.message && (
            <div className="text-xs text-[#4D4D4F] mt-0.5 leading-relaxed">
              {toast.message}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="text-[#4D4D4F] hover:text-[#29251D] transition-colors p-0.5"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};
