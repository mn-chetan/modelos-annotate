/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { IntakeForm } from './components/IntakeForm';
import { SummaryRail } from './components/SummaryRail';
import { ImageAnnotationWorkspace } from './components/ImageAnnotation/ImageAnnotationWorkspace';
import { HitlObjectDetectionWorkspace } from './components/ImageAnnotation/HitlObjectDetectionWorkspace';
import { TextAnnotationWorkspace } from './components/TextAnnotation/TextAnnotationWorkspace';
import { QualityAuditNERWorkspace } from './components/QualityCheck/QualityAuditNERWorkspace';
import { QualityAuditImageWorkspace } from './components/QualityCheck/QualityAuditImageWorkspace';
import { QualityAuditPIIMaskingWorkspace } from './components/QualityCheck/QualityAuditPIIMaskingWorkspace';
import { ProductionReportView } from './components/Dashboard/ProductionReportView';
import { HitlReportView } from './components/Dashboard/HitlReportView';
import { TextHITLDashboardView } from './components/Dashboard/TextHITLDashboardView';
import { QualityReportView } from './components/Dashboard/QualityReportView';
import { SystemAdministrationView } from './components/Administration/SystemAdministrationView';
import { ProjectsView } from './components/ProjectsView';
import {
  DocumentationModal,
  SupportModal,
  SubmissionSuccessModal,
} from './components/Modals';
import { IntakeFormData, isSupportedImageUploadFile, StepId, TargetObjectClass } from './types';
import { Check, CheckCircle2 } from 'lucide-react';

import { api, ProjectResponse } from './services/api';

const getSelectedTextTask = (navItem: string): string | undefined => {
  if (navItem === 'All Text Features') return 'ALL_TEXT_FEATURES';
  if (navItem === 'Text Classification' || navItem === 'HITL - Text Classification') return 'TEXT_CLASSIFICATION';
  if (navItem === 'Sentiment Annotation' || navItem === 'HITL - Sentiment Annotation') {
    return 'SENTIMENT_ANALYSIS';
  }
  if (navItem === 'Relation Extraction' || navItem === 'HITL - Relation Extraction') return 'RELATION_EXTRACTION';
  if (navItem === 'NER Annotation' || navItem === 'HITL - NER Annotation') {
    return 'ENTITY_EXTRACTION';
  }
  return undefined;
};

