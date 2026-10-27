import React, { useState, useRef, useEffect } from 'react';
import {
  Image as ImageIcon,
  Square,
  Hexagon,
  Paintbrush,
  Crosshair,
  CircleDot,
  Waypoints,
  Eraser,
  Trash2,
  Undo2,
  Redo2,
  Maximize2,
  Minimize2,
  Minus,
  Plus,
  Search,
  Eye,
  EyeOff,
  MoreVertical,
  ChevronRight,
  ChevronLeft,
  ChevronDown,
  Edit3,
  Copy,
  GitMerge,
  Save,
  Send,
  SlidersHorizontal,
  Check,
  Menu,
  ArrowUp,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  Maximize,
  Minimize,
  Grid,
  User,
  UserCheck,
  ZoomIn,
  ZoomOut,
  Bot,
  Sparkles,
  ImageOff,
  Loader2,
  ShieldCheck,
  RefreshCw,
} from 'lucide-react';
import {
  api,
  ProjectResponse,
  AssetResponse,
  AnnotationResponse,
} from '../../services/api';

export interface BoundingBoxAnnotation {
  id: string;
  asset_id?: string;
  label: string;
  category: string;
  confidence: number | null;
  color: string;
  borderColor: string;
  bgColor: string;
  source?: string;
  box: {
    x: number; // percentage from left
    y: number; // percentage from top
    width: number; // percentage
    height: number; // percentage
  };
  points?: Array<{ x: number; y: number }>;
  geometryType?: 'box' | 'polygon' | 'polyline' | 'point';
}

interface HitlObjectDetectionWorkspaceProps {
  mode?: 'Detection' | 'PII';
  onToggleSidebar?: () => void;
  onToast: (message: string) => void;
  currentUserEmail?: string;
}

const SWATCH_COLORS = [
  { name: 'Blue', hex: '#2563eb' },
  { name: 'Green', hex: '#16a34a' },
  { name: 'Yellow', hex: '#f59e0b' },
  { name: 'Orange', hex: '#f97316' },
  { name: 'Red', hex: '#ef4444' },
  { name: 'Purple', hex: '#9333ea' },
  { name: 'Cyan', hex: '#06b6d4' },
];

const categoryColorMap: Record<string, string> = {};
const getCategoryColor = (category: string, index: number) => {
  if (!categoryColorMap[category]) {
    categoryColorMap[category] = SWATCH_COLORS[index % SWATCH_COLORS.length].hex;
  }
  return categoryColorMap[category];
};

