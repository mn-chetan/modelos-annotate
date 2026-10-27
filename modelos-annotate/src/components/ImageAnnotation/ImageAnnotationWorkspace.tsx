import React, { useState, useEffect } from 'react';
import {
  Menu,
  Crosshair,
  Shield,
  ShieldCheck,
  CheckCircle2,
  Bot,
  ChevronLeft,
  ChevronRight,
  Loader2,
  FileImage,
} from 'lucide-react';
import { AICanvasView, DetectionItem } from './AICanvasView';
import { AIPredictionsPanel, PredictionRow } from './AIPredictionsPanel';
import { api, ProjectResponse, AssetResponse, AnnotationResponse } from '../../services/api';

interface ImageAnnotationWorkspaceProps {
  mode?: 'Object Detection & Labeling' | 'PII Masking' | 'Detection' | 'PII';
  onToggleSidebar?: () => void;
  onNavigateToProjects?: () => void;
  onNavigateToReview?: () => void;
  onToast: (msg: string) => void;
  isQuality?: boolean;
  projectId?: string;
  assetId?: string;
}

const COLOR_PALETTE = ['#0284c7', '#ef4444', '#10b981', '#f97316', '#8b5cf6', '#ec4899', '#0d9488', '#f59e0b'];

export const ImageAnnotationWorkspace: React.FC<ImageAnnotationWorkspaceProps> = ({
  mode = 'Object Detection & Labeling',
  onToggleSidebar,
  onToast,
  isQuality = false,
  projectId: projectIdProp,
  assetId: assetIdProp,
}) => {
  const isPII = mode === 'PII Masking' || mode === 'PII';
  const [selectedDetectionId, setSelectedDetectionId] = useState<string | null>(null);
  const [confidenceScore, setConfidenceScore] = useState<number>(95);
  const [isPassConfirmed, setIsPassConfirmed] = useState<boolean>(false);
  const [currentImageIndex, setCurrentImageIndex] = useState<number>(1);

  // Real backend data states
  const queryParams = new URLSearchParams(window.location.search);
  const requestedProjectId = projectIdProp || queryParams.get('projectId') || '';
  const requestedAssetId = assetIdProp || queryParams.get('assetId') || queryParams.get('taskId') || '';
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>(requestedProjectId);
  const [selectedAssetId, setSelectedAssetId] = useState<string>(requestedAssetId);
  const [assets, setAssets] = useState<AssetResponse[]>([]);
  const [loadedAssetImageUrl, setLoadedAssetImageUrl] = useState<string | undefined>();
  const [annotations, setAnnotations] = useState<AnnotationResponse[]>([]);
  const [isLoadingProjects, setIsLoadingProjects] = useState<boolean>(true);
  const [isLoadingAssets, setIsLoadingAssets] = useState<boolean>(false);
  const [isLoadingAnnotations, setIsLoadingAnnotations] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Load projects list
  useEffect(() => {
    console.debug('[ObjectDetection] project load started', { projectId: requestedProjectId });
    api.getProjects()
      .then((projList) => {
        console.debug('[ObjectDetection] project list loaded', { projectId: requestedProjectId, count: projList.length });
        setProjects(projList);
        const project = requestedProjectId && projList.some((p) => p.id === requestedProjectId)
          ? requestedProjectId
          : projList[0]?.id || '';
        setSelectedProjectId(project);
        if (!project) setLoadError(null);
      })
      .catch((err) => {
        console.error('[ObjectDetection] project API failed', { projectId: requestedProjectId, error: err });
        setProjects([]);
        setSelectedProjectId('');
        setAssets([]);
        setSelectedAssetId('');
        setLoadError('Unable to load projects from the backend.');
      })
      .finally(() => {
        setIsLoadingProjects(false);
        console.debug('[ObjectDetection] loading state', { isLoadingProjects: false });
      });
  }, [requestedProjectId]);

  // Fetch assets when selected project changes
  useEffect(() => {
    if (!selectedProjectId) {
      setAssets([]);
      setSelectedAssetId('');
      setIsLoadingAssets(false);
      return;
    }

    setIsLoadingAssets(true);
    setLoadError(null);
    console.debug('[ObjectDetection] asset list loading', { projectId: selectedProjectId });
    api.getProjectAssets(selectedProjectId, { throwOnError: true })
      .then((assetList) => {
        // Image workflow must never consume text/PDF assets from a shared or legacy project.
        const imageAssets = assetList.filter((asset) => {
          const contentType = String(asset.content_type || '').toLowerCase();
          const filename = String(asset.filename || '').toLowerCase();
          return contentType.startsWith('image/') ||
            /\.(jpg|jpeg|png|webp|bmp|gif|tif|tiff)$/i.test(filename);
        });
        const requestedAsset = requestedAssetId ? imageAssets.find((asset) => asset.id === requestedAssetId) : null;
        const selected = requestedAsset || imageAssets[0] || null;
        console.debug('[ObjectDetection] asset list loaded', {
          projectId: selectedProjectId,
          assetListCount: imageAssets.length,
          ignoredNonImageAssetCount: assetList.length - imageAssets.length,
          selectedAssetId: selected?.id || null,
          selectedAsset: selected,
        });
        setAssets(imageAssets);
        setSelectedAssetId(selected?.id || '');
        setCurrentImageIndex(selected ? imageAssets.findIndex((asset) => asset.id === selected.id) + 1 : 0);
        if (!selected) setLoadError(null);
      })
      .catch((err) => {
        console.error('[ObjectDetection] asset API failed', { projectId: selectedProjectId, error: err });
        setAssets([]);
        setSelectedAssetId('');
        setLoadError('Unable to load assets for this project.');
      })
      .finally(() => {
        setIsLoadingAssets(false);
        console.debug('[ObjectDetection] loading state', { isLoadingAssets: false });
      });
  }, [selectedProjectId, requestedAssetId]);

  const totalImages = assets.length;
  const currentDisplayIndex = assets.length > 0 ? currentImageIndex : 0;
  const currentAsset: AssetResponse | null = selectedAssetId
    ? assets.find((asset) => asset.id === selectedAssetId) || null
    : null;

  const directImageUrl = currentAsset?.id ? api.getAssetImageUrl(currentAsset.id) : undefined;

  useEffect(() => {
    let disposed = false;

    if (!currentAsset?.id) {
      setLoadedAssetImageUrl(undefined);
      return undefined;
    }

    // Immediately supply direct backend URL so UI is never blank
    setLoadedAssetImageUrl(api.getAssetImageUrl(currentAsset.id));

    // Warm up the cached blob URL in background for smooth viewing
    api.getAssetImageBlobUrl(currentAsset.id)
      .then((url) => {
        if (!disposed) {
          setLoadedAssetImageUrl(url);
        }
      })
      .catch((err) => {
        console.warn('[ObjectDetection] asset image blob fetch failed, direct URL fallback active', {
          projectId: selectedProjectId,
          selectedAssetId: currentAsset.id,
          error: err,
        });
      });

    return () => {
      disposed = true;
      // Crucial: do NOT call URL.revokeObjectURL here because the blob is cached in api.imageBlobUrlCache!
    };
  }, [currentAsset?.id, selectedProjectId]);

  const assetImageUrl = loadedAssetImageUrl || directImageUrl;

  // Fetch annotations when current asset changes
  useEffect(() => {
    if (!currentAsset || !currentAsset.id) {
      setAnnotations([]);
      setIsLoadingAnnotations(false);
      return;
    }

    setIsLoadingAnnotations(true);
    console.debug('[ObjectDetection] annotation/result loading', {
      projectId: selectedProjectId,
      selectedAssetId: currentAsset.id,
    });
    api.getAssetAnnotations(currentAsset.id, { throwOnError: true })
      .then((annList) => {
        // Strict verification: ensure annotations belong to current asset
        const verified = annList
          .filter((a) => a.asset_id === currentAsset.id)
          // Human review may clear the editable confidence field. Keep the
          // genuine model score visible by falling back to the persisted
          // original AI score; never substitute the asset-level mean here.
          .map((a) => ({
            ...a,
            confidence: a.confidence ?? a.original_ai_confidence ?? null,
          }));
        console.debug('[ObjectDetection] annotation/result loaded', {
          projectId: selectedProjectId,
          resultAssetId: verified[0]?.asset_id || currentAsset.id,
          resultExecutionId: (verified[0] as any)?.execution_id || null,
          count: verified.length,
          imageUrl: (currentAsset.image_url && window.location.pathname.startsWith('/app1') && currentAsset.image_url.startsWith('/api/v1/') ? `/app1${currentAsset.image_url}` : currentAsset.image_url) || currentAsset.preview_url || `${window.location.pathname.startsWith('/app1') ? '/app1' : ''}/api/v1/assets/${currentAsset.id}/image`,
        });
        setAnnotations(verified);
      })
      .catch((err) => {
        console.error('[ObjectDetection] annotation/result API failed', {
          projectId: selectedProjectId,
          selectedAssetId: currentAsset.id,
          error: err,
        });
        setAnnotations([]);
        setLoadError('Unable to load annotation results for this asset.');
      })
      .finally(() => {
        setIsLoadingAnnotations(false);
        console.debug('[ObjectDetection] loading state', { isLoadingAnnotations: false });
      });
  }, [currentAsset?.id, selectedProjectId]);

  const handlePrevImage = () => {
    if (currentImageIndex > 1) {
      const next = currentImageIndex - 1;
      setCurrentImageIndex(next);
      setSelectedAssetId(assets[next - 1]?.id || '');
      onToast(`Switched to Image ${next} of ${totalImages}`);
    }
  };

  const handleNextImage = () => {
    if (currentImageIndex < totalImages) {
      const next = currentImageIndex + 1;
      setCurrentImageIndex(next);
      setSelectedAssetId(assets[next - 1]?.id || '');
      onToast(`Switched to Image ${next} of ${totalImages}`);
    }
  };

  const handleConfirmPass = () => {
    setIsPassConfirmed(true);
    onToast('Pass confirmed: Image meets threshold and automated quality check (No Review Needed).');
  };

  // Convert real backend annotations to canvas & predictions model format
  const realDetections: DetectionItem[] = annotations.map((ann, idx) => {
    const color = COLOR_PALETTE[idx % COLOR_PALETTE.length];
    return {
      id: ann.id,
      name: ann.label,
      label: ann.label,
      confidence: ann.evidence_confidence ?? ann.confidence ?? ann.original_ai_confidence ?? null,
      color: color,
      box: {
        x: ann.x > 1 ? ann.x : ann.x * 100,
        y: ann.y > 1 ? ann.y : ann.y * 100,
        width: ann.w > 1 ? ann.w : ann.w * 100,
        height: ann.h > 1 ? ann.h : ann.h * 100,
      },
    };
  });

  const realPredictions: PredictionRow[] = annotations.map((ann, idx) => {
    const classColors = ['#00D084', '#00A8FF', '#FFB000', '#FF4D6D', '#A855F7', '#14B8A6', '#F97316', '#EAB308'];
    const classColorMap = new Map<string, string>();
    annotations.forEach((candidate) => {
      const key = (candidate.label || 'object').trim().toLowerCase();
      if (!classColorMap.has(key)) classColorMap.set(key, classColors[classColorMap.size % classColors.length]);
    });
    const color = classColorMap.get((ann.label || 'object').trim().toLowerCase()) || COLOR_PALETTE[idx % COLOR_PALETTE.length];
    return {
      id: ann.id,
      objectName: ann.label,
      label: ann.label,
      confidence: ann.evidence_confidence ?? ann.confidence ?? ann.original_ai_confidence ?? null,
      dotColor: color,
      barColor: 'bg-emerald-500',
    };
  });

  const handleSelectDetection = (id: string) => {
    setSelectedDetectionId(id);
    const found = realPredictions.find((p) => p.id === id);
    onToast(`Selected ${found ? found.objectName : id}`);
  };

  // Metadata calculations
  const activeProject = projects.find((p) => p.id === selectedProjectId);

  const processingTime = currentAsset?.duration ? `${currentAsset.duration} seconds` : 'N/A';

  const annotationConfidences = annotations
    .map((a) => a.evidence_confidence ?? a.confidence ?? a.original_ai_confidence ?? null)
    .filter((value): value is number => value != null && Number.isFinite(value));
  const calculatedMeanConf = annotationConfidences.length > 0
    ? annotationConfidences.reduce((sum, value) => sum + value, 0) / annotationConfidences.length
    : currentAsset && currentAsset.mean_confidence != null && currentAsset.mean_confidence > 0
    ? currentAsset.mean_confidence
    : null;

  return (
    <div id="image-annotation-workspace" className="flex-1 flex flex-col min-w-0 overflow-y-auto bg-[#F6F8FB]">
      {/* Mobile Top Bar */}
      {onToggleSidebar && (
        <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-slate-200 lg:hidden">
          <button
            id="toggle-sidebar-workspace-btn"
            onClick={onToggleSidebar}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 cursor-pointer"
            aria-label="Toggle navigation"
          >
            <Menu className="h-5 w-5" />
          </button>
          <span className="text-xs font-bold text-slate-800">
            {isPII ? 'PII Masking' : 'Object Detection & Labeling'}
          </span>
          <div className="w-5" />
        </div>
      )}

      {/* Main Workspace Body */}
      <main className="flex-1 p-3 sm:p-5 lg:p-6 space-y-4 max-w-[1700px] w-full mx-auto">
        {/* UI Header for Object Detection & Labeling / PII Masking */}
        <div className="flex flex-wrap items-center justify-between gap-3.5">
          <div className="flex items-center gap-3.5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-blue-200 bg-blue-50 text-blue-600 shadow-2xs">
              {isPII ? <Shield className="h-5 w-5" /> : <Crosshair className="h-5 w-5" />}
            </div>
            <div>
              <h1 className="text-xl font-extrabold tracking-tight text-slate-900">
                {isPII ? 'PII Masking' : 'Object Detection & Labeling'}
              </h1>
              <p className="text-xs text-slate-500">
                {isPII
                  ? 'View AI privacy redactions, confidence scores, and sensitive information bounding masks for this asset.'
                  : 'View persisted object annotations, confidence scores, and bounding boxes for this asset.'}
              </p>
            </div>
          </div>

          {/* Project Selector dropdown if multiple projects exist */}
          {projects.length > 0 && (
            <div className="flex items-center gap-2 bg-white px-3 py-1.5 rounded-xl border border-slate-200 shadow-2xs text-xs font-semibold">
              <span className="text-slate-500">Active Project:</span>
              <select
                value={selectedProjectId}
                onChange={(e) => {
                  setSelectedProjectId(e.target.value);
                  onToast?.(`Loaded assets for ${projects.find((p) => p.id === e.target.value)?.name || e.target.value}`);
                }}
                className="bg-transparent text-slate-900 font-bold border-none focus:ring-0 text-xs cursor-pointer"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Loading Indicator */}
        {(isLoadingProjects || isLoadingAssets || isLoadingAnnotations) && (
          <div className="flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-xl p-3 text-xs text-blue-700 font-semibold">
            <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
            <span>Loading asset & annotation data from backend...</span>
          </div>
        )}

        {loadError && !isLoadingProjects && !isLoadingAssets && !isLoadingAnnotations && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">
            {loadError}
          </div>
        )}

        {/* Asset Metadata Bar */}
        <div
          id="asset-metadata-bar"
          className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white p-3.5 shadow-2xs"
        >
          <div className="flex items-center gap-3">
            <div className="h-12 w-12 overflow-hidden rounded-lg border border-slate-200 bg-slate-950 shrink-0 flex items-center justify-center shadow-2xs">
              {assetImageUrl ? (
                <img
                  src={assetImageUrl}
                  alt="Asset Preview"
                  referrerPolicy="no-referrer"
                  className="h-full w-full object-cover"
                />
              ) : (
                <FileImage className="h-5 w-5 text-slate-400" />
              )}
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                Task ID:
              </span>
              <h2 className="text-xs font-bold text-slate-900 font-mono">
                {currentAsset ? currentAsset.filename || currentAsset.id : 'No Asset Selected'}
              </h2>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-6 text-xs divide-x divide-slate-100">
            <div>
              <span className="block text-[11px] text-slate-400">Project</span>
              <span className="font-semibold text-slate-800">{activeProject?.name || 'Urban Traffic Monitoring'}</span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] text-slate-400">Modality</span>
              <span className="font-semibold text-slate-800">Image</span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] text-slate-400">Image Size</span>
              <span className="font-semibold text-slate-800">
                {currentAsset?.byte_size ? `${(currentAsset.byte_size / (1024 * 1024)).toFixed(1)} MB` : 'N/A'}
              </span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] text-slate-400">Resolution</span>
              <span className="font-semibold text-slate-800">
                {currentAsset?.width && currentAsset?.height ? `${currentAsset.width} × ${currentAsset.height} px` : 'N/A'}
              </span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] text-slate-400">Format</span>
              <span className="font-semibold text-slate-800">
                {currentAsset?.filename ? currentAsset.filename.split('.').pop()?.toUpperCase() || 'JPEG' : 'N/A'}
              </span>
            </div>
          </div>
        </div>

        {/* 2-Column Layout */}
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-5 items-start">
          {/* Left Column: Interactive Canvas */}
          <div className="xl:col-span-8 space-y-4">
            {/* Top Interactive Canvas Card */}
            <AICanvasView
              mode={isPII ? 'PII' : 'Detection'}
              imageIndex={currentDisplayIndex}
              onToast={onToast}
              selectedId={selectedDetectionId}
              onSelect={handleSelectDetection}
              detections={realDetections}
              imageUrl={assetImageUrl}
              fallbackUrl={directImageUrl}
              assetId={currentAsset?.id}
              isLoading={isLoadingAssets}
              onRetry={() => {
                if (currentAsset?.id) {
                  api.invalidateAssetImage(currentAsset.id);
                  setLoadedAssetImageUrl(api.getAssetImageUrl(currentAsset.id));
                }
              }}
            />

            {/* Scroll Image Option below the image */}
            <div
              id="image-scroll-navigator-card"
              className="rounded-xl border border-slate-200 bg-white py-2 px-4 shadow-2xs flex items-center justify-center gap-3.5"
            >
              <button
                id="btn-scroll-image-prev"
                type="button"
                onClick={handlePrevImage}
                disabled={currentImageIndex <= 1 || totalImages === 0}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-900 shadow-2xs transition disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                title="Previous Image"
                aria-label="Previous Image"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>

              <span className="text-xs sm:text-sm font-bold text-slate-700 font-mono tracking-wider select-none px-2">
                {currentDisplayIndex} / {totalImages}
              </span>

              <button
                id="btn-scroll-image-next"
                type="button"
                onClick={handleNextImage}
                disabled={currentImageIndex >= totalImages || totalImages === 0}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-900 shadow-2xs transition disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                title="Next Image"
                aria-label="Next Image"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>

          </div>

          {/* Right Column: AI Prediction Summary & AI Predictions */}
          <div className="xl:col-span-4">
            <AIPredictionsPanel
              mode={isPII ? 'PII' : 'Detection'}
              selectedId={selectedDetectionId}
              onSelect={handleSelectDetection}
              isQuality={isQuality}
              onToast={onToast}
              confidenceScore={confidenceScore}
              onConfidenceChange={(newScore) => {
                setConfidenceScore(newScore);
              }}
              predictions={realPredictions}
              processingTime={processingTime}
              objectsDetected={annotations.length}
              overallConfidence={calculatedMeanConf}
            />
          </div>
        </div>
      </main>
    </div>
  );
};
