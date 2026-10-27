import React from 'react';
import { IntakeFormData } from '../types';
import { X, CheckCircle, HelpCircle, FileText, Send, Sparkles, AlertCircle } from 'lucide-react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}

export const BaseModal: React.FC<ModalProps> = ({ isOpen, onClose, title, children }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs">
      <div className="relative w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
          <h3 className="text-lg font-bold text-slate-900">{title}</h3>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="mt-4">{children}</div>
      </div>
    </div>
  );
};

interface DocumentationModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const DocumentationModal: React.FC<DocumentationModalProps> = ({ isOpen, onClose }) => {
  return (
    <BaseModal isOpen={isOpen} onClose={onClose} title="ModelOS Annotate Documentation">
      <div className="space-y-4 text-sm text-slate-600">
        <p>
          Welcome to the <strong>ModelOS Annotate Intake Pipeline</strong>. This documentation guides you through setting up labeling campaigns for high-accuracy machine learning datasets.
        </p>

        <div className="rounded-xl border border-[#0A0838]/15 bg-[#0A0838]/5 p-4 space-y-2 text-xs">
          <p className="font-semibold text-[#0A0838]">Supported Media & Formats:</p>
          <ul className="list-disc list-inside space-y-1 text-slate-700">
            <li><strong>Video:</strong> MP4, MOV, AVI, WebM (H.264 / ProRes) up to 10GB per sequence.</li>
            <li><strong>Image:</strong> JPG, PNG, TIFF, DICOM (16-bit) with EXIF retention.</li>
            <li><strong>Annotations:</strong> Bounding boxes, Polygons, Keypoints, 3D Cuboids, Segmentation masks.</li>
            <li><strong>Export Specs:</strong> COCO JSON, Pascal VOC, YOLO, GeoJSON, and TFRecord.</li>
          </ul>
        </div>

        <p className="text-xs text-slate-500">
          For automated ingestion via CLI or Python SDK, refer to our REST API endpoint at <code>https://api.modelosannotate.ai/v1/intakes</code>.
        </p>

        <div className="pt-2 flex justify-end">
          <button
            onClick={onClose}
            className="rounded-lg bg-[#E31837] px-4 py-2 text-xs font-semibold text-white hover:bg-[#C1122C] transition shadow-xs cursor-pointer"
          >
            Got it, thanks!
          </button>
        </div>
      </div>
    </BaseModal>
  );
};

interface SupportModalProps {
  isOpen: boolean;
  onClose: () => void;
  userEmail: string;
}

export const SupportModal: React.FC<SupportModalProps> = ({ isOpen, onClose, userEmail }) => {
  const [submitted, setSubmitted] = React.useState(false);
  const [message, setMessage] = React.useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    setTimeout(() => {
      setSubmitted(false);
      setMessage('');
      onClose();
    }, 1800);
  };

  return (
    <BaseModal isOpen={isOpen} onClose={onClose} title="Contact ModelOS Annotate Support">
      {submitted ? (
        <div className="py-8 text-center space-y-3">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-[#247153]/15 text-[#247153]">
            <CheckCircle className="h-6 w-6" />
          </div>
          <h4 className="text-base font-semibold text-slate-900">Message Received</h4>
          <p className="text-xs text-slate-500">
            Our ML Operations team will respond to <strong>{userEmail}</strong> within 1 hour.
          </p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4 text-xs sm:text-sm">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Your Email</label>
            <input
              type="email"
              disabled
              value={userEmail}
              className="w-full rounded-lg border border-[#E2DDD5] bg-[#FBF9F5] px-3 py-2 text-slate-600"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">How can we assist you?</label>
            <textarea
              required
              rows={3}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Describe your dataset sizing, labeling guideline requirements, or custom schema needs..."
              className="w-full rounded-lg border border-[#E2DDD5] px-3 py-2 text-slate-800 focus:border-[#E31837] focus:outline-none focus:ring-2 focus:ring-[#E31837]/15"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-[#D0C9BE] px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-[#FBF9F5] cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex items-center gap-1.5 rounded-lg bg-[#E31837] px-4 py-2 text-xs font-semibold text-white hover:bg-[#C1122C] shadow-xs cursor-pointer"
            >
              <Send className="h-3.5 w-3.5" />
              <span>Send Message</span>
            </button>
          </div>
        </form>
      )}
    </BaseModal>
  );
};

interface SubmissionSuccessModalProps {
  isOpen: boolean;
  onClose: () => void;
  formData: IntakeFormData;
}

export const SubmissionSuccessModal: React.FC<SubmissionSuccessModalProps> = ({
  isOpen,
  onClose,
  formData,
}) => {
  return (
    <BaseModal isOpen={isOpen} onClose={onClose} title="Intake Project Created!">
      <div className="space-y-4">
        <div className="flex items-center gap-3 rounded-xl bg-[#247153]/10 border border-[#247153]/25 p-4">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#247153]/20 text-[#247153]">
            <CheckCircle className="h-6 w-6" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-[#247153]">Project Successfully Initialized</h4>
            <p className="text-xs text-slate-700">
              {formData.projectName} is now queued for annotation ingestion.
            </p>
          </div>
        </div>

        <div className="rounded-xl border border-[#E2DDD5] bg-[#FBF9F5] p-4 space-y-2 text-xs">
          <div className="flex justify-between">
            <span className="text-slate-500">Project:</span>
            <span className="font-semibold text-slate-800">{formData.projectName}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Assigned Team:</span>
            <span className="font-semibold text-slate-800">{formData.assignedTeam}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Target Files:</span>
            <span className="font-semibold text-slate-800">{formData.numberOfFiles} {formData.mediaFormat} files</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Format:</span>
            <span className="font-semibold text-slate-800">{formData.expectedOutputFormat}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Due Date:</span>
            <span className="font-semibold text-slate-800">{formData.dueDate}</span>
          </div>
        </div>

        <div className="pt-2 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg bg-[#E31837] px-5 py-2.5 text-xs font-semibold text-white hover:bg-[#C1122C] shadow-xs cursor-pointer"
          >
            View in Projects Dashboard
          </button>
        </div>
      </div>
    </BaseModal>
  );
};