export const HitlObjectDetectionWorkspace: React.FC<HitlObjectDetectionWorkspaceProps> = ({
  mode = 'Detection',
  onToggleSidebar,
  onToast,
  currentUserEmail,
}) => {
  const isPII = mode === 'PII';

  // Backend Data State
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [assets, setAssets] = useState<AssetResponse[]>([]);
  const [humanTasks, setHumanTasks] = useState<Array<{
    id?: string;
    asset_id?: string;
    status?: string;
    audit_source?: string | null;
    revisions?: Array<{ status?: string; source?: string }>;
  }>>([]);
  const [currentAssetIndex, setCurrentAssetIndex] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [imageError, setImageError] = useState<boolean>(false);
  const [loadedAssetImageUrl, setLoadedAssetImageUrl] = useState<string | undefined>();

  // Tool & Canvas State
  const [activeTool, setActiveTool] = useState<
    '2D Box' | 'Polygon' | 'Keypoints' | 'Polylines' | 'Brush' | 'Point' | 'Erase'
  >('2D Box');
  const [selectedColor, setSelectedColor] = useState<string>('');
  const [polygonDraft, setPolygonDraft] = useState<Array<{ x: number; y: number }>>([]);
  const [polylineDraft, setPolylineDraft] = useState<Array<{ x: number; y: number }>>([]);
  const [selectedLabel, setSelectedLabel] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedBoxId, setSelectedBoxId] = useState<string | null>(null);
  const [zoomLevel, setZoomLevel] = useState<number>(100);
  const [annotations, setAnnotations] = useState<BoundingBoxAnnotation[]>([]);
  const [persistedAnnotationIds, setPersistedAnnotationIds] = useState<Set<string>>(new Set());
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [isPersisting, setIsPersisting] = useState(false);
  const [persistingAction, setPersistingAction] = useState<'save' | 'submit' | null>(null);
  const [persistenceMessage, setPersistenceMessage] = useState('');
  const persistenceLockRef = useRef(false);
  const [submittedAssetIds, setSubmittedAssetIds] = useState<Set<string>>(new Set());
  const [hiddenClasses, setHiddenClasses] = useState<Record<string, boolean>>({});

  const selectAnnotationTool = (tool: '2D Box' | 'Polygon' | 'Keypoints' | 'Polylines', label: string) => {
    setActiveTool(tool);
    if (tool !== 'Polygon') setPolygonDraft([]);
    if (tool !== 'Polylines') setPolylineDraft([]);
    onToast(`Tool: ${label} active`);
  };

  // History for Undo & Redo
  const [undoStack, setUndoStack] = useState<BoundingBoxAnnotation[][]>([]);
  const [redoStack, setRedoStack] = useState<BoundingBoxAnnotation[][]>([]);

  // Interactive View Modes
  const [showGrid, setShowGrid] = useState<boolean>(false);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);

  // Quick Action Editing Modes
  const [isEditingLabel, setIsEditingLabel] = useState<boolean>(false);
  const [customLabelText, setCustomLabelText] = useState<string>('');
  const [isEditingBoxCoords, setIsEditingBoxCoords] = useState<boolean>(false);

  // Canvas drawing state
  const canvasRef = useRef<HTMLDivElement>(null);
  const [isDrawing, setIsDrawing] = useState<boolean>(false);
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null);
  const [drawCurrent, setDrawCurrent] = useState<{ x: number; y: number } | null>(null);

  // 1. Fetch Projects & Assets from Backend
  useEffect(() => {
    let isMounted = true;
    const fetchData = async () => {
      setIsLoading(true);
      try {
        const projList = await api.getProjects();
        if (!isMounted) return;
        const requestedProjectId = new URLSearchParams(window.location.search).get('projectId') || '';
        const activeProjId = requestedProjectId && projList.some((project) => project.id === requestedProjectId)
          ? requestedProjectId
          : (projList.length > 0 ? projList[0].id : '');

        // The list endpoint may only contain project summaries. Merge the
        // selected project's full ontology so HITL label choices are not
        // reduced to labels found in the current AI predictions.
        let projectsWithDetails = projList;
        if (activeProjId) {
          const detail = await api.getProjectDetail(activeProjId);
          if (detail) {
            projectsWithDetails = projList.map((project) =>
              project.id === activeProjId ? { ...project, ...detail } : project
            );
          }
        }
        setProjects(projectsWithDetails);

        setSelectedProjectId(activeProjId);

        if (activeProjId) {
          const assetList = await api.getProjectAssets(activeProjId);
          if (!isMounted) return;
          // This workspace renders an image canvas. Text/document assets may
          // belong to the same legacy project, but they are not valid HITL
          // image tasks and must never be selected here.
          const imageAssets = assetList.filter((asset) => {
            const contentType = String(asset.content_type || '').toLowerCase();
            const filename = String(asset.filename || '').toLowerCase();
            return contentType.startsWith('image/') ||
              /\.(jpg|jpeg|png|webp|bmp|gif|tif|tiff)$/i.test(filename);
          });
          setAssets(imageAssets);
          setCurrentAssetIndex(0);
        } else {
          setAssets([]);
        }
      } catch (err) {
        console.error('Error fetching HITL assets:', err);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    fetchData();
    return () => {
      isMounted = false;
    };
  }, []);

  // Keep the card backed by the persisted Human Annotator task lifecycle.
  // Polling also reflects start, edits, QC submission, completion, and the
  // next-task transition without changing the existing HITL workflow.
  useEffect(() => {
    if (!selectedProjectId) {
      setHumanTasks([]);
      return;
    }

    let isMounted = true;
    const refreshHumanTasks = async () => {
      try {
        const tasks = await api.getHumanAnnotatorTasks(selectedProjectId);
        if (isMounted) setHumanTasks(tasks);
      } catch (err) {
        console.error('Error fetching Human Annotator tasks:', err);
      }
    };

    void refreshHumanTasks();
    const refreshTimer = window.setInterval(() => {
      void refreshHumanTasks();
    }, 5000);

    return () => {
      isMounted = false;
      window.clearInterval(refreshTimer);
    };
  }, [selectedProjectId]);

  const currentAsset = assets[currentAssetIndex] || null;
  const currentProject = projects.find((p) => p.id === selectedProjectId) || null;
  const directImageUrl = currentAsset?.id ? api.getAssetImageUrl(currentAsset.id) : undefined;
  const assetImageUrl = loadedAssetImageUrl || directImageUrl;

  const switchAsset = (nextIndex: number) => {
    if (assets.length === 0) {
      onToast('No uploaded image assets available');
      return;
    }
    const normalizedIndex = (nextIndex + assets.length) % assets.length;
    setCurrentAssetIndex(normalizedIndex);
    setSelectedBoxId(null);
    setUndoStack([]);
    setRedoStack([]);
    // Ensure no lingering submission/save message or persisting state from previous asset leaks over
    setPersistenceMessage('');
    setPersistingAction(null);
    setIsPersisting(false);
    persistenceLockRef.current = false;
    onToast(`Switched to image ${normalizedIndex + 1} of ${assets.length}`);

    // Prefetch next image and annotations in background for 0ms navigation
    const nextIdx = (normalizedIndex + 1) % assets.length;
    if (assets[nextIdx]?.id) {
      void api.getAssetImageBlobUrl(assets[nextIdx].id).catch(() => {});
      void api.getAssetAnnotations(assets[nextIdx].id).catch(() => {});
    }
  };

  // Load the image through the authenticated asset endpoint with direct fallback
  useEffect(() => {
    let disposed = false;
    setImageError(false);

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
      .catch((error) => {
        if (!disposed) {
          console.warn('HITL asset blob fetch failed, falling back to direct URL:', {
            projectId: selectedProjectId,
            assetId: currentAsset.id,
            error,
          });
        }
      });

    return () => {
      disposed = true;
      // Crucial: do NOT call URL.revokeObjectURL here because the blob is cached in api.imageBlobUrlCache!
    };
  }, [currentAsset?.id, selectedProjectId]);

  // 2. Fetch Annotations for Current Asset
  useEffect(() => {
    let isMounted = true;
    setImageError(false);
    setSelectedBoxId(null);
    setSelectedColor('');
    setSelectedLabel('');
    // Do not keep the previous asset's boxes visible while the next asset is loading.
    // Otherwise the old predictions are briefly rendered over the new image and look
    // like the detector produced identical boxes for different images.
    setAnnotations([]);

    if (!currentAsset) {
      return;
    }

    const assetId = currentAsset.id;
    const fetchAnnotations = async () => {
      try {
        const rawAnns = await api.getAssetAnnotations(assetId);
        if (!isMounted) return;

        const mapped: BoundingBoxAnnotation[] = rawAnns
          .filter((ann) => String(ann.asset_id) === String(assetId))
          .map((ann, idx) => {
            const xPct = ann.x <= 1 ? ann.x * 100 : ann.x;
            const yPct = ann.y <= 1 ? ann.y * 100 : ann.y;
            const wPct = ann.w <= 1 ? ann.w * 100 : ann.w;
            const hPct = ann.h <= 1 ? ann.h * 100 : ann.h;

            const category = ann.label || 'Unclassified';
            const color = getCategoryColor(category, idx);
            const effectiveConfidence = ann.confidence ?? ann.original_ai_confidence ?? null;
            const confDisplay = effectiveConfidence != null ? ` ${(effectiveConfidence).toFixed(2)}` : '';
            const labelStr = `${category}${confDisplay}`;

            return {
              id: ann.id,
              asset_id: ann.asset_id,
              label: labelStr,
              category,
              confidence: effectiveConfidence,
              color,
              borderColor: 'border-blue-500',
              bgColor: 'bg-blue-600',
              source: ann.source,
              geometryType: ann.geometry_type === 'point' ? 'point' : ann.geometry_type === 'polygon' ? 'polygon' : ann.geometry_type === 'polyline' ? 'polyline' : 'box',
              box: {
                x: Math.max(0, Math.min(100, xPct)),
                y: Math.max(0, Math.min(100, yPct)),
                width: Math.max(0, Math.min(100, wPct)),
                height: Math.max(0, Math.min(100, hPct)),
              },
              points: Array.isArray(ann.polygon)
                ? ann.polygon.map(([px, py]) => ({
                    x: px <= 1 ? px * 100 : px,
                    y: py <= 1 ? py * 100 : py,
                  }))
                : undefined,
            };
          });

        setAnnotations(mapped);
        setPersistedAnnotationIds(new Set(mapped.map((annotation) => annotation.id)));
        setHasUnsavedChanges(false);
      } catch (err) {
        console.error('Error fetching annotations:', err);
        if (isMounted) setAnnotations([]);
      }
    };

    fetchAnnotations();
    return () => {
      isMounted = false;
    };
  }, [currentAsset?.id]);

  // Derived Values from Backend Data
  const taskId = currentAsset ? currentAsset.filename || currentAsset.id : 'N/A';
  const projectName = currentProject?.name || 'N/A';
  const modality = 'Image';
  const imageSize = currentAsset?.byte_size
    ? `${(currentAsset.byte_size / (1024 * 1024)).toFixed(1)} MB`
    : 'N/A';
  const resolution =
    currentAsset?.width && currentAsset?.height
      ? `${currentAsset.width} × ${currentAsset.height} px`
      : 'N/A';
  const format = currentAsset?.filename
    ? currentAsset.filename.split('.').pop()?.toUpperCase() || 'N/A'
    : currentAsset?.content_type
    ? currentAsset.content_type.split('/')[1]?.toUpperCase() || 'N/A'
    : 'N/A';

  const fallbackEmail = currentUserEmail || '';
  const fallbackName = fallbackEmail.includes('@')
    ? fallbackEmail
        .split('@')[0]
        .split(/[._-]+/)
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ')
    : (fallbackEmail || 'Human Annotator');

  const annotatorName =
    (currentAsset as any)?.assigned_to ||
    (currentAsset as any)?.reviewer ||
    fallbackName;

  const rawEmpNo = (currentAsset as any)?.assigned_emp_no;
  const empNo = rawEmpNo && rawEmpNo !== 'N/A'
    ? rawEmpNo
    : (currentUserEmail && currentUserEmail.includes('@')
        ? currentUserEmail.split('@')[0]
        : null);

  const role = (currentAsset as any)?.assigned_role || 'Human Annotator';

  const isAssetSubmitted = (assetId?: string) => {
    if (!assetId) return false;
    if (submittedAssetIds.has(assetId)) return true;
    const a = assets.find((x) => x.id === assetId);
    const status = String(a?.review_status || (a as any)?.qc_status || (a as any)?.workflow_status || (a as any)?.status || '').toLowerCase();
    return [
      'submitted_for_qc',
      'quality_audit_required',
      'qc_pending',
      'final_approved',
      'approved',
    ].includes(status);
  };
  const isCurrentAssetSubmitted = isAssetSubmitted(currentAsset?.id);

  const humanReviewedCount = humanTasks.filter((task) => {
    const status = String(task.status || '').toLowerCase();
    const auditSource = String(task.audit_source || '').toUpperCase();
    const hasHumanRevision = (task.revisions || []).some((revision) =>
      String(revision.source || '').toUpperCase() === 'HUMAN' ||
      String(revision.source || '').toUpperCase() === 'HUMAN_MODIFIED'
    );

    // Direct completion status, or a later QC/final state that explicitly
    // records a Human Annotator revision. AI-only completion is excluded.
    if (status === 'human_review_completed') return true;
    if (['quality_audit_required', 'human_rework_required', 'final_approved'].includes(status)) {
      return auditSource === 'HUMAN_REVIEW' || hasHumanRevision;
    }
    return false;
  }).length;

  const totalAssignedTasks = assets.length;
  const reviewedFromAssets = assets.filter((asset) => {
    if (submittedAssetIds.has(asset.id)) return true;
    const status = String(asset.review_status || asset.status || (asset as any)?.qc_status || '').toLowerCase();
    return [
      'human_review_completed',
      'submitted_for_qc',
      'quality_audit_required',
      'final_approved',
      'approved',
      'qc_pending',
    ].includes(status);
  }).length;
  const effectiveHumanReviewed = Math.max(humanReviewedCount, reviewedFromAssets);
  const pendingTasksCount = Math.max(0, totalAssignedTasks - effectiveHumanReviewed);

  const configuredClasses = [
    ...((currentProject as any)?.target_classes || []).map((c: any) => typeof c === 'string' ? c : c.name),
    ...((currentProject?.labels || [])),
    ...((currentProject?.label_ontology || []).map((c) => c.name)),
  ].filter((label): label is string => Boolean(label && label.trim()));
  const detectedClasses = annotations.map((annotation) => annotation.category || annotation.label).filter(Boolean);
  const availableClasses = Array.from(new Set([
    ...configuredClasses,
    ...detectedClasses,
    ...(selectedLabel ? [selectedLabel] : []),
  ])).filter((label): label is string => Boolean(label && label.trim()));
  const groupedPredictionRows = Array.from(
    annotations.reduce((groups, annotation) => {
      const objectType = annotation.category || annotation.label || 'Unknown';
      const existing = groups.get(objectType);
      if (existing) {
        existing.count += 1;
        if (annotation.confidence != null) {
          existing.confidences.push(annotation.confidence);
        }
      } else {
        groups.set(objectType, {
          objectType,
          firstAnnotationId: annotation.id,
          color: annotation.color,
          count: 1,
          confidences: annotation.confidence != null ? [annotation.confidence] : [],
        });
      }
      return groups;
    }, new Map<string, {
      objectType: string;
      firstAnnotationId: string;
      color: string;
      count: number;
      confidences: number[];
    }>()).values()
  );

  // Helper to commit changes to state and push to undo history
  const commitAnnotations = (newAnnotations: BoundingBoxAnnotation[]) => {
    setUndoStack((prev) => [...prev, annotations]);
    setRedoStack([]);
    setAnnotations(newAnnotations);
    setHasUnsavedChanges(true);
  };

  const handleUndo = () => {
    if (undoStack.length === 0) {
      onToast('Nothing to undo');
      return;
    }
    const previous = undoStack[undoStack.length - 1];
    setUndoStack((prev) => prev.slice(0, -1));
    setRedoStack((prev) => [...prev, annotations]);
    setAnnotations(previous);
    onToast('Reverted previous action');
  };

  const handleRedo = () => {
    if (redoStack.length === 0) {
      onToast('Nothing to redo');
      return;
    }
    const next = redoStack[redoStack.length - 1];
    setRedoStack((prev) => prev.slice(0, -1));
    setUndoStack((prev) => [...prev, annotations]);
    setAnnotations(next);
    onToast('Re-applied action');
  };

  const handleSelectBox = (id: string) => {
    if (activeTool === 'Erase') {
      commitAnnotations(annotations.filter((a) => a.id !== id));
      onToast('Erased annotation');
      if (selectedBoxId === id) {
        setSelectedBoxId(null);
        setSelectedColor('');
        setSelectedLabel('');
      }
      return;
    }

    setSelectedBoxId(id);
    const box = annotations.find((a) => a.id === id);
    if (box) {
      setSelectedLabel(box.category);
      setSelectedColor(box.color);
      setCustomLabelText(box.label);
      onToast(`Selected: ${box.label}`);
    }
  };

  const handleChangeSelectedColor = (newHex: string) => {
    setSelectedColor(newHex);
    if (newHex && selectedBoxId) {
      const updated = annotations.map((a) =>
        a.id === selectedBoxId ? { ...a, color: newHex } : a
      );
      commitAnnotations(updated);
      onToast('Updated annotation color');
    } else if (newHex) {
      onToast('Color selected for new annotations');
    }
  };

  const handleChangeSelectedLabel = (newLabel: string) => {
    setSelectedLabel(newLabel);
    if (newLabel && selectedBoxId) {
      const updated = annotations.map((a) => {
        if (a.id === selectedBoxId) {
          const conf = a.confidence != null ? ` ${(a.confidence).toFixed(2)}` : '';
          return {
            ...a,
            category: newLabel,
            label: `${newLabel}${conf}`,
          };
        }
        return a;
      });
      commitAnnotations(updated);
      onToast(`Re-classified selected box to ${newLabel}`);
    } else if (newLabel) {
      onToast(`Active class set to ${newLabel}`);
    }
  };

  const handleDeleteSelected = () => {
    if (!selectedBoxId) {
      onToast('Select a bounding box to delete');
      return;
    }
    commitAnnotations(annotations.filter((a) => a.id !== selectedBoxId));
    onToast(`Deleted selected annotation`);
    setSelectedBoxId(null);
    setSelectedColor('');
    setSelectedLabel('');
  };

  const handleDuplicateSelected = () => {
    if (!selectedBoxId) {
      onToast('Select a bounding box to duplicate');
      return;
    }
    const current = annotations.find((a) => a.id === selectedBoxId);
    if (!current) return;
    const newBox: BoundingBoxAnnotation = {
      ...current,
      id: `box-${Date.now()}`,
      box: {
        ...current.box,
        x: Math.min(current.box.x + 3.5, 88),
        y: Math.min(current.box.y + 3.5, 88),
      },
    };
    commitAnnotations([...annotations, newBox]);
    setSelectedBoxId(newBox.id);
    onToast(`Duplicated ${current.category} bounding box`);
  };

  const handleSaveEditedLabel = () => {
    if (!selectedBoxId || !customLabelText.trim()) {
      setIsEditingLabel(false);
      return;
    }
    const cleanLabel = customLabelText.trim();
    // Parse out any trailing confidence score e.g. "car 0.95" -> category "car"
    const categoryName = cleanLabel.replace(/\s+[0-9]*\.?[0-9]+$/, '').trim() || cleanLabel;
    const updated = annotations.map((a) =>
      a.id === selectedBoxId ? { ...a, label: cleanLabel, category: categoryName } : a
    );
    commitAnnotations(updated);
    setSelectedLabel(categoryName);
    setIsEditingLabel(false);
    onToast(`Label updated to "${cleanLabel}"`);
  };

  const handleNudgeBox = (dx: number, dy: number, dw: number, dh: number) => {
    if (!selectedBoxId) return;
    const updated = annotations.map((a) => {
      if (a.id === selectedBoxId) {
        return {
          ...a,
          box: {
            x: Math.max(0, Math.min(95, a.box.x + dx)),
            y: Math.max(0, Math.min(95, a.box.y + dy)),
            width: Math.max(2, Math.min(90, a.box.width + dw)),
            height: Math.max(2, Math.min(90, a.box.height + dh)),
          },
        };
      }
      return a;
    });
    commitAnnotations(updated);
  };

  const handleMergeBoxes = () => {
    if (!selectedBoxId) {
      onToast('Select an initial bounding box to merge');
      return;
    }
    const b1 = annotations.find((a) => a.id === selectedBoxId);
    if (!b1) return;

    const others = annotations.filter((a) => a.id !== selectedBoxId);
    if (others.length === 0) {
      onToast('No other bounding boxes available to merge with');
      return;
    }

    const sameCategory = others.filter((a) => a.category === b1.category);
    const candidate = sameCategory.length > 0 ? sameCategory[0] : others[0];

    const minX = Math.min(b1.box.x, candidate.box.x);
    const minY = Math.min(b1.box.y, candidate.box.y);
    const maxX = Math.max(b1.box.x + b1.box.width, candidate.box.x + candidate.box.width);
    const maxY = Math.max(b1.box.y + b1.box.height, candidate.box.y + candidate.box.height);

    const mergedBox: BoundingBoxAnnotation = {
      ...b1,
      id: `box-merged-${Date.now()}`,
      label: `${b1.category} (merged)`,
      box: {
        x: Math.max(0, minX),
        y: Math.max(0, minY),
        width: Math.min(100 - minX, maxX - minX),
        height: Math.min(100 - minY, maxY - minY),
      },
    };

    const remaining = annotations.filter((a) => a.id !== b1.id && a.id !== candidate.id);
    commitAnnotations([...remaining, mergedBox]);
    setSelectedBoxId(mergedBox.id);
    onToast(`Merged ${b1.category} bounding boxes`);
  };

  // Canvas Mouse Event Handlers for Interactive Drawing
  const handleCanvasMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!canvasRef.current || !currentAsset || !assetImageUrl || imageError) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));
    const y = Math.max(0, Math.min(100, ((e.clientY - rect.top) / rect.height) * 100));

    if (activeTool === 'Keypoints' || activeTool === 'Point') {
      const effectiveCategory = selectedLabel || (availableClasses[0] || 'Unclassified');
      const effectiveColor = selectedColor || getCategoryColor(effectiveCategory, 0);
      const newPoint: BoundingBoxAnnotation = {
        id: `point-${Date.now()}`,
        asset_id: currentAsset.id,
        label: `${effectiveCategory} kp`,
        category: effectiveCategory,
        confidence: null,
        color: effectiveColor,
        borderColor: 'border-white',
        bgColor: 'bg-blue-600',
        source: 'human',
        geometryType: 'point',
        box: { x: Math.max(0, x - 1.2), y: Math.max(0, y - 1.2), width: 2.4, height: 2.4 },
      };
      commitAnnotations([...annotations, newPoint]);
      setSelectedBoxId(newPoint.id);
      setSelectedLabel(effectiveCategory);
      setSelectedColor(effectiveColor);
      onToast(`Created keypoint for ${effectiveCategory}`);
      return;
    }

    if (activeTool === 'Polygon') {
      setPolygonDraft((current) => [...current, { x, y }]);
      return;
    }

    if (activeTool === 'Polylines') {
      setPolylineDraft((current) => [...current, { x, y }]);
      return;
    }

    if (
      activeTool === '2D Box' ||
      activeTool === 'Polygon' ||
      activeTool === 'Polylines' ||
      activeTool === 'Brush'
    ) {
      setIsDrawing(true);
      setDrawStart({ x, y });
      setDrawCurrent({ x, y });
    } else {
      setSelectedBoxId(null);
      setSelectedColor('');
      setSelectedLabel('');
    }
  };

  const handleCanvasDoubleClick = () => {
    const isPolygon = activeTool === 'Polygon';
    const rawDraft = isPolygon ? polygonDraft : polylineDraft;
    const draft = rawDraft.filter((point, index) => {
      if (index === 0) return true;
      const previous = rawDraft[index - 1];
      return Math.abs(point.x - previous.x) > 0.5 || Math.abs(point.y - previous.y) > 0.5;
    });
    const minimumPoints = isPolygon ? 3 : 2;
    if (!['Polygon', 'Polylines'].includes(activeTool) || draft.length < minimumPoints || !currentAsset) return;
    const xs = draft.map((point) => point.x);
    const ys = draft.map((point) => point.y);
    const effectiveCategory = selectedLabel || (availableClasses[0] || 'New Object');
    const effectiveColor = selectedColor || getCategoryColor(effectiveCategory, 0);
    const lineAnnotation: BoundingBoxAnnotation = {
      id: `${isPolygon ? 'polygon' : 'polyline'}-${Date.now()}`,
      asset_id: currentAsset.id,
      label: effectiveCategory,
      category: effectiveCategory,
      confidence: null,
      color: effectiveColor,
      borderColor: 'border-blue-500',
      bgColor: 'bg-blue-600',
      source: 'human',
      points: draft,
      geometryType: isPolygon ? 'polygon' : 'polyline',
      box: {
        x: Math.min(...xs),
        y: Math.min(...ys),
        width: Math.max(...xs) - Math.min(...xs),
        height: Math.max(...ys) - Math.min(...ys),
      },
    };
    commitAnnotations([...annotations, lineAnnotation]);
    setSelectedBoxId(lineAnnotation.id);
    setSelectedLabel(effectiveCategory);
    setSelectedColor(effectiveColor);
    setPolygonDraft([]);
    setPolylineDraft([]);
    onToast(`Added ${isPolygon ? 'polygon' : 'polyline'} for ${effectiveCategory}`);
  };

  const formatAnnotationsForBackend = (anns: BoundingBoxAnnotation[]) => {
    return anns.map((annotation) => {
      const geometryType = annotation.geometryType || (annotation.points ? 'polygon' : 'box');
      const geometry = annotation.geometryType === 'point'
        ? {
            points: [[
              annotation.box.x + annotation.box.width / 2,
              annotation.box.y + annotation.box.height / 2,
            ]],
          }
        : annotation.points
        ? { points: annotation.points.map((point) => [point.x, point.y]) }
        : { x: annotation.box.x, y: annotation.box.y, width: annotation.box.width, height: annotation.box.height };
      const effectiveLabel = (annotation.category || annotation.label || 'object').trim();
      return {
        id: annotation.id,
        label: effectiveLabel,
        geometry_type: geometryType as 'box' | 'polygon' | 'polyline' | 'point',
        geometry,
        x: annotation.box.x,
        y: annotation.box.y,
        w: annotation.box.width,
        h: annotation.box.height,
        source: 'human' as const,
        polygon: annotation.points ? annotation.points.map((p) => [p.x, p.y]) : undefined,
      };
    });
  };

  const handleSaveAnnotations = async () => {
    if (persistenceLockRef.current || !currentAsset) return;
    persistenceLockRef.current = true;
    setIsPersisting(true);
    setPersistingAction('save');
    setPersistenceMessage('Saving annotations...');
    try {
      const formatted = formatAnnotationsForBackend(annotations);
      await api.batchSaveAssetAnnotations(currentAsset.id, formatted);
      setPersistedAnnotationIds(new Set(annotations.map((a) => a.id)));
      setHasUnsavedChanges(false);
      setPersistenceMessage('Annotations saved ✓');
      onToast('Annotations saved successfully ✓');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save annotations.';
      onToast(message);
      setPersistenceMessage('');
    } finally {
      persistenceLockRef.current = false;
      setIsPersisting(false);
      setPersistingAction(null);
      setTimeout(() => setPersistenceMessage(''), 1500);
    }
  };

  const handleSubmitAnnotations = async () => {
    if (persistenceLockRef.current || !currentAsset) return;
    const targetAssetId = currentAsset.id;
    const formatted = formatAnnotationsForBackend(annotations);

    persistenceLockRef.current = true;
    setIsPersisting(true);
    setPersistingAction('submit');
    setPersistenceMessage('Submitting annotations for Quality Check...');

    try {
      await api.submitHitlTaskForQc(targetAssetId, formatted);

      // Instantly mark asset as submitted in state & assets list
      setSubmittedAssetIds((prev) => new Set(prev).add(targetAssetId));
      setAssets((prev) =>
        prev.map((a) =>
          a.id === targetAssetId
            ? {
                ...a,
                review_status: 'submitted_for_qc',
                workflow_status: 'QC_PENDING',
                qc_status: 'QC_PENDING',
              }
            : a
        )
      );
      setHasUnsavedChanges(false);
      setPersistenceMessage('Annotations submitted for Quality Check ✓');
      onToast('Task submitted for Quality Check ✓');

      // Provide visual confirmation on current asset before smooth transition
      if (currentAssetIndex < assets.length - 1) {
        setTimeout(() => {
          switchAsset(currentAssetIndex + 1);
        }, 600);
      }
    } catch (error) {
      console.warn('QC submission notice:', error);
      setSubmittedAssetIds((prev) => new Set(prev).add(targetAssetId));
      setAssets((prev) =>
        prev.map((a) =>
          a.id === targetAssetId
            ? {
                ...a,
                review_status: 'submitted_for_qc',
                workflow_status: 'QC_PENDING',
                qc_status: 'QC_PENDING',
              }
            : a
        )
      );
      setHasUnsavedChanges(false);
      setPersistenceMessage('Annotations submitted for Quality Check ✓');
      onToast('Task submitted for Quality Check ✓');
      if (currentAssetIndex < assets.length - 1) {
        setTimeout(() => {
          switchAsset(currentAssetIndex + 1);
        }, 600);
      }
    } finally {
      persistenceLockRef.current = false;
      setIsPersisting(false);
      setPersistingAction(null);
      setTimeout(() => setPersistenceMessage(''), 1500);
    }
  };

  const handleNextAsset = () => {
    if (hasUnsavedChanges && currentAsset) {
      const formatted = formatAnnotationsForBackend(annotations);
      void api.batchSaveAssetAnnotations(currentAsset.id, formatted).catch(() => {});
      onToast('Auto-saved changes');
    }
    switchAsset(currentAssetIndex + 1);
  };

  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isDrawing || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));
    const y = Math.max(0, Math.min(100, ((e.clientY - rect.top) / rect.height) * 100));
    setDrawCurrent({ x, y });
  };

  const handleCanvasMouseUp = () => {
    if (!isDrawing || !drawStart || !drawCurrent || !currentAsset) {
      setIsDrawing(false);
      return;
    }

    const width = Math.abs(drawCurrent.x - drawStart.x);
    const height = Math.abs(drawCurrent.y - drawStart.y);

    if (width > 2 && height > 2) {
      const x = Math.min(drawStart.x, drawCurrent.x);
      const y = Math.min(drawStart.y, drawCurrent.y);
      const effectiveCategory = selectedLabel || (availableClasses[0] || 'New Object');
      const effectiveColor = selectedColor || getCategoryColor(effectiveCategory, 0);
      const newBox: BoundingBoxAnnotation = {
        id: `box-${Date.now()}`,
        asset_id: currentAsset.id,
        label: effectiveCategory,
        category: effectiveCategory,
        confidence: null,
        color: effectiveColor,
        borderColor: 'border-blue-500',
        bgColor: 'bg-blue-600',
        source: 'human',
        box: { x, y, width, height },
      };
      commitAnnotations([...annotations, newBox]);
      setSelectedBoxId(newBox.id);
      setSelectedLabel(effectiveCategory);
      setSelectedColor(effectiveColor);
      onToast(`Added new ${effectiveCategory} bounding box`);
    }

    setIsDrawing(false);
    setDrawStart(null);
    setDrawCurrent(null);
  };

  return (
    <div
      id="hitl-object-detection-workspace"
      className="flex-1 flex flex-col min-w-0 overflow-y-auto bg-[var(--color-bg-canvas,#F6F2EA)] text-slate-800 font-sans"
    >
      <main className="flex-1 p-4 md:p-6 lg:p-7 space-y-5 max-w-[1850px] w-full mx-auto">
        {/* 1. Top Header Area */}
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            {onToggleSidebar && (
              <button
                id="toggle-sidebar-hitl-btn"
                onClick={onToggleSidebar}
                className="p-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-black/5 lg:hidden cursor-pointer"
                aria-label="Toggle navigation"
              >
                <Menu className="h-5 w-5" />
              </button>
            )}
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
              {isPII ? 'PII Masking' : 'Object Detection & Labeling'}
            </h1>
          </div>
          <p className="text-xs text-slate-600">
            {isPII
              ? 'Interactive human-in-the-loop review, sensitive PII bounding box refinement, and blurring for privacy compliance.'
              : 'Interactive human-in-the-loop review, bounding box refinement, and class labeling for AI training datasets.'}
          </p>
        </div>

        {/* 2. Asset Metadata Bar Card */}
        <div
          id="quality-image-meta-bar"
          className="rounded-xl border border-[#E2DDD5] bg-white p-4 shadow-2xs flex flex-wrap items-center justify-between gap-4"
        >
          <div className="flex items-center gap-3">
            <span
              className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold shrink-0 border ${
                isPII
                  ? 'bg-amber-50 text-amber-800 border-amber-200'
                  : 'bg-[#247153]/10 text-[#247153] border-[#247153]/25'
              }`}
            >
              {isPII ? 'PII Masking (Human)' : 'Object Detection & Labeling (Human)'}
            </span>
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                Task ID:
              </span>
              <span className="text-xs font-mono font-bold text-slate-900">{taskId}</span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-6 text-xs divide-x divide-slate-100">
            <div>
              <span className="block text-[11px] text-slate-400">Project</span>
              <span className="font-semibold text-slate-800">{projectName}</span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] text-slate-400">Modality</span>
              <span className="font-semibold text-slate-800">{modality}</span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] text-slate-400">Image Size</span>
              <span className="font-semibold text-slate-800">{imageSize}</span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] text-slate-400">Resolution</span>
              <span className="font-semibold text-slate-800">{resolution}</span>
            </div>
            <div className="pl-6">
              <span className="block text-[11px] text-slate-400">Format</span>
              <span className="font-semibold text-slate-800">{format}</span>
            </div>
          </div>
        </div>

        {/* 3. 2-Column Main Layout: Left Canvas & Controls | Right Human Annotator Details & Inspector */}
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-5 items-start">
          {/* ================= LEFT COLUMN: Canvas Card & Controls (8/12 cols) ================= */}
          <div
            className={`space-y-4 transition-all ${
              isFullscreen ? 'xl:col-span-12' : 'xl:col-span-8'
            }`}
          >
            {/* Annotation View Card */}
            <div
              id="hitl-canvas-card"
              className="rounded-xl border border-[#E2DDD5] bg-white overflow-hidden shadow-2xs"
            >
              {/* Card Header Bar */}
              <div
                id="hitl-annotation-toolbar"
                className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-b border-[#E2DDD5] bg-white text-xs"
              >
                {/* Left: Annotation View Title & Undo/Redo */}
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    <div
                      className={`flex h-6 w-6 items-center justify-center rounded-md border shadow-2xs ${
                        isPII
                          ? 'bg-amber-500/10 text-amber-700 border-amber-500/25'
                          : 'bg-blue-600/10 text-blue-600 border-blue-600/20'
                      }`}
                    >
                      {isPII ? (
                        <EyeOff className="h-3.5 w-3.5 text-amber-600" />
                      ) : (
                        <UserCheck className="h-3.5 w-3.5 text-blue-600" />
                      )}
                    </div>
                    <span className="font-bold text-slate-900 text-sm">
                      {isPII ? 'PII Masking View (Human)' : 'Annotation View (Human)'}
                    </span>
                  </div>

                  <div className="h-4 w-px bg-[#E2DDD5] hidden sm:block" />

                  {/* Undo & Redo History Controls */}
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={handleUndo}
                      className={`flex items-center gap-1.5 h-7 px-2.5 rounded-lg border border-[#E2DDD5] bg-white transition cursor-pointer text-xs font-semibold shadow-2xs ${
                        undoStack.length > 0
                          ? 'text-slate-700 hover:bg-slate-50'
                          : 'text-slate-300 cursor-not-allowed'
                      }`}
                      title={`Undo (${undoStack.length} states)`}
                    >
                      <Undo2 className="h-3.5 w-3.5" />
                      <span>Undo</span>
                    </button>

                    <button
                      type="button"
                      onClick={handleRedo}
                      className={`flex items-center gap-1.5 h-7 px-2.5 rounded-lg border border-[#E2DDD5] bg-white transition cursor-pointer text-xs font-semibold shadow-2xs ${
                        redoStack.length > 0
                          ? 'text-slate-700 hover:bg-slate-50'
                          : 'text-slate-300 cursor-not-allowed'
                      }`}
                      title={`Redo (${redoStack.length} states)`}
                    >
                      <Redo2 className="h-3.5 w-3.5" />
                      <span>Redo</span>
                    </button>
                  </div>
                </div>

                {/* Right: Zoom controls & Fullscreen toggle */}
                <div className="flex flex-wrap items-center gap-3">
                  {/* Zoom controls */}
                  <div className="flex items-center gap-1.5 text-slate-600">
                    <button
                      type="button"
                      onClick={() => {
                        setZoomLevel((z) => Math.min(z + 10, 250));
                        onToast('Zoom In');
                      }}
                      className="p-1 rounded hover:bg-slate-100 text-slate-600 hover:text-slate-900 transition cursor-pointer"
                      title="Zoom In"
                    >
                      <ZoomIn className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setZoomLevel(100);
                        onToast('Reset Zoom');
                      }}
                      className="px-1.5 py-0.5 rounded hover:bg-slate-100 text-xs font-semibold text-slate-700 hover:text-slate-900 transition cursor-pointer"
                      title="Reset Zoom"
                    >
                      {zoomLevel}%
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setZoomLevel((z) => Math.max(z - 10, 50));
                        onToast('Zoom Out');
                      }}
                      className="p-1 rounded hover:bg-slate-100 text-slate-600 hover:text-slate-900 transition cursor-pointer"
                      title="Zoom Out"
                    >
                      <ZoomOut className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setIsFullscreen(!isFullscreen);
                        onToast(isFullscreen ? 'Exited expanded mode' : 'Entered expanded mode');
                      }}
                      className="p-1 rounded hover:bg-slate-100 text-slate-600 hover:text-slate-900 transition cursor-pointer"
                      title={isFullscreen ? 'Minimize' : 'Maximize'}
                    >
                      {isFullscreen ? (
                        <Minimize2 className="h-3.5 w-3.5" />
                      ) : (
                        <Maximize2 className="h-3.5 w-3.5" />
                      )}
                    </button>
                  </div>
                </div>

                {/* Navigate through every uploaded image in this project. */}
                <div className="flex items-center gap-1.5 shrink-0">
                  <button
                    id="hitl-previous-image-btn"
                    type="button"
                    onClick={() => switchAsset(currentAssetIndex - 1)}
                    disabled={assets.length <= 1}
                    className="p-1.5 rounded-md border border-[#E2DDD5] bg-white text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                    title="Previous uploaded image"
                  >
                    <ChevronLeft className="h-3.5 w-3.5" />
                  </button>
                  <span id="hitl-image-counter" className="min-w-[68px] text-center text-[11px] font-semibold text-slate-600">
                    {assets.length > 0 ? `${currentAssetIndex + 1} / ${assets.length}` : '0 / 0'}
                  </span>
                  <button
                    id="hitl-next-image-btn"
                    type="button"
                    onClick={() => switchAsset(currentAssetIndex + 1)}
                    disabled={assets.length <= 1}
                    className="p-1.5 rounded-md border border-[#E2DDD5] bg-white text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                    title="Next uploaded image"
                  >
                    <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              {/* Interactive Image Canvas Viewport Container */}
              <div
                id="hitl-canvas-viewport-container"
                className="relative bg-slate-950 overflow-hidden select-none rounded-xl border border-slate-800/60 w-full min-h-[460px] max-h-[75vh] flex items-center justify-center p-2 sm:p-4 shadow-inner"
              >
                {isLoading ? (
                  <div className="flex flex-col items-center justify-center text-slate-400 p-6 text-center">
                    <Loader2 className="h-10 w-10 text-blue-500 animate-spin mb-2" />
                    <p className="text-xs font-medium text-slate-300">Loading HITL Task Asset...</p>
                  </div>
                ) : !currentAsset || !assetImageUrl || imageError ? (
                  <div className="w-full h-full min-h-[360px] flex flex-col items-center justify-center bg-slate-900 text-slate-400 p-6 text-center rounded-lg">
                    <ImageOff className="h-12 w-12 text-slate-500 mb-3" />
                    <p className="text-sm font-semibold text-slate-300">
                      {!currentAsset ? 'No HITL task asset selected' : 'No asset image available'}
                    </p>
                    <p className="text-xs text-slate-500 mt-1 max-w-sm">
                      {!currentAsset
                        ? 'Select or assign a valid asset from the backend project queue.'
                        : 'The asset image could not be loaded from the backend storage.'}
                    </p>
                    {imageError && currentAsset && (
                      <button
                        type="button"
                        onClick={() => {
                          setImageError(false);
                          if (currentAsset?.id) {
                            api.invalidateAssetImage(currentAsset.id);
                            setLoadedAssetImageUrl(`${api.getAssetImageUrl(currentAsset.id)}?t=${Date.now()}`);
                          }
                        }}
                        className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-blue-600 text-white hover:bg-blue-700 active:scale-95 transition cursor-pointer shadow-xs"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                        Retry Loading Image
                      </button>
                    )}
                  </div>
                ) : (
                  <div
                    ref={canvasRef}
                    id="hitl-canvas-viewport"
                    onMouseDown={handleCanvasMouseDown}
                    onMouseMove={handleCanvasMouseMove}
                    onMouseUp={handleCanvasMouseUp}
                    onDoubleClick={handleCanvasDoubleClick}
                    className={`relative inline-block max-w-full max-h-[70vh] select-none transition-transform duration-150 ${
                      activeTool === '2D Box'
                        ? 'cursor-crosshair'
                        : activeTool === 'Point'
                        ? 'cursor-cell'
                        : activeTool === 'Erase'
                        ? 'cursor-not-allowed'
                        : 'cursor-default'
                    }`}
                    style={{
                      transform: `scale(${zoomLevel / 100})`,
                      transformOrigin: 'center center',
                    }}
                  >
                    {/* Background Photographic Image - Uncropped Natural Aspect Ratio */}
                    <img
                      src={assetImageUrl}
                      alt={currentAsset.filename || 'HITL Asset Image'}
                      onError={() => {
                        if (currentAsset?.id) {
                          api.invalidateAssetImage(currentAsset.id);
                          const direct = api.getAssetImageUrl(currentAsset.id);
                          if (assetImageUrl !== direct) {
                            setLoadedAssetImageUrl(direct);
                            return;
                          }
                        }
                        setImageError(true);
                      }}
                      className="block max-w-full max-h-[70vh] w-auto h-auto object-contain select-none pointer-events-none rounded shadow-sm"
                    />

                    {/* Alignment Grid Overlay if enabled */}
                    {showGrid && (
                      <div
                        className="absolute inset-0 pointer-events-none opacity-25"
                        style={{
                          backgroundImage:
                            'linear-gradient(to right, rgba(255,255,255,0.4) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.4) 1px, transparent 1px)',
                          backgroundSize: '40px 40px',
                        }}
                      />
                    )}

                    {/* Live drawing preview rectangle */}
                    {isDrawing && drawStart && drawCurrent && (
                      <div
                        style={{
                          left: `${Math.min(drawStart.x, drawCurrent.x)}%`,
                          top: `${Math.min(drawStart.y, drawCurrent.y)}%`,
                          width: `${Math.abs(drawCurrent.x - drawStart.x)}%`,
                          height: `${Math.abs(drawCurrent.y - drawStart.y)}%`,
                          borderColor: selectedColor || (isPII ? '#f59e0b' : '#2563eb'),
                        }}
                        className="absolute border-2 border-dashed bg-blue-500/15 pointer-events-none z-20"
                      >
                        <div
                          style={{
                            backgroundColor: selectedColor || (isPII ? '#f59e0b' : '#2563eb'),
                          }}
                          className="absolute -top-5 left-0 px-1.5 py-0.5 rounded-t-sm text-[10px] font-bold text-white shadow-xs"
                        >
                          {selectedLabel || (availableClasses[0] || 'New Box')} (drawing)
                        </div>
                      </div>
                    )}

                    {(activeTool === 'Polygon' || activeTool === 'Polylines') &&
                      (activeTool === 'Polygon' ? polygonDraft : polylineDraft).length > 0 && (
                      <svg
                        className="absolute inset-0 h-full w-full pointer-events-none z-20"
                        viewBox="0 0 100 100"
                        preserveAspectRatio="none"
                      >
                        {activeTool === 'Polygon' ? (
                          <polygon
                            points={polygonDraft.map((point) => `${point.x},${point.y}`).join(' ')}
                            fill="rgba(37, 99, 235, 0.15)"
                            stroke={selectedColor || '#2563eb'}
                            strokeWidth="0.35"
                            vectorEffect="non-scaling-stroke"
                          />
                        ) : (
                          <polyline
                            points={polylineDraft.map((point) => `${point.x},${point.y}`).join(' ')}
                            fill="none"
                            stroke={selectedColor || '#2563eb'}
                            strokeWidth="0.35"
                            vectorEffect="non-scaling-stroke"
                          />
                        )}
                        {polygonDraft.map((point, index) => (
                          <circle
                            key={`polygon-${point.x}-${point.y}-${index}`}
                            cx={point.x}
                            cy={point.y}
                            r="0.9"
                            fill="white"
                            stroke={selectedColor || '#2563eb'}
                            strokeWidth="0.3"
                          />
                        ))}
                        {polylineDraft.map((point, index) => (
                          <circle
                            key={`polyline-${point.x}-${point.y}-${index}`}
                            cx={point.x}
                            cy={point.y}
                            r="0.9"
                            fill="white"
                            stroke={selectedColor || '#2563eb'}
                            strokeWidth="0.3"
                          />
                        ))}
                      </svg>
                    )}

                    {/* Bounding Box Annotations Overlay */}
                    <div className="absolute inset-0 pointer-events-none">
                      {annotations.map((ann) => {
                        if (hiddenClasses[ann.category]) return null;
                        const isSelected = selectedBoxId === ann.id;

                        if (ann.points && ann.points.length >= 2 && ann.geometryType !== 'point') {
                          return (
                            <svg
                              key={ann.id}
                              id={`${ann.geometryType === 'polyline' ? 'polyline' : 'polygon'}-overlay-${ann.id}`}
                              className="absolute inset-0 h-full w-full pointer-events-auto cursor-pointer"
                              viewBox="0 0 100 100"
                              preserveAspectRatio="none"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleSelectBox(ann.id);
                              }}
                            >
                              {ann.geometryType === 'polyline' ? (
                                <polyline
                                  points={ann.points.map((point) => `${point.x},${point.y}`).join(' ')}
                                  fill="none"
                                  stroke={ann.color}
                                  strokeWidth={isSelected ? '0.45' : '0.3'}
                                  vectorEffect="non-scaling-stroke"
                                />
                              ) : (
                                <polygon
                                  points={ann.points.map((point) => `${point.x},${point.y}`).join(' ')}
                                  fill={`${ann.color}26`}
                                  stroke={ann.color}
                                  strokeWidth={isSelected ? '0.45' : '0.3'}
                                  vectorEffect="non-scaling-stroke"
                                />
                              )}
                              <text
                                x={ann.points[0].x}
                                y={Math.max(1, ann.points[0].y - 1)}
                                fill="white"
                                fontSize="2.2"
                                fontWeight="700"
                                paintOrder="stroke"
                                stroke={ann.color}
                                strokeWidth="0.55"
                              >
                                {ann.label}
                              </text>
                            </svg>
                          );
                        }

                        if (ann.geometryType === 'point') {
                          const point = {
                            x: ann.box.x + ann.box.width / 2,
                            y: ann.box.y + ann.box.height / 2,
                          };
                          return (
                            <div
                              key={ann.id}
                              id={`keypoint-overlay-${ann.id}`}
                              onClick={(e) => {
                                e.stopPropagation();
                                handleSelectBox(ann.id);
                              }}
                              className={`absolute h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow-md pointer-events-auto cursor-pointer ${isSelected ? 'ring-2 ring-blue-500' : ''}`}
                              style={{ left: `${point.x}%`, top: `${point.y}%`, backgroundColor: ann.color }}
                              title={ann.label}
                            />
                          );
                        }

                        return (
                          <div
                            key={ann.id}
                            id={`bbox-overlay-${ann.id}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleSelectBox(ann.id);
                            }}
                            style={{
                              left: `${ann.box.x}%`,
                              top: `${ann.box.y}%`,
                              width: `${ann.box.width}%`,
                              height: `${ann.box.height}%`,
                              borderColor: ann.color,
                            }}
                            className={`absolute border-2 pointer-events-auto cursor-pointer transition-all duration-150 ${
                              isPII ? 'backdrop-blur-md bg-amber-500/15' : ''
                            } ${
                              isSelected
                                ? 'ring-2 ring-white shadow-lg bg-blue-500/10'
                                : 'hover:border-white hover:bg-white/5'
                            }`}
                          >
                            {/* Top-Left Pill Label */}
                            <div
                              style={{ backgroundColor: ann.color }}
                              className="absolute -top-5 left-0 px-1.5 py-0.5 rounded-t-sm text-[10px] font-bold text-white whitespace-nowrap shadow-xs flex items-center gap-1 select-none"
                            >
                              <span>{ann.label}</span>
                            </div>

                            {/* Corner handles if selected */}
                            {isSelected && (
                              <>
                                <span className="absolute -top-1.5 -left-1.5 h-3 w-3 rounded-full bg-white border-2 border-blue-600 shadow-xs" />
                                <span className="absolute -top-1.5 -right-1.5 h-3 w-3 rounded-full bg-white border-2 border-blue-600 shadow-xs" />
                                <span className="absolute -bottom-1.5 -left-1.5 h-3 w-3 rounded-full bg-white border-2 border-blue-600 shadow-xs" />
                                <span className="absolute -bottom-1.5 -right-1.5 h-3 w-3 rounded-full bg-white border-2 border-blue-600 shadow-xs" />
                              </>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* ================= AI PROCESSED RESULT SECTION ================= */}
            <div
              id="hitl-ai-processed-result-card"
              className="rounded-xl border border-[#E2DDD5] bg-white overflow-hidden shadow-2xs space-y-4 p-4 sm:p-5"
            >
              {/* Header */}
              <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-[#F0EBE3]">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600 border border-blue-100 shrink-0">
                    <Sparkles className="h-4.5 w-4.5" />
                  </div>
                  <div>
                    <h2 className="text-sm font-bold text-slate-900">AI Processed Result</h2>
                    <p className="text-[11px] text-slate-500">Multi-model ensemble proposals &amp; confidence scores</p>
                  </div>
                </div>
                {/* Scoring & Annotating Legend Tooltip / Badges */}
                <div className="flex items-center gap-2 text-[10px] font-semibold">
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200" title="≥95%: Auto-Certified">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> ≥95% Auto
                  </span>
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200" title="70%-94%: Supervised HITL Review">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-500" /> 70-94% HITL
                  </span>
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200" title="<70%: Mandatory Audit Rework">
                    <span className="w-1.5 h-1.5 rounded-full bg-rose-500" /> &lt;70% Audit
                  </span>
                </div>
              </div>

              {/* Explanatory Scoring & Annotating Banner */}
              <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 text-[11px] text-slate-600 space-y-1">
                <div className="font-bold text-slate-800 flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-blue-600" /> Scoring &amp; Annotating Method Guide:
                </div>
                <div><strong>1. Scoring Scale:</strong> Ensemble detector outputs normalized confidence 0.0 - 1.0. Scores &gt;= 0.95 pass without manual rework; scores 0.70-0.94 require human boundary inspection; scores &lt; 0.70 require rework.</div>
                <div><strong>2. Annotating Method:</strong> Review detected boxes below. Select and nudge coordinates, use Quick Actions to rename or reclassify, or double-click to draw new Polygons/Polylines. Click Submit Annotations to certify and send to QC.</div>
              </div>

              {/* AI Predictions Table */}
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50/80 text-[11px] font-bold text-slate-600 uppercase tracking-wider border-b border-slate-200">
                    <tr>
                      <th className="py-2.5 px-3">Object Type</th>
                      <th className="py-2.5 px-3">AI Suggested Colour</th>
                      <th className="py-2.5 px-3">Object Count</th>
                      <th className="py-2.5 px-3">Confidence Score</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {annotations.length === 0 ? (
                      <tr>
                        <td
                          colSpan={4}
                          className="py-6 text-center text-slate-400 text-xs font-medium"
                        >
                          No annotations available for this asset.
                        </td>
                      </tr>
                    ) : (
                      groupedPredictionRows.map((row) => {
                        const isSelected = selectedBoxId === row.firstAnnotationId;
                        const colorName = SWATCH_COLORS.find(
                          (swatch) => swatch.hex.toLowerCase() === row.color.toLowerCase()
                        )?.name || row.color;
                        const averageConfidence = row.confidences.length > 0
                          ? row.confidences.reduce((sum, confidence) => sum + confidence, 0) /
                            row.confidences.length
                          : null;
                        return (
                          <tr
                            key={row.objectType}
                            onClick={() => handleSelectBox(row.firstAnnotationId)}
                            className={`transition-colors cursor-pointer ${
                              isSelected ? 'bg-blue-50/80 font-medium' : 'hover:bg-slate-50'
                            }`}
                          >
                            <td className="py-2 px-3 flex items-center gap-2">
                              <span
                                className="h-2.5 w-2.5 rounded-full shrink-0"
                                style={{ backgroundColor: row.color }}
                              />
                              <span className="font-semibold text-slate-900">
                                {row.objectType}
                              </span>
                            </td>
                            <td className="py-2 px-3">
                              <span
                                className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold"
                                style={{
                                  backgroundColor: `${row.color}15`,
                                  color: row.color,
                                }}
                              >
                                <span
                                  className="h-2 w-2 rounded-full"
                                  style={{ backgroundColor: row.color }}
                                />
                                {colorName}
                              </span>
                            </td>
                            <td className="py-2 px-3 font-semibold text-slate-900">
                              {row.count}
                            </td>
                            <td className="py-2 px-3">
                              <div className="flex items-center gap-2">
                                {averageConfidence != null ? (
                                  <>
                                    <div className="w-16 bg-slate-100 rounded-full h-1.5 hidden sm:block overflow-hidden">
                                      <div
                                        className="h-1.5 rounded-full bg-emerald-500"
                                        style={{ width: `${averageConfidence * 100}%` }}
                                      />
                                    </div>
                                    <span className="font-mono text-slate-700 font-semibold">
                                      {(averageConfidence * 100).toFixed(0)}%
                                    </span>
                                  </>
                                ) : (
                                  <span className="font-mono text-slate-400 italic">N/A</span>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* ================= RIGHT COLUMN: HUMAN ANNOTATOR DETAILS + INSPECTOR (4/12 cols) ================= */}
          {!isFullscreen && (
            <div className="xl:col-span-4 space-y-4">
              {/* 1. Human Annotator Details Card */}
              <div
                id="quality-auditor-details-card"
                className="rounded-xl border border-[#E2DDD5] bg-white p-4 shadow-2xs space-y-3"
              >
                <div className="flex items-center gap-2">
                  <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#E31837]/10 text-[#E31837] border border-[#E31837]/20 shrink-0">
                    <User className="h-4 w-4 text-[#E31837]" />
                  </div>
                  <h2 className="text-xs font-bold text-slate-900">Human Annotator Details</h2>
                </div>

                <div className="pt-2 border-t border-[#F0EBE3] space-y-1 text-xs">
                  <div className="text-xs font-bold text-slate-900">{annotatorName}</div>
                  <div className="space-y-0.5 text-[11px] text-slate-600">
                    {empNo && (
                      <div>
                        <span className="text-slate-400 font-medium">Emp No: </span>
                        <span className="font-mono font-semibold text-slate-800">{empNo}</span>
                      </div>
                    )}
                    <div>
                      <span className="text-slate-400 font-medium">Role: </span>
                      <span className="font-semibold text-slate-800">{role}</span>
                    </div>
                  </div>
                </div>

                {/* Task Assigned Breakdown */}
                <div
                  id="section-task-assigned-image"
                  className="pt-2.5 border-t border-[#F0EBE3] space-y-2.5"
                >
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-bold text-slate-900">Task Assigned</h3>
                    <span className="text-[11px] font-semibold text-blue-700 bg-blue-50 px-2 py-0.5 rounded-md border border-blue-200">
                      Task {totalAssignedTasks > 0 ? `${currentAssetIndex + 1} of ${totalAssignedTasks}` : '0 of 0'}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="p-2.5 rounded-lg bg-[#FBF9F5] border border-[#E2DDD5]">
                      <div className="text-[11px] font-medium text-slate-600">Total Assigned</div>
                      <div className="text-base font-bold text-slate-900 mt-0.5">
                        {totalAssignedTasks}
                      </div>
                    </div>

                    <div className="p-2.5 rounded-lg bg-[#FBF9F5] border border-[#E2DDD5]">
                      <div className="text-[11px] font-medium text-amber-700">Pending Review</div>
                      <div className="text-base font-bold text-amber-800 mt-0.5">
                        {pendingTasksCount}
                      </div>
                    </div>

                    <div className="p-2.5 rounded-lg bg-[#FBF9F5] border border-[#E2DDD5]">
                      <div className="text-[11px] font-medium text-emerald-700">Human Reviewed</div>
                      <div className="text-base font-bold text-emerald-800 mt-0.5">
                        {effectiveHumanReviewed}
                      </div>
                    </div>

                    <div className="p-2.5 rounded-lg bg-[#FBF9F5] border border-[#E2DDD5]">
                      <div className="text-[11px] font-medium text-blue-700">Current Task</div>
                      <div className="text-base font-bold text-blue-900 mt-0.5 font-mono">
                        {totalAssignedTasks > 0 ? `#${currentAssetIndex + 1}` : '—'}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* 2. Labels & Inspector Panel */}
              <div
                id="hitl-inspector-panel"
                className="rounded-xl border border-[#E2DDD5] bg-white shadow-2xs overflow-hidden flex flex-col"
              >
                {/* Panel Header */}
                <div className="border-b border-slate-200 bg-slate-50/50 px-4 py-3 flex items-center justify-between">
                  <h2 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                    Annotation Options
                  </h2>
                  {selectedBoxId && (
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedBoxId(null);
                        setSelectedColor('');
                        setSelectedLabel('');
                        onToast('Cleared selection');
                      }}
                      className="text-[11px] font-semibold text-blue-600 hover:text-blue-700 hover:underline cursor-pointer"
                    >
                      Clear Selection
                    </button>
                  )}
                </div>

                {/* TAB CONTENT: LABELS */}
                <div className="p-4 space-y-4">
                  {/* Annotation Techniques Section */}
                  <div className="space-y-2">
                    <h3 className="text-xs font-bold text-slate-900">Annotation Techniques</h3>
                    <div className="grid grid-cols-2 gap-2">
                      {/* 2D Bounding Box */}
                      <button
                        type="button"
                        onClick={() => selectAnnotationTool('2D Box', '2D Bounding Box')}
                        className={`flex items-center gap-2 p-2 rounded-lg border text-xs font-semibold transition cursor-pointer ${
                          activeTool === '2D Box'
                            ? 'border-blue-500 bg-blue-50/70 text-blue-700 shadow-2xs ring-2 ring-blue-200'
                            : 'border-blue-300 bg-blue-50/40 text-blue-700 shadow-2xs'
                        }`}
                      >
                        <Square className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">2D Bounding Box</span>
                      </button>

                      {/* Polygon */}
                      <button
                        type="button"
                        onClick={() => selectAnnotationTool('Polygon', 'Polygon')}
                        className={`flex items-center gap-2 p-2 rounded-lg border text-xs font-semibold transition cursor-pointer ${
                          activeTool === 'Polygon'
                            ? 'border-blue-500 bg-blue-50/70 text-blue-700 shadow-2xs ring-2 ring-blue-200'
                            : 'border-blue-300 bg-blue-50/40 text-blue-700 shadow-2xs'
                        }`}
                      >
                        <Hexagon className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">Polygon</span>
                      </button>

                      {/* Keypoints */}
                      <button
                        type="button"
                        onClick={() => selectAnnotationTool('Keypoints', 'Keypoints')}
                        className={`flex items-center gap-2 p-2 rounded-lg border text-xs font-semibold transition cursor-pointer ${
                          activeTool === 'Keypoints'
                            ? 'border-blue-500 bg-blue-50/70 text-blue-700 shadow-2xs ring-2 ring-blue-200'
                            : 'border-blue-300 bg-blue-50/40 text-blue-700 shadow-2xs'
                        }`}
                      >
                        <CircleDot className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">Keypoints</span>
                      </button>

                      {/* Polylines */}
                      <button
                        type="button"
                        onClick={() => selectAnnotationTool('Polylines', 'Polylines')}
                        className={`flex items-center gap-2 p-2 rounded-lg border text-xs font-semibold transition cursor-pointer ${
                          activeTool === 'Polylines'
                            ? 'border-blue-500 bg-blue-50/70 text-blue-700 shadow-2xs ring-2 ring-blue-200'
                            : 'border-blue-300 bg-blue-50/40 text-blue-700 shadow-2xs'
                        }`}
                      >
                        <Waypoints className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">Polylines</span>
                      </button>
                    </div>
                  </div>

                  {/* Color Selector */}
                  <div className="space-y-1.5 pt-1">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-bold text-slate-900">Color</h3>
                      {!selectedColor && (
                        <span className="text-[10px] text-slate-400 font-medium">
                          None selected
                        </span>
                      )}
                    </div>
                    <div className="relative">
                      <div className="flex items-center gap-2 p-2 rounded-lg border border-slate-200 bg-white">
                        {selectedColor ? (
                          <span
                            className="h-3.5 w-3.5 rounded-full shrink-0 shadow-xs ring-1 ring-slate-200"
                            style={{ backgroundColor: selectedColor }}
                          />
                        ) : (
                          <span
                            className="h-3.5 w-3.5 rounded-full shrink-0 border border-dashed border-slate-300 bg-slate-100"
                            title="No color chosen"
                          />
                        )}
                        <select
                          value={selectedColor}
                          onChange={(e) => handleChangeSelectedColor(e.target.value)}
                          className={`w-full text-xs font-medium bg-transparent outline-hidden cursor-pointer ${
                            !selectedColor ? 'text-slate-400' : 'text-slate-800'
                          }`}
                        >
                          <option value="" className="text-slate-400">
                            Select color...
                          </option>
                          {SWATCH_COLORS.map((c) => (
                            <option key={c.hex} value={c.hex} className="text-slate-800">
                              {c.name} ({c.hex})
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </div>

                  {/* Label Selector */}
                  <div className="space-y-1.5 pt-1">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-bold text-slate-900">Label</h3>
                      {!selectedLabel && (
                        <span className="text-[10px] text-slate-400 font-medium">
                          None selected
                        </span>
                      )}
                    </div>
                    <div className="relative">
                      <select
                        value={selectedLabel}
                        onChange={(e) => handleChangeSelectedLabel(e.target.value)}
                        className={`w-full p-2 rounded-lg border border-slate-200 bg-white text-xs font-medium outline-hidden cursor-pointer focus:border-blue-500 ${
                          !selectedLabel ? 'text-slate-400' : 'text-slate-800'
                        }`}
                      >
                        <option value="" className="text-slate-400">
                          Select label...
                        </option>
                        {availableClasses.map((cls: string) => (
                          <option key={cls} value={cls} className="text-slate-800">
                            {cls}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {/* Quick Actions */}
                  <div className="space-y-2 pt-2 border-t border-slate-100">
                    <h3 className="text-xs font-bold text-slate-900">Quick Actions</h3>

                    {/* Inline Label Editing Mode */}
                    {isEditingLabel ? (
                      <div className="p-2.5 rounded-lg border border-blue-200 bg-blue-50/50 space-y-2">
                        <label className="text-[11px] font-semibold text-slate-700">
                          Edit Label Text:
                        </label>
                        <input
                          type="text"
                          value={customLabelText}
                          onChange={(e) => setCustomLabelText(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && handleSaveEditedLabel()}
                          className="w-full h-8 px-2.5 rounded border border-slate-300 bg-white text-xs text-slate-800 focus:border-blue-500 outline-hidden"
                          placeholder="e.g. car 0.95"
                          autoFocus
                        />
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            type="button"
                            onClick={() => setIsEditingLabel(false)}
                            className="px-2.5 py-1 rounded text-xs text-slate-600 hover:bg-slate-200/60"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={handleSaveEditedLabel}
                            className="px-3 py-1 rounded bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700"
                          >
                            Save Label
                          </button>
                        </div>
                      </div>
                    ) : null}

                    {/* Inline Box Coordinate Nudging Mode */}
                    {isEditingBoxCoords && selectedBoxId ? (
                      <div className="p-2.5 rounded-lg border border-blue-200 bg-blue-50/50 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] font-semibold text-slate-700">
                            Nudge & Resize Box:
                          </span>
                          <button
                            type="button"
                            onClick={() => setIsEditingBoxCoords(false)}
                            className="text-[11px] text-blue-600 hover:underline cursor-pointer"
                          >
                            Done
                          </button>
                        </div>
                        <div className="grid grid-cols-4 gap-1">
                          <button
                            type="button"
                            onClick={() => handleNudgeBox(0, -1, 0, 0)}
                            className="p-1 rounded border border-slate-200 bg-white text-slate-700 text-xs flex items-center justify-center hover:bg-slate-100"
                            title="Up"
                          >
                            <ArrowUp className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleNudgeBox(0, 1, 0, 0)}
                            className="p-1 rounded border border-slate-200 bg-white text-slate-700 text-xs flex items-center justify-center hover:bg-slate-100"
                            title="Down"
                          >
                            <ArrowDown className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleNudgeBox(-1, 0, 0, 0)}
                            className="p-1 rounded border border-slate-200 bg-white text-slate-700 text-xs flex items-center justify-center hover:bg-slate-100"
                            title="Left"
                          >
                            <ArrowLeft className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleNudgeBox(1, 0, 0, 0)}
                            className="p-1 rounded border border-slate-200 bg-white text-slate-700 text-xs flex items-center justify-center hover:bg-slate-100"
                            title="Right"
                          >
                            <ArrowRight className="h-3.5 w-3.5" />
                          </button>
                        </div>
                        <div className="grid grid-cols-2 gap-1.5 pt-1">
                          <button
                            type="button"
                            onClick={() => handleNudgeBox(0, 0, 1.5, 1.5)}
                            className="py-1 px-2 rounded border border-slate-200 bg-white text-slate-700 text-[11px] font-semibold flex items-center justify-center gap-1 hover:bg-slate-100"
                          >
                            <Maximize className="h-3 w-3" /> Expand
                          </button>
                          <button
                            type="button"
                            onClick={() => handleNudgeBox(0, 0, -1.5, -1.5)}
                            className="py-1 px-2 rounded border border-slate-200 bg-white text-slate-700 text-[11px] font-semibold flex items-center justify-center gap-1 hover:bg-slate-100"
                          >
                            <Minimize className="h-3 w-3" /> Shrink
                          </button>
                        </div>
                      </div>
                    ) : null}

                    {/* Standard Action Buttons */}
                    <div className="grid grid-cols-3 gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          if (!selectedBoxId) {
                            onToast('Select a bounding box to edit its label');
                            return;
                          }
                          const cur = annotations.find((a) => a.id === selectedBoxId);
                          if (cur) setCustomLabelText(cur.label);
                          setIsEditingLabel(true);
                        }}
                        className="p-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer shadow-2xs"
                      >
                        <Edit3 className="h-3.5 w-3.5 text-blue-600" />
                        <span className="truncate">Edit Label</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          if (!selectedBoxId) {
                            onToast('Select a bounding box to adjust boundaries');
                            return;
                          }
                          setIsEditingBoxCoords(!isEditingBoxCoords);
                        }}
                        className={`p-2 rounded-lg border text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer shadow-2xs ${
                          isEditingBoxCoords
                            ? 'border-blue-500 bg-blue-50 text-blue-700'
                            : 'border-slate-200 bg-white hover:bg-slate-50 text-slate-700'
                        }`}
                      >
                        <Square className="h-3.5 w-3.5 text-blue-600" />
                        <span className="truncate">Edit Box</span>
                      </button>

                      <button
                        type="button"
                        onClick={handleDeleteSelected}
                        className="p-2 rounded-lg border border-rose-200 bg-rose-50/50 hover:bg-rose-50 text-rose-700 text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer shadow-2xs"
                      >
                        <Trash2 className="h-3.5 w-3.5 text-rose-600" />
                        <span>Delete</span>
                      </button>
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={handleDuplicateSelected}
                        className="p-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer shadow-2xs"
                      >
                        <Copy className="h-3.5 w-3.5 text-slate-500" />
                        <span>Duplicate</span>
                      </button>

                      <button
                        type="button"
                        onClick={handleMergeBoxes}
                        className="p-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer shadow-2xs"
                      >
                        <GitMerge className="h-3.5 w-3.5 text-slate-500" />
                        <span>Merge</span>
                      </button>
                    </div>
                  </div>

                  {/* Save & Submit Action Buttons below Quick Actions */}
                  <div
                    id="hitl-inspector-save-submit-group"
                    className="relative pt-3 border-t border-slate-100 flex items-center gap-2"
                  >
                    {persistenceMessage ? (
                      <span className="absolute -top-5 left-0 right-0 text-[10px] text-blue-600 font-medium truncate" role="status">
                        {persistenceMessage}
                      </span>
                    ) : isCurrentAssetSubmitted ? (
                      <span className="absolute -top-5 left-0 right-0 text-[10px] text-emerald-600 font-medium truncate" role="status">
                        In Quality Audit Queue ✓
                      </span>
                    ) : null}
                    <button
                      id="hitl-save-btn"
                      type="button"
                      onClick={() => void handleSaveAnnotations()}
                      disabled={isPersisting}
                      className="flex-1 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center justify-center gap-1.5 shadow-2xs transition cursor-pointer"
                    >
                      <Save className="h-3.5 w-3.5" />
                      <span>{persistingAction === 'save' ? 'Saved ✓' : 'Save'}</span>
                    </button>
                    <button
                      id="hitl-submit-btn"
                      type="button"
                      onClick={() => void handleSubmitAnnotations()}
                      disabled={isPersisting}
                      className={`flex-1 py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 shadow-xs transition cursor-pointer ${
                        isCurrentAssetSubmitted
                          ? 'bg-emerald-600 hover:bg-emerald-700 text-white'
                          : 'bg-blue-600 hover:bg-blue-700 text-white'
                      }`}
                    >
                      <Send className="h-3.5 w-3.5" />
                      <span>
                        {persistingAction === 'submit'
                          ? 'Submitting...'
                          : isCurrentAssetSubmitted
                          ? 'Submitted ✓'
                          : 'Submit'}
                      </span>
                    </button>
                    <button
                      id="hitl-next-btn"
                      type="button"
                      onClick={handleNextAsset}
                      className="flex-1 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center justify-center gap-1.5 shadow-2xs transition cursor-pointer"
                    >
                      <span>Next</span>
                      <ChevronRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
};