export default function App() {
  // Initial form values starting empty until the user fills them out or selects options
  const [formData, setFormData] = useState<IntakeFormData>({
    projectName: '',
    description: '',
    projectType: '',
    domainUseCase: '',
    dataType: '',
    cloudStorageUrl: '',
    mediaFormat: '',
    numberOfFiles: 0,
    annotationTypes: [],
    expectedOutputFormat: '',
    qualityLevel: '',
    assignedTeam: '',
    priority: '',
    dueDate: '',
    uploadedFiles: [],
    visionTechnique: '2D Bounding Box',
    visionTechniques: ['2D Bounding Box'],
    targetClasses: [],
    sentimentAnalysisLevel: 'document',
    classificationAnalysisLevel: 'document',
  });

  const [currentStep, setCurrentStep] = useState<StepId>(1);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [activeNavItem, setActiveNavItem] = useState('Production report');
  const [searchQuery, setSearchQuery] = useState('');

  // Authentication State
  const [currentUserEmail] = useState<string>('Annotator');

  const resetNewProjectForm = () => {
    setFormData({
      projectName: '',
      description: '',
      projectType: '',
      domainUseCase: '',
      dataType: '',
      cloudStorageUrl: '',
      mediaFormat: '',
      numberOfFiles: 0,
      annotationTypes: [],
      expectedOutputFormat: '',
      qualityLevel: '',
      assignedTeam: '',
      priority: '',
      dueDate: '',
      uploadedFiles: [],
      visionTechnique: '2D Bounding Box',
      visionTechniques: ['2D Bounding Box'],
      targetClasses: [],
      targetObjectsText: '',
      inputText: '',
    });
    setSelectedProjectId(undefined);
    window.history.replaceState({}, '', window.location.pathname);
  };

  // Modals & toast states
  const [isDocsOpen, setIsDocsOpen] = useState(false);
  const [isSupportOpen, setIsSupportOpen] = useState(false);
  const [isSuccessOpen, setIsSuccessOpen] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  const handleFormChange = (updated: Partial<IntakeFormData>) => {
    setFormData((prev) => ({ ...prev, ...updated }));
  };

  const getTargetClassesForSubmission = () => {
    const isNer = formData.annotationTypes.includes('NER Annotation');
    const isVision =
      formData.projectType === 'Image Annotation' || formData.projectType === 'Video Annotation';
    if (!isNer && !isVision) return [];
    return (formData.targetClasses || []).map((target) => {
      let cleanName = target.name.trim();
      cleanName = cleanName
        .replace(/^(?:please\s+)?(?:precisely|accurately|carefully)?\s*(?:detect|identify|find|annotate|label|extract|track|locate|segment|classify|recognize)\s+(?:all\s+)?(?:the\s+)?/i, '')
        .replace(/\s+(?:should\s+be|to\s+be|must\s+be|need\s+to\s+be|needs\s+to\s+be|will\s+be|are\s+to\s+be)?\s*(?:identified|detected|annotated|labeled|labelled|found|tracked|segmented|extracted|classified|recognized|located).*$/i, '')
        .replace(/\s+(?:should\s+be|to\s+be|must\s+be|need\s+to\s+be|needs\s+to\s+be)$/i, '')
        .replace(/\s+(?:identified|detected|annotated|labeled|labelled|found|tracked|segmented|extracted|classified|recognized|located)$/i, '')
        .replace(/\s+(?:in|from|within)\s+(?:the\s+)?(?:traffic\s+)?(?:images?|photos?|pictures?|video|frame|scene).*$/i, '')
        .trim();

      if (/^(pedestrian|pedestrians|people|person)$/i.test(cleanName)) {
        cleanName = 'person';
      } else if (/^(cars?)$/i.test(cleanName)) {
        cleanName = 'car';
      } else if (/^(buses?)$/i.test(cleanName)) {
        cleanName = 'bus';
      } else if (/^(trucks?)$/i.test(cleanName)) {
        cleanName = 'truck';
      }

      return {
        ...target,
        name: cleanName || target.name.trim(),
      };
    });
  };

  const getImageProjectInstruction = () =>
    formData.projectType === 'Image Annotation'
      ? formData.targetObjectsText?.trim() || ''
      : formData.description;

  const handleSaveDraft = async () => {
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    showToast(`Draft "${formData.projectName || 'New Project'}" saved at ${timeStr}`);
    if (formData.projectName) {
      try {
        await api.createProject({
          name: formData.projectName,
          description: getImageProjectInstruction(),
          project_type: formData.projectType,
          domain_use_case: formData.domainUseCase,
          data_type: formData.dataType,
          cloud_storage_url: formData.cloudStorageUrl,
          media_format: formData.mediaFormat,
          annotation_types: formData.annotationTypes,
          expected_output_format: formData.expectedOutputFormat,
          quality_level: formData.qualityLevel,
          assigned_team: formData.assignedTeam,
          priority: formData.priority,
          due_date: formData.dueDate,
          target_classes: getTargetClassesForSubmission(),
          sentiment_analysis_level: formData.sentimentAnalysisLevel || 'document',
          classification_analysis_level: formData.classificationAnalysisLevel || 'document',
        });
      } catch (e: any) {
        console.warn('Backend draft save notice:', e.message);
      }
    }
  };

  const [isAiAnnotating, setIsAiAnnotating] = useState<boolean>(false);
  const [aiCompletionProjectId, setAiCompletionProjectId] = useState<string | null>(null);
  const [textAnalysisContext, setTextAnalysisContext] = useState<{ projectId: string; assetId?: string } | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string | undefined>(undefined);

  const loadProjectIntoForm = (fullProj: ProjectResponse, assetCountFromApi?: number) => {
    const actualAssetCount = typeof assetCountFromApi === 'number' && assetCountFromApi > 0
      ? assetCountFromApi
      : (fullProj.asset_count ?? fullProj.item_count ?? 0);

    const isText = (
      (fullProj.project_type || '').toLowerCase().includes('text') ||
      (fullProj.media_format || '').toLowerCase() === 'text' ||
      ((fullProj as any).modality || '').toLowerCase() === 'text' ||
      ((fullProj as any).modality || '').toLowerCase() === 'document' ||
      (fullProj.task_type || '').toUpperCase().includes('TEXT') ||
      (fullProj.task_type || '').toUpperCase().includes('NER') ||
      (fullProj.task_type || '').toUpperCase().includes('SENTIMENT')
    );

    const targetClasses: TargetObjectClass[] = (fullProj.label_ontology || fullProj.labels || []).map((l: any, idx: number) =>
      typeof l === 'string'
        ? { id: `class-${idx}`, name: /^(pedestrian|pedestrians|people|person)$/i.test(l.trim()) ? 'person' : l, color: '#06B6D4', shortcutIndex: idx + 1 }
        : { id: l.id || `class-${idx}`, name: /^(pedestrian|pedestrians|people|person)$/i.test((l.name || '').trim()) ? 'person' : (l.name || ''), color: l.color || '#06B6D4', shortcutIndex: l.shortcutIndex || idx + 1 }
    );

    setFormData({
      projectName: fullProj.name || '',
      description: fullProj.description || '',
      projectType: (fullProj.project_type || (isText ? 'Text Annotation' : 'Image Annotation')) as any,
      domainUseCase: '',
      dataType: 'Files Upload',
      cloudStorageUrl: '',
      mediaFormat: (fullProj.media_format || (isText ? 'Text' : 'Image')) as any,
      numberOfFiles: actualAssetCount,
      annotationTypes: isText
        ? [String(fullProj.task_type || '').toUpperCase().includes('SENTIMENT')
          ? 'Sentiment Annotation'
          : String(fullProj.task_type || '').toUpperCase().includes('CLASSIFICATION')
          ? 'Text Classification'
          : 'NER Annotation']
        : ['Object Detection & Labeling'],
      expectedOutputFormat: ((fullProj as any).expected_output_format || 'COCO JSON') as any,
      qualityLevel: (fullProj.quality_level || 'Standard Quality (95%+)') as any,
      assignedTeam: (fullProj.assigned_team || 'Computer Vision Team A') as any,
      priority: (fullProj.priority || 'Medium') as any,
      dueDate: fullProj.due_date || '',
      uploadedFiles: [],
      visionTechnique: '',
      targetClasses: targetClasses,
      targetObjectsText: (fullProj.labels || []).map((l: any) => typeof l === 'string' ? l : l.name).join(', ') || fullProj.description || '',
      sentimentAnalysisLevel: fullProj.sentiment_analysis_level || 'document',
      classificationAnalysisLevel: fullProj.classification_analysis_level || 'document',
    });
  };

  const handleSelectProject = async (project: ProjectResponse) => {
    setSelectedProjectId(project.id);
    const newUrl = `${window.location.pathname}?projectId=${encodeURIComponent(project.id)}`;
    window.history.pushState({ projectId: project.id }, '', newUrl);

    showToast(`Loading project "${project.name}"...`);
    try {
      const fullProj = (await api.getProjectDetail(project.id).catch(() => project)) || project;
      const assets = await api.getProjectAssets(project.id).catch(() => []);

      const modality = String(fullProj.modality || '').toLowerCase();
      const isTextProject = modality === 'text' || modality === 'document';
      if (isTextProject) {
        loadProjectIntoForm(fullProj, assets.length);
        setActiveNavItem('Create Project');
        showToast(`Opened project "${fullProj.name}" configuration`);
        return;
      }

      loadProjectIntoForm(fullProj, assets.length);
      setActiveNavItem('Create Project');
      showToast(`Opened project "${fullProj.name}" configuration`);
    } catch (err: any) {
      showToast(`Failed to load project configuration: ${err.message || 'Unknown error'}`);
    }
  };

  useEffect(() => {
    const queryParams = new URLSearchParams(window.location.search);
    const pid = queryParams.get('projectId');
    if (pid) {
      setSelectedProjectId(pid);
      api.getProjectDetail(pid).then((fullProj) => {
        if (fullProj) {
          api.getProjectAssets(pid).then((assets) => {
            loadProjectIntoForm(fullProj, assets.length);
            setActiveNavItem('Create Project');
          });
        }
      });
    }
  }, []);

  const handleAiAnnotate = async () => {
    const isImageFilesUpload =
      formData.projectType === 'Image Annotation' && formData.dataType === 'Files Upload';
    const imageUploadEntries = formData.uploadedFiles || [];
    const isUploadFile = (value: unknown): value is File =>
      Boolean(value && typeof (value as File).name === 'string' && typeof (value as File).arrayBuffer === 'function');
    const imageFilesToUpload = imageUploadEntries
      .map((item) => item.file)
      .filter(isUploadFile);
    const hasUploadedFile = imageUploadEntries.some((item) => isUploadFile(item.file));

    // 1. Form Validation
    if (!formData.projectName || !formData.projectName.trim()) {
      showToast('Please enter a Project Name.');
      return;
    }
    if (!formData.projectType) {
      showToast('Please select a Project Type.');
      return;
    }
    if (formData.projectType === 'Text Annotation') {
      if (formData.dataType === 'Input Text Field' && !(formData.inputText || '').trim()) {
        showToast('Please enter text before starting AI Annotation.');
        return;
      }
      if (formData.dataType === 'Files Upload' && !hasUploadedFile) {
        showToast('Please upload a text file before starting AI Annotation.');
        return;
      }
    }

    setIsAiAnnotating(true);
    setAiCompletionProjectId(null);
    showToast(`Initializing AI annotation pipeline for "${formData.projectName}"...`);

    try {
      // 2. Obtain or Create Project ID
      let targetProjectId = selectedProjectId;
      // A project can be deleted while an old intake URL remains open. Do not
      // send uploads to that stale ID; fall back to creating the project from
      // the current intake form instead.
      if (targetProjectId) {
        const existingProject = await api.getProjectDetail(targetProjectId);
        if (!existingProject) {
          targetProjectId = '';
          setSelectedProjectId('');
          window.history.replaceState({}, '', window.location.pathname);
        }
      }
      if (!targetProjectId) {
        const proj = await api.createProject({
          name: formData.projectName,
          description: getImageProjectInstruction(),
          project_type: formData.projectType,
          domain_use_case: formData.domainUseCase,
          data_type: formData.dataType,
          cloud_storage_url: formData.cloudStorageUrl,
          media_format: formData.mediaFormat,
          annotation_types: formData.annotationTypes,
          expected_output_format: formData.expectedOutputFormat,
          quality_level: formData.qualityLevel,
          assigned_team: formData.assignedTeam,
          priority: formData.priority,
          due_date: formData.dueDate,
          target_classes: getTargetClassesForSubmission(),
          sentiment_analysis_level: formData.sentimentAnalysisLevel || 'document',
          classification_analysis_level: formData.classificationAnalysisLevel || 'document',
        });

        if (!proj || !proj.id) {
          throw new Error('Project creation failed to return a valid project ID.');
        }
        targetProjectId = proj.id;
        setSelectedProjectId(proj.id);
      }

      // 3. Upload / Register Datasets & Assets
      let uploadedImageAssets: Array<{ id: string; project_id: string }> = [];
      let uploadedAssets: Array<{ id: string; project_id: string }> = [];
      if (formData.uploadedFiles && formData.uploadedFiles.length > 0) {
        const realFiles = formData.uploadedFiles
          .map((f) => f.file)
          .filter(isUploadFile);
        if (realFiles.length > 0) {
          uploadedAssets = await api.uploadAssets(targetProjectId, realFiles);
          if (isImageFilesUpload) {
            uploadedImageAssets = Array.isArray(uploadedAssets) ? uploadedAssets : [];
          }
        }
      }

      // Image annotation must only dispatch after the upload endpoint has
      // returned and the persisted project assets are visible through the
      // canonical project-assets endpoint.
      if (formData.projectType === 'Image Annotation' && formData.dataType === 'Files Upload' && imageFilesToUpload.length > 0) {
        let persistedAssets = await api.getProjectAssets(targetProjectId, { throwOnError: true, forceRefresh: true });
        let persistedAssetIds = new Set(persistedAssets.map((asset) => asset.id));
        let missingUploadedAssets = uploadedImageAssets.filter((asset) => !persistedAssetIds.has(asset.id));
        for (let retry = 0; retry < 3 && missingUploadedAssets.length > 0; retry++) {
          await new Promise((resolve) => window.setTimeout(resolve, 800));
          persistedAssets = await api.getProjectAssets(targetProjectId, { throwOnError: true, forceRefresh: true });
          persistedAssetIds = new Set(persistedAssets.map((asset) => asset.id));
          missingUploadedAssets = uploadedImageAssets.filter((asset) => !persistedAssetIds.has(asset.id));
        }
        if (missingUploadedAssets.length > 0) {
          throw new Error(
            `Image upload completed but ${missingUploadedAssets.length} returned asset(s) were not found in the persisted project asset list.`
          );
        }
      }

      // Text analysis accepts either direct input or the first uploaded text file.
      const uploadedTextFile = formData.uploadedFiles?.find((item) => isUploadFile(item.file))?.file;
      const directText = formData.inputText?.trim() || '';
      const textForAnalysis = directText || (uploadedTextFile && !/\.(pdf|docx)$/i.test(uploadedTextFile.name) ? await uploadedTextFile.text() : '');
      const textAnalysisTypes = formData.annotationTypes.includes('All Text Features')
        // Use the backend's combined capability once; four graph requests
        // made the deployed text workflow unnecessarily slow.
        ? ['All Text Features']
        : [
            formData.annotationTypes.includes('Sentiment Annotation')
              ? 'Sentiment'
              : formData.annotationTypes.includes('Text Classification')
              ? 'Classification'
              : formData.annotationTypes.includes('Relation Extraction')
              ? 'Relation'
              : 'NER',
          ];
      if (formData.projectType === 'Text Annotation' && (textForAnalysis || uploadedTextFile)) {
        // Text input must enter the canonical project-assets store before any
        // analysis starts. The returned ID is the only ID used downstream.
        const textFilename = `${formData.projectName.trim().replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase() || 'text-input'}.txt`;
        const textFile = new File([textForAnalysis], textFilename, { type: 'text/plain' });
        const createdTextAssets = directText
          ? await api.uploadAssets(targetProjectId, [textFile])
          : uploadedAssets;
        let createdTextAsset = (createdTextAssets || []).find(
          (asset: { project_id?: string; id?: string }) =>
            Boolean(asset.id) && (!asset.project_id || asset.project_id === targetProjectId)
        );
        if (!createdTextAsset?.id) {
          const currentAssets = await api.getProjectAssets(targetProjectId, { throwOnError: false });
          if (currentAssets.length > 0) {
            createdTextAsset = currentAssets[0];
          } else {
            throw new Error('Text asset creation did not return a persisted asset ID.');
          }
        }

        const persistedTextAssets = await api.getProjectAssets(targetProjectId, { throwOnError: true });
        const textAssetsToAnalyze = directText
          ? persistedTextAssets.filter((asset) => asset.id === createdTextAsset.id)
          : persistedTextAssets;

        const analyzeResults: Array<{ project_id?: string; asset_id?: string }> = [];
        const failedAssets: string[] = [];
        // Analyze uploaded documents concurrently; the API calls are
        // independent and the backend bounds Gemini concurrency.
        await Promise.all(textAssetsToAnalyze.map(async (targetAsset) => {
          try {
            let res: { project_id?: string; asset_id?: string } | null = null;
            for (const textAnalysisType of textAnalysisTypes) {
              res = await api.analyzeText({
                projectId: targetProjectId,
                assetId: targetAsset.id,
                analysisType: textAnalysisType as any,
                assessmentName: `${formData.projectName} Analysis`,
                identificationName:
                  formData.annotationTypes.includes('NER Annotation') ||
                  formData.annotationTypes.includes('All Text Features')
                    ? formData.targetObjectsText
                    : undefined,
              });
            }
            if (res?.asset_id) analyzeResults.push(res);
          } catch (error) {
            try {
              let retryResult: { project_id?: string; asset_id?: string } | null = null;
              for (const textAnalysisType of textAnalysisTypes) {
                retryResult = await api.analyzeText({
                  projectId: targetProjectId,
                  assetId: targetAsset.id,
                  analysisType: textAnalysisType as any,
                  assessmentName: `${formData.projectName} Analysis (Retry)`,
                  identificationName:
                    formData.annotationTypes.includes('NER Annotation') ||
                    formData.annotationTypes.includes('All Text Features')
                      ? formData.targetObjectsText
                      : undefined,
                });
              }
              if (retryResult?.asset_id) analyzeResults.push(retryResult);
            } catch (retryError) {
              failedAssets.push(targetAsset.filename || targetAsset.id);
              console.error('Text annotation failed after retry:', targetAsset.id, retryError);
            }
          }
        }));
        if (failedAssets.length > 0) {
          showToast(`AI annotation completed for ${analyzeResults.length}/${textAssetsToAnalyze.length} documents. ${failedAssets.length} failed; retry those documents.`);
        }
        if (analyzeResults.length === 0) {
          throw new Error(`Text AI annotation failed for all uploaded documents: ${failedAssets.join(', ') || 'backend returned no result'}.`);
        }
        const lastResult = analyzeResults[analyzeResults.length - 1] || analyzeResults[0];
        setTextAnalysisContext({
          projectId: lastResult?.project_id || targetProjectId,
          assetId: lastResult?.asset_id || createdTextAsset.id,
        });
      } else if (formData.projectType === 'Text Annotation') {
        // Existing projects opened from Projects have persisted assets but no
        // browser File handles. Reuse those canonical assets instead of
        // waiting for a new upload or silently leaving the button running.
        const persistedTextAssets = (await api.getProjectAssets(targetProjectId, { throwOnError: true }))
          .filter((asset) => /text|pdf|word|csv|json|plain/i.test(`${asset.content_type || ''} ${asset.filename || ''}`));
        if (persistedTextAssets.length === 0) {
          throw new Error('No persisted text documents found in this project.');
        }
        const analyzeResults: Array<{ project_id?: string; asset_id?: string }> = [];
        const failedAssets: string[] = [];
        await Promise.all(persistedTextAssets.map(async (persistedTextAsset) => {
          try {
            let res: { project_id?: string; asset_id?: string } | null = null;
            for (const textAnalysisType of textAnalysisTypes) {
              res = await api.analyzeText({
                projectId: targetProjectId,
                assetId: persistedTextAsset.id,
                analysisType: textAnalysisType as any,
                assessmentName: `${formData.projectName} Analysis`,
                identificationName:
                  formData.annotationTypes.includes('NER Annotation') ||
                  formData.annotationTypes.includes('All Text Features')
                    ? formData.targetObjectsText
                    : undefined,
              });
            }
            if (res?.asset_id) analyzeResults.push(res);
          } catch (error) {
            try {
              let retryResult: { project_id?: string; asset_id?: string } | null = null;
              for (const textAnalysisType of textAnalysisTypes) {
                retryResult = await api.analyzeText({
                  projectId: targetProjectId,
                  assetId: persistedTextAsset.id,
                  analysisType: textAnalysisType as any,
                  assessmentName: `${formData.projectName} Analysis (Retry)`,
                  identificationName:
                    formData.annotationTypes.includes('NER Annotation') ||
                    formData.annotationTypes.includes('All Text Features')
                      ? formData.targetObjectsText
                      : undefined,
                });
              }
              if (retryResult?.asset_id) analyzeResults.push(retryResult);
            } catch (retryError) {
              failedAssets.push(persistedTextAsset.filename || persistedTextAsset.id);
              console.error('Text annotation failed after retry:', persistedTextAsset.id, retryError);
            }
          }
        }));
        if (failedAssets.length > 0) {
          showToast(`AI annotation completed for ${analyzeResults.length}/${persistedTextAssets.length} documents. ${failedAssets.length} failed; retry those documents.`);
        }
        if (analyzeResults.length === 0) {
          throw new Error(`Text AI annotation failed for all persisted documents: ${failedAssets.join(', ') || 'backend returned no result'}.`);
        }
        const lastResult = analyzeResults[analyzeResults.length - 1];
        if (lastResult?.asset_id) {
          setTextAnalysisContext({
            projectId: lastResult.project_id || targetProjectId,
            assetId: lastResult.asset_id,
          });
        }
      }

      // Text projects are analyzed by analyzeText and must not enter the
      // project-wide image batch endpoint.
      let imageBatchCompleted = false;
      if (formData.projectType !== 'Text Annotation') {
        const aiResponse = await api.triggerAiAnnotation(targetProjectId);
        const batchId = aiResponse?.batch_id;
        if (!batchId || ['succeeded', 'partial_success', 'completed'].includes(String(aiResponse?.status || '').toLowerCase())) {
          imageBatchCompleted = true;
        } else {
          for (let attempt = 0; attempt < 90; attempt += 1) {
            await new Promise((resolve) => window.setTimeout(resolve, 2000));
            const batches = await api.getProjectBatches(targetProjectId);
            const batch = batches.find((item) => item.id === batchId);
            const status = String(batch?.status || '').toLowerCase();
            if (['succeeded', 'partial_success', 'completed'].includes(status)) {
              imageBatchCompleted = true;
              break;
            }
            if (['failed', 'cancelled', 'interrupted'].includes(status)) {
              throw new Error(`AI annotation batch ${status}.`);
            }
          }
        }
        if (!imageBatchCompleted) throw new Error('AI annotation is still processing. Please check the batch status shortly.');
        setAiCompletionProjectId(targetProjectId);
        api.invalidateProjectCache(targetProjectId);
      }

      showToast(`AI Annotation completed for "${formData.projectName}".`);

      // 5. Navigate to appropriate workspace view based on annotation type
      if (formData.projectType === 'Text Annotation') {
        const selectedType = formData.annotationTypes[0] || 'NER Annotation';
        setActiveNavItem(selectedType);
      } else {
        setSelectedProjectId(targetProjectId);
        const newUrl = `${window.location.pathname}?projectId=${encodeURIComponent(targetProjectId)}`;
        window.history.pushState({ projectId: targetProjectId }, '', newUrl);
        setActiveNavItem('AI Processed result');
      }
    } catch (err: any) {
      showToast(`Error starting AI Annotation: ${err.message || 'Unknown error'}`);
    } finally {
      setIsAiAnnotating(false);
    }
  };

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div id="annotate-ai-app" className="flex min-h-screen bg-[#F6F2EA] text-[#29251D] antialiased font-['Inter',sans-serif]">
      {/* Dark Sidebar */}
      <Sidebar
        currentProject={
          activeNavItem === 'Text Annotation' ||
          activeNavItem === 'All Text Features' ||
          activeNavItem === 'NER Annotation' ||
          activeNavItem === 'Sentiment Annotation' ||
          activeNavItem === 'Text Annotation HITL' ||
          activeNavItem === 'HITL - NER Annotation' ||
          activeNavItem === 'HITL - NER' ||
          activeNavItem === 'HITL - Sentiment Annotation' ||
          activeNavItem === 'HITL - Sentiment' ||
          activeNavItem === 'Quality - Text' ||
          activeNavItem === 'Quality Text' ||
          activeNavItem === 'Quality - NER Annotation' ||
          activeNavItem === 'Quality - Sentiment Annotation' ||
          activeNavItem === 'Quality - Text Classification' ||
          activeNavItem === 'Quality - Relation Extraction'
            ? 'Customer Support Sentiment'
            : activeNavItem === 'Image Annotation' ||
              activeNavItem === 'Object Detection & Labeling' ||
              activeNavItem === 'PII Masking' ||
              activeNavItem === 'Annotation Tasks' ||
              activeNavItem === 'AI Results' ||
              activeNavItem === 'AI Processed result' ||
              activeNavItem === 'Image Annotation HITL' ||
              activeNavItem === 'HITL - Object Detection & Labeling' ||
              activeNavItem === 'HITL - Object Detection' ||
              activeNavItem === 'HITL - PII Masking' ||
              activeNavItem === 'Human Review' ||
              activeNavItem === 'Human Annotator' ||
              activeNavItem === 'Quality' ||
              activeNavItem === 'Quality - Image' ||
              activeNavItem === 'Quality Image' ||
              activeNavItem === 'Quality - Object Detection' ||
              activeNavItem === 'Quality - PII Masking'
            ? 'Urban Object Detection'
            : formData.projectName || 'Urban Traffic Monitoring'
        }
        isOpen={isMobileSidebarOpen}
        onClose={() => setIsMobileSidebarOpen(false)}
        activeItem={activeNavItem}
        onSelectItem={(item) => {
          setActiveNavItem(item);
          showToast(`Switched view to ${item}`);
        }}
        userEmail={currentUserEmail}
      />

      {/* Conditional View Rendering */}
      {activeNavItem === 'Production report' ||
      activeNavItem === 'Production Report' ||
      activeNavItem === 'Dashboard' ? (
        <ProductionReportView
          projectId={selectedProjectId}
          onToggleSidebar={() => setIsMobileSidebarOpen(true)}
          onNavigateToHitl={() => {
            setActiveNavItem('HITL report');
            showToast('Switched to HITL Report');
          }}
          onNavigateToQuality={() => {
            setActiveNavItem('Quality report');
            showToast('Switched to Quality Report');
          }}
          onNavigateToAiResults={(projectId) => {
            setSelectedProjectId(projectId);
            setActiveNavItem('AI Processed result');
            showToast('Opened AI Proceed Results');
          }}
          onNavigateToHumanAnnotator={() => {
            setActiveNavItem('Human Annotator');
            showToast('Opened Human Annotator');
          }}
          onToast={showToast}
          userEmail={currentUserEmail}
        />
      ) : activeNavItem === 'HITL report' || activeNavItem === 'HITL Report' ? (
        <HitlReportView
          onToggleSidebar={() => setIsMobileSidebarOpen(true)}
          onNavigateToProduction={() => {
            setActiveNavItem('Production report');
            showToast('Switched to Production Report');
          }}
          onNavigateToQuality={() => {
            setActiveNavItem('Quality report');
            showToast('Switched to Quality Report');
          }}
          onToast={showToast}
        />
      ) : activeNavItem === 'Text HITL Dashboard' ? (
        <TextHITLDashboardView
          onToggleSidebar={() => setIsMobileSidebarOpen(true)}
          projectId={selectedProjectId}
          onToast={showToast}
        />
      ) : activeNavItem === 'Quality report' || activeNavItem === 'Quality Report' ? (
        <QualityReportView
          onToggleSidebar={() => setIsMobileSidebarOpen(true)}
          onNavigateToProduction={() => {
            setActiveNavItem('Production report');
            showToast('Switched to Production Report');
          }}
          onNavigateToHitl={() => {
            setActiveNavItem('HITL report');
            showToast('Switched to HITL Report');
          }}
          onToast={showToast}
        />
      ) : activeNavItem === 'Quality - Text' || activeNavItem === 'Quality Text' ? (
        <QualityAuditNERWorkspace
          projectId={selectedProjectId}
          mode="NER"
          onToggleSidebar={() => setIsMobileSidebarOpen(true)}
          onNavigateToProjects={() => setActiveNavItem('Projects')}
          onToast={showToast}
        />
      ) : activeNavItem === 'Quality - Image' ||
        activeNavItem === 'Quality Image' ||
        activeNavItem === 'Quality' ||
        activeNavItem === 'Quality Check' ? (
        <QualityAuditImageWorkspace
          projectId={selectedProjectId}
          onToggleSidebar={() => setIsMobileSidebarOpen(true)}
          onNavigateToProjects={() => setActiveNavItem('Projects')}
          onToast={showToast}
        />
      ) : activeNavItem === 'Quality - NER Annotation' ||
      activeNavItem === 'Quality - NER' ||
      activeNavItem === 'Quality - Sentiment Annotation' ||
      activeNavItem === 'Quality - Sentiment' ||
      activeNavItem === 'Quality - Text Classification' ||
      activeNavItem === 'Quality - Relation Extraction' ? (
        <QualityAuditNERWorkspace
          projectId={selectedProjectId}
          mode={
            activeNavItem === 'Quality - Sentiment Annotation' ||
            activeNavItem === 'Quality - Sentiment'
              ? 'Sentiment'
              : activeNavItem === 'Quality - Text Classification'
              ? 'Classification'
              : 'NER'
          }
          onToggleSidebar={() => setIsMobileSidebarOpen(true)}
          onNavigateToProjects={() => setActiveNavItem('Projects')}
          onToast={showToast}
        />
      ) : activeNavItem === 'Text Annotation' ||
      activeNavItem === 'All Text Features' ||
      activeNavItem === 'NER Annotation' ||
      activeNavItem === 'Sentiment Annotation' ||
      activeNavItem === 'Text Classification' ||
      activeNavItem === 'Relation Extraction' ||
      activeNavItem === 'Text Annotation HITL' ||
      activeNavItem === 'HITL - NER Annotation' ||
      activeNavItem === 'HITL - NER' ||
      activeNavItem === 'HITL - Sentiment Annotation' ||
      activeNavItem === 'HITL - Sentiment' ||
      activeNavItem === 'HITL - Text Classification' ||
      activeNavItem === 'HITL - Relation Extraction' ? (
        <TextAnnotationWorkspace
          projectId={selectedProjectId || textAnalysisContext?.projectId}
          assetId={textAnalysisContext?.assetId}
          selectedTask={getSelectedTextTask(activeNavItem)}
          mode={
            activeNavItem.includes('Sentiment')
              ? 'Sentiment'
              : 'NER'
          }
          isHitl={
            activeNavItem === 'Text Annotation HITL' ||
            activeNavItem.startsWith('HITL')
          }
          onSwitchMode={(newMode) => {
            const isHitlMode =
              activeNavItem === 'Text Annotation HITL' ||
              activeNavItem.startsWith('HITL');
            const nextItem =
              newMode === 'Sentiment'
                ? isHitlMode
                  ? 'HITL - Sentiment Annotation'
                  : 'Sentiment Annotation'
                : isHitlMode
                ? 'HITL - NER Annotation'
                : 'NER Annotation';
            setActiveNavItem(nextItem);
            showToast(`Switched to ${nextItem}`);
          }}
          onToggleSidebar={() => setIsMobileSidebarOpen(true)}
          onNavigateToProjects={() => setActiveNavItem('Projects')}
          onToast={showToast}
          currentUserEmail={currentUserEmail}
        />
      ) : activeNavItem === 'AI Results' ||
        activeNavItem === 'AI Processed result' ||
        activeNavItem === 'Image Annotation' ? (
        <ImageAnnotationWorkspace
          mode="Detection"
          isQuality={false}
          projectId={selectedProjectId}
          onToggleSidebar={() => setIsMobileSidebarOpen(true)}
          onNavigateToProjects={() => setActiveNavItem('Projects')}
          onNavigateToReview={() => setActiveNavItem('NER Annotation')}
          onToast={showToast}
        />
      ) : activeNavItem === 'Quality - Object Detection' ||
        activeNavItem === 'Quality - Object Detection & Labeling' ? (
        <QualityAuditImageWorkspace
          projectId={selectedProjectId}
          onToggleSidebar={() => setIsMobileSidebarOpen(true)}
          onNavigateToProjects={() => setActiveNavItem('Projects')}
          onToast={showToast}
        />
      ) : activeNavItem === 'Quality - PII Masking' ||
        activeNavItem === 'Quality PII Masking' ? (
        <QualityAuditPIIMaskingWorkspace
          projectId={selectedProjectId}
          onToggleSidebar={() => setIsMobileSidebarOpen(true)}
          onNavigateToProjects={() => setActiveNavItem('Projects')}
          onToast={showToast}
        />
      ) : activeNavItem === 'HITL - Object Detection & Labeling' ||
        activeNavItem === 'HITL - Object Detection' ||
        activeNavItem === 'Human Annotator' ||
        activeNavItem === 'Image Annotation HITL' ? (
        <HitlObjectDetectionWorkspace
          mode="Detection"
          onToggleSidebar={() => setIsMobileSidebarOpen(true)}
          onToast={showToast}
          currentUserEmail={currentUserEmail}
        />
      ) : activeNavItem === 'HITL - PII Masking' ? (
        <HitlObjectDetectionWorkspace
          mode="PII"
          onToggleSidebar={() => setIsMobileSidebarOpen(true)}
          onToast={showToast}
          currentUserEmail={currentUserEmail}
        />
      ) : activeNavItem === 'Object Detection & Labeling' ||
        activeNavItem === 'PII Masking' ||
        activeNavItem === 'Annotation Tasks' ||
        activeNavItem === 'Human Review' ? (
        <ImageAnnotationWorkspace
          mode={
            activeNavItem === 'PII Masking'
              ? 'PII'
              : 'Detection'
          }
          isQuality={false}
          projectId={selectedProjectId}
          onToggleSidebar={() => setIsMobileSidebarOpen(true)}
          onNavigateToProjects={() => setActiveNavItem('Projects')}
          onNavigateToReview={() => setActiveNavItem('NER Annotation')}
          onToast={showToast}
        />
      ) : activeNavItem === 'Administration' ||
        activeNavItem === 'System Administration' ||
        activeNavItem === 'Governance' ? (
        <SystemAdministrationView
          onToggleSidebar={() => setIsMobileSidebarOpen(true)}
          onToast={showToast}
        />
      ) : activeNavItem === 'Projects' ? (
        <ProjectsView
          onToast={showToast}
          onSelectProject={handleSelectProject}
          onCreateProject={() => {
            resetNewProjectForm();
            setActiveNavItem('Create Project');
            showToast('Create a new annotation project');
          }}
        />
      ) : (
        /* Main Intake Form Page Area */
        <div className="flex flex-1 flex-col min-w-0">
          {/* Top Header */}
          <Header
            onToggleMobileSidebar={() => setIsMobileSidebarOpen(true)}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            onOpenNotifications={() => setIsNotificationsOpen(!isNotificationsOpen)}
            notificationCount={12}
          />

          {/* Notifications Dropdown if opened */}
          {isNotificationsOpen && (
            <div
              id="notifications-popover"
              className="absolute top-16 right-4 sm:right-24 z-40 w-80 rounded-xl bg-white p-4 shadow-xl border border-slate-200"
            >
              <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                <span className="text-xs font-bold text-slate-900">Review Queue (12)</span>
                <button
                  onClick={() => setIsNotificationsOpen(false)}
                  className="text-xs text-blue-600 hover:underline cursor-pointer"
                >
                  Mark all read
                </button>
              </div>
              <div className="mt-2 space-y-2 text-xs">
                <div className="rounded-lg bg-blue-50/60 p-2 text-slate-700">
                  <span className="font-semibold block text-slate-900">12 QA Tasks Pending</span>
                  Assigned in &quot;Urban Traffic Monitoring&quot;.
                </div>
              </div>
            </div>
          )}

          {/* Content Container */}
          <main className="flex-1 px-4 sm:px-8 py-6 max-w-[1600px] w-full mx-auto">
            {/* Page Title */}
            <div className="mb-6">
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900">
                Create New Intake
              </h1>
            </div>

            {/* Main 2-Column Layout */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
              {/* Left Column: Intake Form (approx 70%) */}
              <div className="lg:col-span-8">
                <IntakeForm
                  formData={formData}
                  onChange={handleFormChange}
                  onSaveDraft={handleSaveDraft}
                  onNext={handleAiAnnotate}
                  isLoading={isAiAnnotating}
                  aiCompleted={Boolean(aiCompletionProjectId)}
                  onViewAiResults={() => {
                    if (!aiCompletionProjectId) return;
                    setSelectedProjectId(aiCompletionProjectId);
                    setActiveNavItem('AI Processed result');
                    showToast('Opened AI Proceed Results');
                  }}
                  onViewProductionDashboard={() => {
                    if (!aiCompletionProjectId) return;
                    setSelectedProjectId(aiCompletionProjectId);
                    setActiveNavItem('Production report');
                    showToast('Opened Production Dashboard');
                  }}
                  onResetProject={() => {
                    handleFormChange({
                      projectName: '',
                      projectType: '',
                      annotationTypes: [],
                      mediaFormat: '',
                      dataType: '',
                      cloudStorageUrl: '',
                      inputText: '',
                      visionTechnique: '',
                      targetClasses: [],
                      targetObjectsText: '',
                      numberOfFiles: 0,
                      expectedOutputFormat: '',
                      uploadedFiles: [],
                    });
                    showToast('Project inputs have been reset');
                  }}
                />
              </div>

              {/* Right Column: Project Summary Rail (approx 30%) */}
              <div className="lg:col-span-4 sticky top-22">
                <SummaryRail
                  formData={formData}
                  onEdit={scrollToTop}
                  onViewDocs={() => setIsDocsOpen(true)}
                  onContactSupport={() => setIsSupportOpen(true)}
                />
              </div>
            </div>
          </main>
        </div>
      )}

      {/* Floating Interactive Toast */}
      {toastMessage && (
        <div
          id="toast-notification"
          className="fixed bottom-6 right-6 z-50 flex items-center gap-3 rounded-xl bg-slate-900 text-white px-4 py-3 shadow-xl border border-slate-800 animate-in fade-in slide-in-from-bottom-4 duration-200"
        >
          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400">
            <Check className="h-4 w-4 stroke-[3]" />
          </div>
          <div className="text-xs">
            <span className="font-semibold block">{toastMessage}</span>
          </div>
        </div>
      )}

      {/* Documentation Modal */}
      <DocumentationModal isOpen={isDocsOpen} onClose={() => setIsDocsOpen(false)} />

      {/* Contact Support Modal */}
      <SupportModal
        isOpen={isSupportOpen}
        onClose={() => setIsSupportOpen(false)}
        userEmail={currentUserEmail}
      />

      {/* Review / Final Submission Modal */}
      <SubmissionSuccessModal
        isOpen={isSuccessOpen}
        onClose={() => setIsSuccessOpen(false)}
        formData={formData}
      />
    </div>
  );
}
