import React, { useEffect, useRef, useState } from 'react';
import { TextAIViewer } from './TextAIViewer';
import { TextAIPredictions } from './TextAIPredictions';
import { TextAISummary } from './TextAISummary';
import { NERAnnotationWorkbench } from './NERAnnotationWorkbench';
import { SentimentAnnotationWorkbench } from './SentimentAnnotationWorkbench';
import { TextTaskHitlWorkbench } from './TextTaskHitlWorkbench';
import {
  Menu,
  ChevronRight,
  ChevronLeft,
  AlertCircle,
  UserCheck,
  Tag,
  Smile,
  FileText,
  CheckCircle2,
  Play,
  Loader2,
} from 'lucide-react';
import { api, AnnotationResponse, AssetResponse, HumanAnnotatorTaskResponse, ProjectResponse, TextAnalysisResponse } from '../../services/api';

interface TextAnnotationWorkspaceProps {
  mode?: 'NER' | 'Sentiment';
  selectedTask?: string;
  isHitl?: boolean;
  onSwitchMode?: (mode: 'NER' | 'Sentiment') => void;
  onToggleSidebar?: () => void;
  onNavigateToProjects?: () => void;
  onToast: (msg: string) => void;
  projectId?: string;
  assetId?: string;
  currentUserEmail?: string;
}

