/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useState } from 'react';
import {
  ProjectOption,
  ModelRunOption,
  DatasetSliceOption,
  DateFilter,
  AnnotationType,
  AnnotatorRecord,
  DisputedItem
} from './types';
import {
  PROJECTS,
  MODEL_RUNS,
  DATASET_SLICES,
  DISPUTED_ITEMS
} from './data/mockData';

import { TechMTopBar } from './components/TechMTopBar';
import { TechMScorecard } from './components/TechMScorecard';
import { TechMConfidenceThresholdBar } from './components/TechMConfidenceThresholdBar';
import { TechMAnnotationComparisonChart } from './components/TechMAnnotationComparisonChart';
import { TechMSectionDetail } from './components/TechMSectionDetail';
import { TechMWorkforceAndTriage } from './components/TechMWorkforceAndTriage';

import { DisputeResolutionModal } from './components/modals/DisputeResolutionModal';
import { LeadAuditModal } from './components/modals/LeadAuditModal';
import { ActiveLearningExportModal } from './components/modals/ActiveLearningExportModal';
import { AnnotatorDetailModal } from './components/modals/AnnotatorDetailModal';
import { CalibrationGuideModal } from './components/modals/CalibrationGuideModal';
import { Toast, ToastMessage } from './components/Toast';

export interface LiveScorecardMetrics {
  totalDocs: number;
  autoRate: number;
  autoApprovedDocs: number;
  threshold: number;
  humanReviewRate: number;
  humanReviewDocs: number;
  humanEditRate: number;
  costSavedDollars: number;
  timeSavedHrs: number;
  workloadDeltaPct: number;
  annotationBreakdown: import('./components/TechMAnnotationComparisonChart').AnnotationComparisonRow[];
  areaIdentification: import('./components/TechMSectionDetail').AreaIdentificationRow[];
  annotators: AnnotatorRecord[];
  triage: { disputed_count: number; low_latency_count: number; active_learning_count: number };
}

export interface StandaloneDashboardProps {
  liveMetrics?: LiveScorecardMetrics;
  projects?: ProjectOption[];
  selectedProject?: ProjectOption;
  onSelectProject?: (p: ProjectOption) => void;
}