export const TextAnnotationWorkspace: React.FC<TextAnnotationWorkspaceProps> = ({
  mode = 'NER',
  selectedTask,
  isHitl = false,
  onSwitchMode,
  onToggleSidebar,
  onNavigateToProjects,
  onToast,
  projectId,
  assetId,
  currentUserEmail,
}) => {
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [currentAssetIndex, setCurrentAssetIndex] = useState<number>(0);
  const [textAssets, setTextAssets] = useState<AssetResponse[]>([]);
  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [textAsset, setTextAsset] = useState<AssetResponse | null>(null);
  const [analysis, setAnalysis] = useState<TextAnalysisResponse | null>(null);
  const [isRunningAnalysis, setIsRunningAnalysis] = useState(false);
  const [hitlTask, setHitlTask] = useState<HumanAnnotatorTaskResponse | null>(null);
  const [resolvedProjectId, setResolvedProjectId] = useState(projectId || '');
  const [isAssignedToHitl, setIsAssignedToHitl] = useState<boolean>(false);
  const batchStatusByAsset = useRef<Record<string, string>>({});
  const analysisCacheRef = useRef<Map<string, TextAnalysisResponse>>(new Map());
  const [allFeatureTask, setAllFeatureTask] = useState('ALL');
  const isAllFeatures = selectedTask === 'ALL_TEXT_FEATURES';
  const activeTask = isAllFeatures ? allFeatureTask : selectedTask;

  const resolvedTaskType = String(activeTask || analysis?.analysis_type || project?.task_type || '')
    .trim()
    .toUpperCase();
  const resolvedCapability = String(analysis?.capability || '').trim().toLowerCase();
  const isTextClassification =
    resolvedTaskType === 'TEXT_CLASSIFICATION' || resolvedCapability === 'text_classification';
  const isSentiment = resolvedTaskType === 'SENTIMENT_ANALYSIS' || resolvedCapability === 'text_sentiment_analysis';
  const isNer = resolvedTaskType === 'NER' || resolvedTaskType === 'ENTITY_EXTRACTION' || resolvedCapability === 'text_entity_extraction';
  const isRelationExtraction =
    resolvedTaskType === 'RELATION_EXTRACTION' || resolvedCapability === 'text_relation_extraction';
  const analysisLevel = analysis?.raw_result?.analysis_level || 'document';
  const activeMode = activeTask === 'SENTIMENT_ANALYSIS' ? 'Sentiment' : mode;
  const pageTitle = isAllFeatures
    ? 'All Text Features'
    : isTextClassification
    ? 'Text Classification'
    : isSentiment
    ? 'Sentiment Annotation'
    : isNer
    ? 'NER Annotation'
    : isRelationExtraction
    ? 'Relation Extraction'
    : 'Text Annotation';
  const taskTypeLabel = isTextClassification
    ? 'Text Classification'
    : isSentiment
    ? 'Sentiment Analysis'
    : isNer
    ? 'Named Entity Recognition'
    : isRelationExtraction
    ? 'Relation Extraction'
    : isAllFeatures && activeTask === 'ALL'
    ? 'All Text Features'
    : 'Text Annotation';

  const getAnalysisTask = (result: TextAnalysisResponse) => {
    const task = `${result.analysis_type || ''} ${result.capability || ''}`.toUpperCase();
    if (task.includes('SENTIMENT')) return 'SENTIMENT_ANALYSIS';
    if (task.includes('CLASSIFICATION')) return 'TEXT_CLASSIFICATION';
    if (task.includes('RELATION')) return 'RELATION_EXTRACTION';
    if (task.includes('NER') || task.includes('ENTITY_EXTRACTION')) return 'NER';
    return '';
  };

  const normalizeTextTask = (value?: string) => {
    const task = String(value || '').trim().toUpperCase().replace(/[\s-]+/g, '_');
    if (task === 'ENTITY_EXTRACTION' || task === 'TEXT_ENTITY_EXTRACTION' || task === 'NER') return 'NER';
    if (task === 'SENTIMENT' || task === 'SENTIMENT_ANALYSIS') return 'SENTIMENT_ANALYSIS';
    if (task === 'CLASSIFICATION' || task === 'TEXT_CLASSIFICATION') return 'TEXT_CLASSIFICATION';
    if (task === 'RELATION' || task === 'RELATION_EXTRACTION') return 'RELATION_EXTRACTION';
    return task;
  };

  const loadSelectedAnalysis = async (projectId: string, assetId: string) => {
    const analyses = await api.getTextAnalyses(projectId, assetId);
    if (!isAllFeatures) {
      const expectedTask = String(activeTask || project?.task_type || '').trim().toUpperCase();
      const normalizedExpectedTask = normalizeTextTask(expectedTask);
      const matchingAnalysis = analyses.find((result) => getAnalysisTask(result) === normalizedExpectedTask);
      if (matchingAnalysis) return matchingAnalysis;

      // Legacy installations may only expose the latest result endpoint. Use it
      // only when its task matches the currently selected text feature.
      const legacyAnalysis = await api.getTextAnalysis(projectId, assetId);
      return legacyAnalysis && resultMatchesSelectedTask(legacyAnalysis, project?.task_type)
        ? legacyAnalysis
        : null;
    }
    if (activeTask === 'ALL') {
      if (analyses.length === 0) return null;
      const annotations = analyses.flatMap((result) =>
        (result.annotations || []).map((annotation, index) => ({
          ...annotation,
          id: `${getAnalysisTask(result) || 'task'}:${annotation.id || index}`,
        }))
      );
      return {
        ...analyses[0],
        analysis_type: 'ALL_TEXT_FEATURES',
        capability: undefined,
        annotations,
        quality_report: { annotation_count: annotations.length },
      };
    }
    return analyses.find((result) => getAnalysisTask(result) === activeTask) || null;
  };

  const resultMatchesSelectedTask = (result: TextAnalysisResponse, projectTaskType?: string) => {
    const expectedTask = String(activeTask || '').trim().toUpperCase();
    if (!expectedTask) return true;

    if (isAllFeatures) {
      return expectedTask === 'ALL'
        ? result.analysis_type === 'ALL_TEXT_FEATURES'
        : getAnalysisTask(result) === expectedTask;
    }

    const detectedTask = getAnalysisTask(result);
    const normExpected = normalizeTextTask(expectedTask);
    if (detectedTask && detectedTask === normExpected) return true;

    const actualTask = String(result.analysis_type || projectTaskType || '').trim().toUpperCase();
    if (!actualTask) return false;

    const normActual = normalizeTextTask(actualTask);
    return normActual === normExpected;
  };

  const taskCapability = (task?: string) => {
    switch (String(task || '').trim().toUpperCase()) {
      case 'ENTITY_EXTRACTION':
      case 'TEXT_ENTITY_EXTRACTION':
      case 'NER':
        return 'text_entity_extraction';
      case 'SENTIMENT_ANALYSIS':
      case 'SENTIMENT':
        return 'text_sentiment_analysis';
      case 'TEXT_CLASSIFICATION':
      case 'CLASSIFICATION':
        return 'text_classification';
      case 'RELATION_EXTRACTION':
      case 'RELATION':
        return 'text_relation_extraction';
      default:
        return undefined;
    }
  };

  const activeCapability = taskCapability(activeTask);

  const annotationMatchesCurrentTask = (annotation: AnnotationResponse) => {
    const provenance = annotation.provenance || {};
    const rawCap = String(provenance.capability || '').trim().toLowerCase();
    const modelId = String(annotation.model_id || '').trim().toLowerCase();
    const geometryType = String(annotation.geometry_type || '').toLowerCase();
    if (activeTask === 'ENTITY_EXTRACTION' || activeTask === 'NER') {
      if (rawCap === 'text_entity_extraction' || rawCap === 'ner' || rawCap === 'entity_extraction') return true;
      if (modelId === 'text_entity_extraction') return true;
      // Classification/sentiment results can also carry text_span; geometry
      // shape alone is not enough unless it is the NER-specific text_span type.
      return geometryType === 'text_span';
    }

    if (activeTask === 'SENTIMENT_ANALYSIS') {
      if (rawCap === 'text_sentiment_analysis' || rawCap === 'sentiment') return true;
      // text_classification geometry is shared by sentiment and classification;
      // geometry alone must never leak one task's results into the other.
      return false;
    }

    if (activeTask === 'TEXT_CLASSIFICATION') {
      if (rawCap === 'text_classification' || rawCap === 'classification') return true;
      return false;
    }

    if (activeTask === 'RELATION_EXTRACTION') {
      if (rawCap === 'text_relation_extraction' || rawCap === 'relation') return true;
      return geometryType === 'text_relation';
    }

    if (rawCap && activeCapability) return rawCap === activeCapability;
    return true;
  };

  useEffect(() => {
    let isMounted = true;
    const load = async () => {
      try {
        // A task switch must not render the previous task's result while the
        // selected task's persisted result is being loaded.
        setAnalysis(null);
        setSelectedEntityId(null);
        const projects = await api.getProjects();
        const textProjects = projects.filter(
          (p) =>
            p.project_type?.toLowerCase().includes('text') ||
            ['text', 'document'].includes(String((p as ProjectResponse & { modality?: string }).modality || '').toLowerCase()) ||
            p.name.toLowerCase().includes('text') ||
            p.name.toLowerCase().includes('sentiment') ||
            p.name.toLowerCase().includes('ner')
        );
        let hitlTasksForProject: HumanAnnotatorTaskResponse[] | null = null;
        let proj = projectId ? projects.find((p) => p.id === projectId) : undefined;

        // The sidebar can open HITL without a project id. Select the text
        // project that actually owns the pending review queue in that case.
        if (!proj && isHitl) {
          for (const candidate of textProjects) {
            const candidateTasks = await api.getHumanAnnotatorTasks(candidate.id);
            if (candidateTasks.length > 0) {
              proj = candidate;
              hitlTasksForProject = candidateTasks;
              break;
            }
            const candidateAssets = await api.getProjectAssets(candidate.id);
            const hasHumanReviewAssets = candidateAssets.some((item) => {
              const status = String(item.review_status || item.status || '').trim().toLowerCase();
              return (
                ['human_review', 'human_review_required', 'in_human_review', 'human_rework_required', 'pending', 'rework'].includes(status) ||
                (item.mean_confidence != null && Number(item.mean_confidence) < 0.95 && !status.includes('approved'))
              );
            });
            if (hasHumanReviewAssets) {
              proj = candidate;
              break;
            }
          }
        }
        proj = proj || textProjects[0] || projects[0];

        if (!proj || !isMounted) return;
        setResolvedProjectId(proj.id);
        setProject(proj);

        const assets = await api.getProjectAssets(proj.id);
        const textList = assets.filter(
          (item) =>
            item.content_type?.startsWith('text') ||
            item.content_type === 'application/pdf' ||
            item.content_type === 'application/msword' ||
            item.content_type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
            item.filename?.match(/\.(txt|csv|json|md|pdf|doc|docx)$/i) ||
            !item.content_type ||
            item.content_type === 'text/plain'
        );
        let availableTextAssets = textList;
        const hitlTaskByAsset = new Map<string, HumanAnnotatorTaskResponse>();
        const hitlAnalysisByAsset = new Map<string, TextAnalysisResponse>();
        if (isHitl) {
          const tasks = hitlTasksForProject || await api.getHumanAnnotatorTasks(proj.id);
          tasks.forEach((task) => hitlTaskByAsset.set(task.asset_id, task));
          const openHumanReviewStatuses = new Set([
            'human_review_required',
            'in_human_review',
            'human_rework_required',
            'human_review',
            'pending',
            'rework',
          ]);
          availableTextAssets = textList.filter((item) => {
            const task = hitlTaskByAsset.get(item.id);
            const taskStatus = String(task?.status || '').trim().toLowerCase();
            const assetStatus = String(item.review_status || item.status || '').trim().toLowerCase();
            const taskIsOpen = Boolean(task && openHumanReviewStatuses.has(taskStatus));
            const assetIsOpen = openHumanReviewStatuses.has(assetStatus);
            const lowConfidenceReview =
              item.mean_confidence != null &&
              Number(item.mean_confidence) < 0.95 &&
              !assetStatus.includes('approved');
            return taskIsOpen || assetIsOpen || lowConfidenceReview;
          });
          if (activeTask) {
            const taskAnalyses = await Promise.all(
              availableTextAssets.map(async (item) => ({
                asset: item,
                analysis: await loadSelectedAnalysis(proj.id, item.id),
              }))
            );
            const matchingTaskAssets = taskAnalyses
              .filter(({ analysis: taskAnalysis }) => resultMatchesSelectedTask(taskAnalysis || {}, proj.task_type))
              .map(({ asset, analysis: taskAnalysis }) => {
                if (taskAnalysis) hitlAnalysisByAsset.set(asset.id, taskAnalysis);
                return asset;
              });
            if (matchingTaskAssets.length > 0) {
              availableTextAssets = matchingTaskAssets;
            }
          }
          if (availableTextAssets.length === 0 && textList.length > 0) {
            availableTextAssets = textList;
          }
        }

        if (!isMounted) return;
        setTextAssets(availableTextAssets);

        if (availableTextAssets.length > 0) {
          const requestedAsset = assetId ? availableTextAssets.find((item) => item.id === assetId) : null;
          const initialAsset = requestedAsset || availableTextAssets[0];
          const initialIndex = Math.max(0, availableTextAssets.findIndex((item) => item.id === initialAsset.id));
          setCurrentAssetIndex(initialIndex);
          setTextAsset(initialAsset);
          setHitlTask(hitlTaskByAsset.get(initialAsset.id) || null);
          hitlAnalysisByAsset.forEach((val, key) => {
            if (val) analysisCacheRef.current.set(key, val);
          });
          let result = hitlAnalysisByAsset.get(initialAsset.id) || await loadSelectedAnalysis(proj.id, initialAsset.id);
          if (!result || !result.text) {
            const fallbackAnalysis = await api.getTextAnalysis(proj.id, initialAsset.id);
            if (fallbackAnalysis && (fallbackAnalysis.text || (fallbackAnalysis.annotations && fallbackAnalysis.annotations.length > 0))) {
              result = {
                ...fallbackAnalysis,
                ...(result || {}),
                text: fallbackAnalysis.text || result?.text || '',
              };
            }
          }
          if (result) {
            analysisCacheRef.current.set(initialAsset.id, result);
          }
          if (isMounted) {
            if (
              result &&
              (result.analysis_id || (result.annotations && result.annotations.length > 0) || result.text)
            ) {
              setAnalysis((current) =>
                current?.asset_id === initialAsset.id && (current.annotations?.length || 0) > 0
                  ? { ...result, ...current }
                  : result
              );
            } else {
              setAnalysis({
                asset_id: initialAsset.id,
                text: '',
                annotations: [],
              } as any);
            }
          }
        } else {
          setTextAsset(null);
          setAnalysis(null);
          setHitlTask(null);
        }
      } catch (err) {
        console.error('Error loading text annotation workspace:', err);
      }
    };
    load();
    return () => {
      isMounted = false;
    };
  }, [projectId, assetId, activeTask, isAllFeatures, isHitl]);

  useEffect(() => {
    const activeProjectId = resolvedProjectId;
    const activeAssetId = textAsset?.id;
    if (!activeProjectId || !activeAssetId) return;

    let isMounted = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const refreshPersistedAnnotations = async (allowEmptyCompletedResult = false) => {
      const [persisted, persistedAnalysis] = await Promise.all([
        api.getAssetAnnotations(activeAssetId),
        loadSelectedAnalysis(activeProjectId, activeAssetId),
      ]);
      if (!isMounted) return;

      const persistedTaskMatches =
        persistedAnalysis &&
        resultMatchesSelectedTask(persistedAnalysis, project?.task_type) &&
        (persistedAnalysis.annotations?.length || 0) > 0;
      const currentAssetAnnotations = persisted.filter(
        (annotation) => annotation.asset_id === activeAssetId && annotationMatchesCurrentTask(annotation)
      );
      const annotations = persistedTaskMatches
        ? (persistedAnalysis?.annotations || []).map((annotation) => ({
            ...annotation,
            id: annotation.id,
          }))
        : currentAssetAnnotations.map((annotation) => {
            const geometry = annotation.text_span || annotation.geometry;

            return {
              id: annotation.id,
              label: annotation.label,
              text_span: geometry,
              geometry: annotation.geometry,
              confidence: annotation.confidence ?? undefined,
              geometry_type: annotation.geometry_type,
              model_id: annotation.model_id,
              provenance: annotation.provenance,
            };
          });

      setAnalysis((current) => {
        const validCurrent = current?.asset_id === activeAssetId ? current : null;
        const hasAnalysisPayload = Boolean(
          validCurrent ||
            persistedAnalysis?.analysis_id ||
            persistedAnalysis?.text ||
            persistedAnalysis?.annotations?.length ||
            persistedAnalysis?.status
        );
        if (!hasAnalysisPayload && annotations.length === 0 && !allowEmptyCompletedResult) {
          return validCurrent;
        }

        const base = validCurrent || persistedAnalysis || {};
        return {
          ...base,
          project_id: activeProjectId,
          asset_id: activeAssetId,
          analysis_type: base.analysis_type || activeTask || project?.task_type || 'NER',
          text: persistedAnalysis?.text || base.text,
          agent_status: base.agent_status || (allowEmptyCompletedResult ? 'COMPLETED' : undefined),
          annotations,
          quality_report: {
            ...(base.quality_report || {}),
            annotation_count: annotations.length,
          },
        };
      });
    };

    const pollBatchStatus = async () => {
      const batches = await api.getProjectBatches(activeProjectId);
      if (!isMounted) return;

      const matchingItems = batches.flatMap((batch) =>
        (batch.items || [])
          .filter((item) => item.asset_id === activeAssetId)
          .map((item) => ({ item, batch }))
      );
      const latest = matchingItems[matchingItems.length - 1];
      const status = (latest?.item.status || latest?.batch.status || '').toLowerCase();
      const previousStatus = batchStatusByAsset.current[activeAssetId];
      const wasPending = !previousStatus || previousStatus === 'queued' || previousStatus === 'processing' || previousStatus === 'running';
      const succeeded = status === 'succeeded' || status === 'completed';

      if (status) batchStatusByAsset.current[activeAssetId] = status;
      if (succeeded && wasPending) {
        await refreshPersistedAnnotations(true);
      }

      const shouldContinuePolling =
        status === 'queued' ||
        status === 'processing' ||
        status === 'running' ||
        (!status && wasPending);

      if (isMounted && shouldContinuePolling) {
        timer = setTimeout(pollBatchStatus, 2000);
      }
    };

    // Hydrate persisted annotations on mount as well as after a status
    // transition, so returning to an already-completed asset renders results.
    refreshPersistedAnnotations().catch((err) => {
      console.error('Error loading persisted text annotations:', err);
    });

    pollBatchStatus().catch((err) => {
      console.error('Error polling text annotation batch status:', err);
    });

    return () => {
      isMounted = false;
      if (timer) clearTimeout(timer);
    };
  }, [resolvedProjectId, textAsset?.id, activeTask, isAllFeatures]);

  // Keep the review decision in sync when the annotator moves between queued
  // text assets. The initial project load hydrates this value, but navigation
  // can change the asset without remounting the workspace.
  useEffect(() => {
    if (!isHitl || !resolvedProjectId || !textAsset?.id) {
      setHitlTask(null);
      return;
    }
    let active = true;
    void api.getHumanAnnotatorTasks(resolvedProjectId).then((tasks) => {
      if (!active) return;
      setHitlTask(tasks.find((task) => task.asset_id === textAsset.id) || null);
    }).catch(() => {
      if (active) setHitlTask(null);
    });
    return () => { active = false; };
  }, [isHitl, resolvedProjectId, textAsset?.id]);

  const loadAssetAtIndex = async (index: number) => {
    if (index < 0 || index >= textAssets.length || !resolvedProjectId) return;
    const targetAsset = textAssets[index];
    setCurrentAssetIndex(index);
    setTextAsset(targetAsset);
    setSelectedEntityId(null);
    setIsAssignedToHitl(targetAsset.review_status === 'assigned' || targetAsset.review_status === 'in_review');

    // 1. Instant Cache Hit: render in 0ms without clearing to null or showing empty state
    const cached = analysisCacheRef.current.get(targetAsset.id);
    if (cached) {
      setAnalysis(cached);
    } else {
      setAnalysis((prev) => (prev?.asset_id === targetAsset.id ? prev : null));
    }

    try {
      let result = cached || await loadSelectedAnalysis(resolvedProjectId, targetAsset.id);
      if (!result || !result.text) {
        const fallbackAnalysis = await api.getTextAnalysis(resolvedProjectId, targetAsset.id);
        if (fallbackAnalysis && (fallbackAnalysis.text || fallbackAnalysis.annotations?.length)) {
          result = { ...fallbackAnalysis, ...(result || {}), text: fallbackAnalysis.text || result?.text || '' };
        }
      }
      if (result) {
        analysisCacheRef.current.set(targetAsset.id, result);
        setAnalysis(result);
      } else if (!cached) {
        setAnalysis({ asset_id: targetAsset.id, text: '', annotations: [] } as any);
      }

      // Prefetch adjacent assets in the background so next/submit clicks are instant (0ms)
      const adjacentIndices = [index + 1, index - 1];
      for (const adjIdx of adjacentIndices) {
        if (adjIdx >= 0 && adjIdx < textAssets.length) {
          const adjAsset = textAssets[adjIdx];
          if (!analysisCacheRef.current.has(adjAsset.id)) {
            void loadSelectedAnalysis(resolvedProjectId, adjAsset.id).then((adjResult) => {
              if (adjResult) analysisCacheRef.current.set(adjAsset.id, adjResult);
            }).catch(() => {});
          }
        }
      }

      // Run background AI analysis asynchronously without blocking asset navigation
      if ((!result || !result.annotations?.length) && !isRunningAnalysis) {
        const task = String(activeTask || project?.task_type || 'NER').trim().toUpperCase();
        const analysisType = task.includes('SENTIMENT')
          ? 'Sentiment'
          : task.includes('CLASSIFICATION')
          ? 'Classification'
          : task.includes('RELATION')
          ? 'Relation'
          : 'NER';

        void api.analyzeText({
          projectId: resolvedProjectId,
          assetId: targetAsset.id,
          analysisType: isAllFeatures ? ('ALL' as any) : (analysisType as any),
          assessmentName: `${project?.name || 'Text'} Analysis`,
          identificationName: project?.target_objects_text || undefined,
        }).then((autoResult) => {
          if (autoResult && (autoResult.text || autoResult.annotations?.length)) {
            analysisCacheRef.current.set(targetAsset.id, autoResult);
            setAnalysis((current) => current?.asset_id === targetAsset.id ? autoResult : current);
          }
        }).catch((autoErr) => {
          console.warn('Background AI analysis notice:', autoErr);
        });
      }
    } catch (err) {
      console.error('Error loading text analysis:', err);
    }
  };

  const handleFeatureClick = async (taskId: string) => {
    setAllFeatureTask(taskId);
    if (!resolvedProjectId || !textAsset?.id) return;

    // Do not keep the previous feature's result visible while the selected
    // feature is being loaded. A relation result here can otherwise make the
    // Classification screen render an empty relation state.
    setAnalysis(null);

    try {
      const taskNorm = taskId === 'SENTIMENT_ANALYSIS'
        ? 'Sentiment'
        : taskId === 'TEXT_CLASSIFICATION'
        ? 'Classification'
        : taskId === 'RELATION_EXTRACTION'
        ? 'Relation'
        : taskId === 'ALL'
        ? 'ALL'
        : 'NER';

      let result = await loadSelectedAnalysis(resolvedProjectId, textAsset.id);
      
      if (!result && !isRunningAnalysis) {
        setIsRunningAnalysis(true);
        try {
          const newResult = await api.analyzeText({
            projectId: resolvedProjectId,
            assetId: textAsset.id,
            analysisType: taskNorm as any,
            assessmentName: `${project?.name || 'Text'} Analysis`,
            identificationName: project?.target_objects_text || undefined,
          });
          if (newResult) {
            result = newResult;
          }
        } catch (err) {
          console.warn('Feature analysis execution failed:', err);
        } finally {
          setIsRunningAnalysis(false);
        }
      }

      setAnalysis(result || null);
    } catch (err) {
      console.error('Error switching feature tab:', err);
    }
  };

  const handleRunAiAnnotation = async () => {
    if (isRunningAnalysis) return;
    if (!resolvedProjectId || !textAsset?.id) {
      onToast('Please open a text project from Projects before running NER annotation.');
      onNavigateToProjects?.();
      return;
    }
    const task = String(activeTask || project?.task_type || 'NER').trim().toUpperCase();
    const analysisType = task.includes('SENTIMENT')
      ? 'Sentiment'
      : task.includes('CLASSIFICATION')
      ? 'Classification'
      : task.includes('RELATION')
      ? 'Relation'
      : 'NER';

    setIsRunningAnalysis(true);
    onToast('Starting AI annotation for the selected asset...');
    try {
      const analysisTypes = isAllFeatures && activeTask === 'ALL'
        ? ['NER', 'Sentiment', 'Classification', 'Relation']
        : [analysisType];
      for (const selectedAnalysisType of analysisTypes) {
        await api.analyzeText({
          projectId: resolvedProjectId,
          assetId: textAsset.id,
          analysisType: selectedAnalysisType as any,
          assessmentName: `${project?.name || 'Text'} Analysis`,
        });
      }
      const result = await loadSelectedAnalysis(resolvedProjectId, textAsset.id);
      if (result) setAnalysis(result);
      onToast('AI annotation completed for the selected asset.');
    } catch (err) {
      onToast(err instanceof Error ? err.message : 'AI annotation failed.');
    } finally {
      setIsRunningAnalysis(false);
    }
  };

  const handlePrev = () => {
    if (currentAssetIndex > 0) {
      loadAssetAtIndex(currentAssetIndex - 1);
    }
  };

  const handleNext = () => {
    if (currentAssetIndex < textAssets.length - 1) {
      loadAssetAtIndex(currentAssetIndex + 1);
    }
  };

  const handleSelectEntity = (id: string) => {
    setSelectedEntityId(id);
    const foundAnnotation = (analysis?.annotations || []).find(
      (a, idx) => (a.id || `annotation-${idx}`) === id
    );
    if (foundAnnotation) {
      const label = foundAnnotation.label || 'Annotation';
      const text = foundAnnotation.text_span?.text || 'Text span';
      onToast(`Selected entity: ${text} (${label})`);
    }
  };

  const handleAssignHitl = () => {
    setIsAssignedToHitl(true);
    onToast('Assigned to Human Annotator (HITL). Text asset routed to verification queue.');
  };

  // Compute Quality Gate metrics dynamically from real analysis
  const annotations = analysis?.annotations || [];
  const confidenceValues = annotations
    .map((item) => item.confidence)
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  const qualityReport = analysis?.quality_report as
    | {
        score?: number | null;
        confidence_score?: number | null;
        pass_threshold?: number | null;
        confidence_threshold?: number | null;
        final_decision?: string;
      }
    | undefined;

  const meanConfidence =
    confidenceValues.length > 0
      ? confidenceValues.reduce((sum, value) => sum + value, 0) / confidenceValues.length
      : qualityReport?.confidence_score ?? qualityReport?.score ?? null;

  const finalDecision = qualityReport?.final_decision || analysis?.agent_status;
  const threshold = qualityReport?.confidence_threshold ?? qualityReport?.pass_threshold ?? 0.95;
  const isPassed =
    meanConfidence !== null &&
    meanConfidence >= threshold &&
    finalDecision !== 'HUMAN_REVIEW';
  const requiresHumanReview =
    finalDecision === 'HUMAN_REVIEW' ||
    meanConfidence === null ||
    (meanConfidence !== null && meanConfidence < threshold);
  const confidenceDecisionText =
    meanConfidence === null
      ? `Confidence score is unavailable, so the asset cannot pass the ${Math.round(threshold * 100)}% threshold requirement.`
      : `Confidence score (${Math.round(meanConfidence * 100)}% / ${meanConfidence.toFixed(2)}) is ${
          meanConfidence >= threshold ? 'at or above' : 'below'
        } the ${Math.round(threshold * 100)}% threshold requirement.`;

  // If in dedicated HITL Workbench mode, render the interactive workbench
  if (isHitl) {
    if (isNer || isSentiment || isTextClassification || isRelationExtraction) {
      return (
        <TextTaskHitlWorkbench
          taskType={
            isNer
              ? 'NER'
              : isSentiment
              ? 'SENTIMENT_ANALYSIS'
              : isTextClassification
              ? 'TEXT_CLASSIFICATION'
              : 'RELATION_EXTRACTION'
          }
          onToggleSidebar={onToggleSidebar}
          onToast={onToast}
          onSubmit={async (annotations) => {
            await api.submitHumanReview(
              hitlTask?.id || textAsset?.id || '',
              annotations,
              currentUserEmail || 'HUMAN_ANNOTATOR'
            );
          }}
          textAsset={textAsset}
          project={project}
          analysis={analysis}
          totalAssets={textAssets.length}
          currentAssetIndex={currentAssetIndex}
          onPrevAsset={handlePrev}
          onNextAsset={handleNext}
          currentUserEmail={currentUserEmail}
        />
      );
    }
    if (mode === 'Sentiment') {
      return (
        <div id="text-annotation-workspace-hitl" className="flex-1 flex flex-col min-w-0 overflow-y-auto bg-[#F6F2EA]">
          <SentimentAnnotationWorkbench
            onSwitchMode={onSwitchMode}
            onToggleSidebar={onToggleSidebar}
            onToast={onToast}
            textAsset={textAsset}
            project={project}
            analysis={analysis}
            totalAssets={textAssets.length}
            currentAssetIndex={currentAssetIndex}
            onPrevAsset={handlePrev}
            onNextAsset={handleNext}
            currentUserEmail={currentUserEmail}
          />
        </div>
      );
    }
    return (
      <div id="text-annotation-workspace-hitl" className="flex-1 flex flex-col min-w-0 overflow-y-auto bg-[#F6F2EA]">
        <NERAnnotationWorkbench
          onSwitchMode={onSwitchMode}
          onToggleSidebar={onToggleSidebar}
          onToast={onToast}
          textAsset={textAsset}
          project={project}
          analysis={analysis}
          totalAssets={textAssets.length}
          currentAssetIndex={currentAssetIndex}
          onPrevAsset={handlePrev}
          onNextAsset={handleNext}
          currentUserEmail={currentUserEmail}
        />
      </div>
    );
  }

  return (
    <div id="text-annotation-workspace" className="flex-1 flex flex-col min-w-0 overflow-y-auto bg-[#F6F8FB]">
      {/* Mobile Top Bar */}
      {onToggleSidebar && (
        <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-slate-200 lg:hidden">
          <button
            id="toggle-sidebar-text-workspace-btn"
            onClick={onToggleSidebar}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 cursor-pointer"
            aria-label="Toggle navigation"
          >
            <Menu className="h-5 w-5" />
          </button>
          <span className="text-xs font-bold text-slate-800">{taskTypeLabel}</span>
          <div className="w-5" />
        </div>
      )}

      {/* Main Workspace Body */}
      <main className="flex-1 p-3 sm:p-5 lg:p-6 space-y-4 max-w-[1700px] w-full mx-auto">
        {/* Page Title & Status Header */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div
              className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-white shadow-xs ${
                activeMode === 'Sentiment'
                  ? 'bg-emerald-600 shadow-emerald-500/20'
                  : 'bg-blue-600 shadow-blue-500/20'
              }`}
            >
              {activeMode === 'Sentiment' ? (
                <Smile className="h-6 w-6" />
              ) : (
                <Tag className="h-6 w-6" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-xl md:text-2xl font-black text-slate-900 tracking-tight">
                  {pageTitle}
                </h1>
                {isHitl && (
                  <span
                    id="hitl-mode-badge"
                    className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-[11px] font-bold text-amber-800 ring-1 ring-amber-200"
                  >
                    <UserCheck className="h-3 w-3 text-amber-600" />
                    HITL Verification
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                {isHitl
                  ? `Human-in-the-Loop review: verify and adjust AI-predicted ${
                      isTextClassification
                        ? 'text classification results and document-level labels.'
                        : isSentiment
                        ? 'sentiment classifications and aspect polarities.'
                        : isRelationExtraction
                        ? 'extracted relationships between entities in the text.'
                        : 'named entities, token spans, and label boundaries.'
                    }`
                  : isTextClassification
                  ? 'Review AI text classifications and category predictions at the configured analysis level.'
                  : isSentiment
                  ? 'Analyze customer sentiment polarity, emotional tone, and aspect confidence scores.'
                  : isNer
                  ? 'View AI Named Entity Recognition (NER), detected entity spans, and token labels.'
                  : isRelationExtraction
                  ? 'Review AI-extracted relationships between entities in the text.'
                  : 'Load the actual text annotation task metadata to view its results.'}
              </p>
            </div>
          </div>

        </div>

        {isAllFeatures && (
          <div className="flex flex-wrap gap-2" role="tablist" aria-label="Text feature results">
            {[
              { id: 'ALL', label: 'All Results' },
              { id: 'NER', label: 'NER' },
              { id: 'SENTIMENT_ANALYSIS', label: 'Sentiment' },
              { id: 'TEXT_CLASSIFICATION', label: 'Classification' },
              { id: 'RELATION_EXTRACTION', label: 'Relation Extraction' },
            ].map((task) => (
              <button
                key={task.id}
                type="button"
                role="tab"
                aria-selected={activeTask === task.id}
                onClick={() => handleFeatureClick(task.id)}
                className={`rounded-lg border px-3 py-2 text-xs font-semibold transition cursor-pointer ${
                  activeTask === task.id
                    ? 'border-blue-600 bg-blue-50 text-blue-800'
                    : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                {task.label}
              </button>
            ))}
          </div>
        )}

        {/* Asset Metadata Strip Card */}
        <div
          id="text-asset-metadata-card"
          className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-2xs"
        >
          {/* File Name & Task ID */}
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 border border-blue-100 text-blue-600 shrink-0">
              <FileText className="h-5 w-5" />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                TASK ID:
              </span>
              <span className="text-sm font-bold text-slate-900 font-mono">
                {textAsset ? (textAsset.filename || textAsset.id) : 'N/A'}
              </span>
            </div>
          </div>

          {textAssets.length > 0 && (
            <label className="flex min-w-[220px] flex-1 items-center gap-2 text-xs font-semibold text-slate-600">
              <span className="whitespace-nowrap">PDF</span>
              <select
                id="text-pdf-selector"
                value={textAsset?.id || ''}
                onChange={(event) => {
                  const index = textAssets.findIndex((item) => item.id === event.target.value);
                  if (index >= 0) void loadAssetAtIndex(index);
                }}
                className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-800 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                aria-label="Select PDF document"
              >
                {textAssets.map((asset, index) => (
                  <option key={asset.id} value={asset.id}>
                    {`${index + 1}. ${asset.filename || asset.id}`}
                  </option>
                ))}
              </select>
            </label>
          )}

          {/* Key Metric Columns */}
          <div className="flex flex-wrap items-center gap-6 text-xs divide-x divide-slate-100">
            <div>
              <span className="block text-[11px] font-medium text-slate-400">Project</span>
              <span className="font-semibold text-slate-800">{project?.name || 'N/A'}</span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] font-medium text-slate-400">Modality</span>
              <span className="font-semibold text-slate-800">
                {textAsset?.content_type?.split('/')[0]?.toUpperCase() || 'TEXT'}
              </span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] font-medium text-slate-400">Format</span>
              <span className="font-semibold text-slate-800">
                {textAsset?.filename ? textAsset.filename.split('.').pop()?.toUpperCase() || 'TXT' : 'TXT'}
              </span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] font-medium text-slate-400">Size</span>
              <span className="font-semibold text-slate-800">
                {textAsset?.byte_size ? `${(textAsset.byte_size / 1024).toFixed(1)} KB` : 'N/A'}
              </span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] font-medium text-slate-400">Status</span>
              <span className="font-semibold text-slate-800 uppercase">
                {textAsset?.status || 'Active'}
              </span>
            </div>
          </div>
        </div>

        {/* 2-Column Responsive Layout matching Screenshot */}
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-5 items-start">
          {/* Left Column: Text Canvas Card + Pagination + Threshold Decision Card */}
          <div className="xl:col-span-8 space-y-4">
            {/* Top Interactive Text Canvas Card */}
            <TextAIViewer
              selectedEntityId={selectedEntityId}
              onSelectEntity={handleSelectEntity}
              onToast={onToast}
              mode={activeMode}
              taskType={taskTypeLabel}
              text={analysis?.text}
              annotations={analysis?.annotations}
              analysisLevel={analysisLevel as 'document' | 'page' | 'paragraph' | 'sentence'}
            />

            {/* Pagination Controls */}
            <div
              id="text-canvas-pagination-card"
              className="flex items-center justify-center rounded-xl border border-slate-200/90 bg-white py-2.5 px-4 shadow-2xs"
            >
              <div className="flex items-center gap-5">
                <button
                  id="btn-text-prev-asset"
                  onClick={handlePrev}
                  disabled={currentAssetIndex <= 0}
                  className="flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                  title="Previous Text Asset"
                  aria-label="Previous Text Asset"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>

                <span className="text-xs font-bold text-slate-700 font-mono tracking-wider tabular-nums">
                  {textAssets.length > 0 ? currentAssetIndex + 1 : 0} / {textAssets.length}
                </span>

                <button
                  id="btn-text-next-asset"
                  onClick={handleNext}
                  disabled={currentAssetIndex >= textAssets.length - 1}
                  className="flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                  title="Next Text Asset"
                  aria-label="Next Text Asset"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Threshold Decision & Automated Quality Audit Card (rendered ONLY when real analysis results exist) */}
            {analysis && (
              <div
                id="text-threshold-decision-card"
                className="rounded-xl border border-slate-200/90 bg-white p-5 shadow-2xs space-y-4"
              >
                {/* Header row */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 bg-transparent ${
                        isPassed ? 'border-emerald-500 text-emerald-600' : 'border-amber-400 text-amber-500'
                      }`}
                    >
                      {isPassed ? <CheckCircle2 className="h-4.5 w-4.5" /> : <AlertCircle className="h-4.5 w-4.5" />}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-xs sm:text-sm font-bold text-slate-900 leading-tight">
                          Threshold Decision & Automated Quality Audit
                        </h3>
                        <span className="px-2 py-0.5 rounded bg-slate-100 border border-slate-200 text-slate-600 text-[10px] font-semibold">
                          {taskTypeLabel}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        Automated pass criteria: overall confidence score ≥ {Math.round(threshold * 100)}%
                      </p>
                    </div>
                  </div>

                  {/* Right Badge */}
                  <div
                    className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-semibold self-start sm:self-auto ${
                      isPassed
                        ? 'border-emerald-300 bg-emerald-50 text-emerald-800'
                        : 'border-amber-400 bg-amber-50/50 text-amber-700'
                    }`}
                  >
                    {isPassed ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
                    ) : (
                      <AlertCircle className="h-3.5 w-3.5 text-amber-600 shrink-0" />
                    )}
                    <span>{isPassed ? 'Passed Threshold' : 'Failed Threshold'}</span>
                  </div>
                </div>

                {/* Inner Banner: Decision & Assign Action */}
                <div
                  className={`rounded-xl border p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 ${
                    isPassed ? 'border-emerald-200 bg-[#F4FBF7]' : 'border-amber-300 bg-[#FFFDF5]'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={`flex h-5 w-5 shrink-0 items-center justify-center mt-0.5 ${
                        isPassed ? 'text-emerald-600' : 'text-amber-500'
                      }`}
                    >
                      {isPassed ? <CheckCircle2 className="h-5 w-5" /> : <AlertCircle className="h-5 w-5" />}
                    </div>
                    <div>
                      <div className={`text-xs sm:text-sm font-bold ${isPassed ? 'text-emerald-950' : 'text-amber-950'}`}>
                        Decision: {requiresHumanReview ? 'Need Human Review' : 'Passed Automated Audit'}
                      </div>
                      <p
                        className={`text-[11.5px] mt-0.5 leading-relaxed max-w-xl ${
                          isPassed ? 'text-emerald-900/80' : 'text-amber-900/80'
                        }`}
                      >
                        {confidenceDecisionText}{' '}
                        {isPassed
                          ? 'Text asset passed automated quality audit.'
                          : 'Text asset failed the threshold and has been marked as Need Human Review.'}
                      </p>
                    </div>
                  </div>

                  {requiresHumanReview && (
                    <button
                      id="btn-assign-hitl"
                      onClick={handleAssignHitl}
                      className={`inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-xs font-bold text-white shadow-xs transition-colors cursor-pointer shrink-0 ${
                        isAssignedToHitl
                          ? 'bg-slate-700 ring-2 ring-slate-400'
                          : 'bg-[#E31837] hover:bg-[#C9142E]'
                      }`}
                    >
                      <UserCheck className="h-4 w-4" />
                      <span>{isAssignedToHitl ? 'Assigned to HITL ✓' : 'Assign to Human Annotator (HITL)'}</span>
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Right Column: AI Prediction Summary & AI Predictions */}
          <div className="xl:col-span-4 space-y-4">
            <TextAISummary mode={activeMode} compact={true} analysis={analysis} />
            <TextAIPredictions
              selectedEntityId={selectedEntityId}
              onSelectEntity={handleSelectEntity}
              analysis={analysis}
            />
          </div>
        </div>
      </main>
    </div>
  );
};