export default function App({
  liveMetrics,
  projects: propProjects,
  selectedProject: propSelectedProject,
  onSelectProject: propOnSelectProject,
}: StandaloneDashboardProps) {
  const availableProjects = propProjects && propProjects.length > 0 ? propProjects : PROJECTS;
  // Navigation & Project Selectors State
  const [internalSelectedProject, setInternalSelectedProject] = useState<ProjectOption>(availableProjects[0]);

  useEffect(() => {
    if (propSelectedProject) {
      setInternalSelectedProject(propSelectedProject);
    } else if (availableProjects.length > 0 && !availableProjects.some((p) => p.id === internalSelectedProject.id)) {
      setInternalSelectedProject(availableProjects[0]);
    }
  }, [propSelectedProject, availableProjects]);

  const activeProject = propSelectedProject || internalSelectedProject;

  // Threshold is initialized from the backend project configuration.
  const [threshold, setThreshold] = useState<number>(0);
  useEffect(() => {
    if (liveMetrics) setThreshold(liveMetrics.threshold);
    if (liveMetrics?.annotators) setAnnotators(liveMetrics.annotators);
    if (liveMetrics?.triage) {
      setDisputedCount(liveMetrics.triage.disputed_count);
      setLowLatencyCount(liveMetrics.triage.low_latency_count);
      setActiveLearningCount(liveMetrics.triage.active_learning_count);
    }
  }, [liveMetrics]);

  // Active Section State: 'text_extraction' | 'ner' | 'sentiment' | 'relation' | 'classification'
  const [activeSection, setActiveSection] = useState<AnnotationType>('text_extraction');

  // Interactive Workforce & Data Lists State
  const [annotators, setAnnotators] = useState<AnnotatorRecord[]>([]);
  const [disputedItems, setDisputedItems] = useState<DisputedItem[]>(DISPUTED_ITEMS);
  const [disputedCount, setDisputedCount] = useState<number>(0);
  const [lowLatencyCount, setLowLatencyCount] = useState<number>(0);
  const [activeLearningCount, setActiveLearningCount] = useState<number>(0);

  // Modals State
  const [disputeModalOpen, setDisputeModalOpen] = useState(false);
  const [leadAuditModalOpen, setLeadAuditModalOpen] = useState(false);
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [selectedAnnotator, setSelectedAnnotator] = useState<AnnotatorRecord | null>(null);
  const [calibrationGuideOpen, setCalibrationGuideOpen] = useState(false);

  // Toast State
  const [toast, setToast] = useState<ToastMessage | null>(null);

  // Scorecard metrics are authoritative backend values. Do not render the old
  // demo calculations while the project request is still in flight.
  const metrics = liveMetrics;
  const displayMetrics = metrics || {
    totalDocs: 0,
    autoRate: 0,
    autoApprovedDocs: 0,
    threshold: 0,
    humanReviewRate: 0,
    humanReviewDocs: 0,
    humanEditRate: 0,
    costSavedDollars: 0,
    timeSavedHrs: 0,
    workloadDeltaPct: 0,
    areaIdentification: [],
    annotators: [],
    triage: { disputed_count: 0, low_latency_count: 0, active_learning_count: 0 },
  };

  // Handler for dispute arbitration
  const handleResolveDispute = (itemId: string, chosenResolution: string) => {
    setDisputedItems((prev) =>
      prev.map((item) =>
        item.id === itemId
          ? { ...item, status: 'resolved', resolution: chosenResolution }
          : item
      )
    );
    setDisputedCount((prev) => Math.max(0, prev - 1));
    setToast({
      id: Date.now().toString(),
      type: 'success',
      title: 'Dispute Arbitrated Successfully',
      message: chosenResolution
    });
  };

  // Handler for Lead Audit dispatch
  const handleDispatchAudit = ({
    sampleSize,
    leadAuditor,
    targetAnnotator
  }: {
    sampleSize: number;
    leadAuditor: string;
    targetAnnotator: string;
  }) => {
    setLowLatencyCount((prev) => Math.max(0, prev - sampleSize));
    setToast({
      id: Date.now().toString(),
      type: 'warning',
      title: 'Lead Audit Batch Dispatched',
      message: `Assigned ${sampleSize} flagged documents from ${targetAnnotator} to ${leadAuditor} for expedited QA re-check.`
    });
  };

  // Handler for Active Learning export
  const handleExportSuccess = (format: string, count: number) => {
    setToast({
      id: Date.now().toString(),
      type: 'info',
      title: 'Active Learning Export Dispatched',
      message: `Successfully serialized ${count} high-uncertainty edge cases in ${format} format to s3://mednlp-models-store/.`
    });
  };

  return (
    <div className="min-h-screen bg-[#F6F2EA] text-[#29251D] flex flex-col font-sans">
      
      {/* 1. TOP HEADER: Tech Mahindra Brand + Single Review Tab "Lead Review" + Context Selectors */}
      <TechMTopBar
        projects={availableProjects}
        selectedProject={activeProject}
        onSelectProject={(p) => {
          setInternalSelectedProject(p);
          propOnSelectProject?.(p);
          setToast({
            id: Date.now().toString(),
            type: 'info',
            title: `Active Project: ${p.name}`,
            message: `Loaded ${p.domain} configuration.`
          });
        }}
        onOpenExportModal={() => setExportModalOpen(true)}
        onOpenCalibrationGuide={() => setCalibrationGuideOpen(true)}
      />

      {/* Main Content Workspace */}
      <main className="flex-1 max-w-[1720px] w-full mx-auto px-4 sm:px-6 lg:px-8 py-5">
        
        {/* 2. TOP SCORECARD: Total Ingested Docs, Auto-Approved Rate, Human Review Rate, Human Edit Rate, Cost & Time Saved */}
        {metrics ? (
          <TechMScorecard
            totalDocs={metrics.totalDocs}
            autoApprovedRate={metrics.autoRate}
            autoApprovedDocs={metrics.autoApprovedDocs}
            threshold={metrics.threshold}
            humanReviewRate={metrics.humanReviewRate}
            humanReviewDocs={metrics.humanReviewDocs}
            humanEditRate={metrics.humanEditRate}
            costSavedDollars={metrics.costSavedDollars}
            timeSavedHrs={metrics.timeSavedHrs}
            workloadDeltaPct={metrics.workloadDeltaPct}
          />
        ) : (
          <div className="mb-5 rounded-lg border border-[#E5DFD3] bg-white p-4 text-sm text-[#4D4D4F]">
            Loading project metrics...
          </div>
        )}

        {/* 3. CONFIDENCE THRESHOLD BAR */}
        <TechMConfidenceThresholdBar
          threshold={threshold}
          onChangeThreshold={(val) => setThreshold(val)}
          autoRate={displayMetrics.autoRate}
          humanReviewRate={displayMetrics.humanReviewRate}
          workloadDeltaPct={displayMetrics.workloadDeltaPct}
        />

        {/* 4. COMPARISON BAR GRAPH FOR ALL 5 ANNOTATION TYPES (AI Processed vs Moved to HITL) */}
          <TechMAnnotationComparisonChart
          data={metrics?.annotationBreakdown || []}
          activeAnnotationType={activeSection}
          onSelectAnnotationType={(t) => setActiveSection(t)}
        />

        {/* 5. ACTIVE ANNOTATION SECTION DETAIL (Sections 2 to 6) WITH DEDICATED SCORECARD & AREA IDENTIFICATION TRENDS */}
          <TechMSectionDetail
          data={metrics?.annotationBreakdown || []}
          areas={metrics?.areaIdentification || []}
          activeSection={activeSection}
          onChangeSection={(t) => setActiveSection(t)}
        />

        {/* 6. WORKFORCE & ACTIONABLE AUDIT QUEUE: Annotator Performance & Safeguard Audit + Actionable HITL Triage Drawer */}
        <TechMWorkforceAndTriage
          annotators={annotators}
          disputedCount={disputedCount}
          lowLatencyCount={lowLatencyCount}
          activeLearningCount={activeLearningCount}
          onSelectAnnotator={(ann) => setSelectedAnnotator(ann)}
          onOpenDisputeResolution={() => setDisputeModalOpen(true)}
          onOpenLeadAudit={() => setLeadAuditModalOpen(true)}
          onOpenActiveLearningExport={() => setExportModalOpen(true)}
        />

      </main>

      {/* Tech Mahindra Enterprise Footer */}
      <footer className="border-t border-[#E5DFD3] bg-white py-4 text-xs text-[#4D4D4F] mt-8">
        <div className="max-w-[1720px] mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="font-bold text-[#29251D]">Tech Mahindra</span>
            <span>·</span>
            <span>Enterprise Human-in-the-Loop Text Annotation Workbench</span>
          </div>
          <div className="flex items-center gap-4 text-[#4D4D4F]">
            <span>WCAG 2.2 AA Compliant</span>
            <span>·</span>
            <span>Lead Review Workflow Active</span>
            <span>·</span>
            <span>Kafka Ingestion SLA: 99.98%</span>
          </div>
        </div>
      </footer>

      {/* Modals & Overlays */}
      <DisputeResolutionModal
        isOpen={disputeModalOpen}
        onClose={() => setDisputeModalOpen(false)}
        disputedItems={disputedItems}
        onResolveDispute={handleResolveDispute}
      />

      <LeadAuditModal
        isOpen={leadAuditModalOpen}
        onClose={() => setLeadAuditModalOpen(false)}
        onDispatchAudit={handleDispatchAudit}
      />

      <ActiveLearningExportModal
        isOpen={exportModalOpen}
        onClose={() => setExportModalOpen(false)}
        onExportSuccess={handleExportSuccess}
      />

      <AnnotatorDetailModal
        annotator={selectedAnnotator}
        onClose={() => setSelectedAnnotator(null)}
        onActionComplete={(msg) => {
          setToast({
            id: Date.now().toString(),
            type: 'success',
            title: 'Action Applied',
            message: msg
          });
        }}
      />

      <CalibrationGuideModal
        isOpen={calibrationGuideOpen}
        onClose={() => setCalibrationGuideOpen(false)}
      />

      {/* Toast Notification */}
      <Toast toast={toast} onDismiss={() => setToast(null)} />

    </div>
  );
}
