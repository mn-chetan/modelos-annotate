import React, { useEffect, useRef, useState } from 'react';
import {
  IntakeFormData,
  ProjectType,
  DomainUseCase,
  DataTypeOption,
  MediaFormat,
  AnnotationType,
  OutputFormat,
  QualityLevel,
  TeamName,
  PriorityLevel,
  VisionAnnotationTechnique,
  TargetObjectClass,
  AXA_INSURANCE_DAMAGE_CLASSES,
  AXA_INSURANCE_NER_CLASSES,
  SUPPORTED_IMAGE_UPLOAD_EXTENSIONS,
  isSupportedImageUploadFile,
} from '../types';
import {
  FolderKanban,
  Database,
  Settings,
  Users,
  UploadCloud,
  Cloud,
  Link2,
  Calendar,
  ChevronDown,
  Video,
  Image as ImageIcon,
  FileText,
  Mic,
  Box,
  Layers,
  Check,
  ArrowRight,
  Sparkles,
  FileCheck,
  Plus,
  X,
  RotateCcw,
} from 'lucide-react';

interface IntakeFormProps {
  formData: IntakeFormData;
  onChange: (updated: Partial<IntakeFormData>) => void;
  onSaveDraft: () => void;
  onNext: () => void;
  isLoading?: boolean;
  onResetProject?: () => void;
  aiCompleted?: boolean;
  onViewAiResults?: () => void;
  onViewProductionDashboard?: () => void;
}

const TARGET_CLASS_COLORS = [
  '#2563EB',
  '#10B981',
  '#F59E0B',
  '#8B5CF6',
  '#EF4444',
  '#06B6D4',
  '#EC4899',
  '#84CC16',
];

const TARGET_CLASS_ALIASES: Record<string, string> = {
  car: 'Car',
  cars: 'Car',
  bus: 'Bus',
  buses: 'Bus',
  truck: 'Truck',
  trucks: 'Truck',
  motorcycle: 'Motorcycle',
  motorcycles: 'Motorcycle',
  bicycle: 'Bicycle',
  bicycles: 'Bicycle',
  van: 'Van',
  vans: 'Van',
  pedestrian: 'Pedestrian',
  pedestrians: 'Pedestrian',
  'traffic sign': 'Traffic Sign',
  'traffic signs': 'Traffic Sign',
  'traffic light': 'Traffic Light',
  'traffic lights': 'Traffic Light',
  'road barrier': 'Road Barrier',
  'road barriers': 'Road Barrier',
  'auto rickshaw': 'Auto-Rickshaw',
  'auto-rickshaw': 'Auto-Rickshaw',
  'auto rickshaws': 'Auto-Rickshaw',
  'auto-rickshaws': 'Auto-Rickshaw',
  'road object': 'Road Object',
  'road objects': 'Road Object',
};

const classKey = (name: string) => name.trim().toLocaleLowerCase().replace(/[\s-]+/g, ' ');

const toDisplayClassName = (value: string): string | null => {
  let normalized = value
    .replace(/[.!?:()[\]{}]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLocaleLowerCase();

  // Strip instruction prefixes
  normalized = normalized
    .replace(/^(?:please\s+)?(?:precisely|accurately|carefully)?\s*(?:detect|identify|find|annotate|label|include|including|extract|track|locate|segment|classify|recognize)\s+(?:and\s+(?:annotate|segment|detect|label)\s+)?(?:all\s+)?(?:the\s+)?/i, '')
    .replace(/^objects?\s+(?:such\s+as|like)\s+/i, '')
    .replace(/^other\s+/, '');

  // Strip trailing instruction / verb clauses
  normalized = normalized
    .replace(/\s+(?:should\s+be|to\s+be|must\s+be|need\s+to\s+be|needs\s+to\s+be|will\s+be|are\s+to\s+be|ought\s+to\s+be)\s*(?:identified|detected|annotated|labeled|labelled|found|tracked|segmented|extracted|classified|recognized|located).*$/i, '')
    .replace(/\s+(?:should\s+be|to\s+be|must\s+be|need\s+to\s+be|needs\s+to\s+be)\s*$/i, '')
    .replace(/\s+(?:identified|detected|annotated|labeled|labelled|found|tracked|segmented|extracted|classified|recognized|located)\s*$/i, '')
    .replace(/\s+(?:in|from|within)\s+(?:the\s+)?(?:traffic\s+)?(?:images?|photos?|pictures?|video|frame|scene).*$/i, '')
    .replace(/\s+(?:using|with|for)\s+(?:accurate|precise|instance|pixel)?\s*(?:object\s+)?(?:boundaries|masks|boxes|polygons).*$/i, '')
    .replace(/\s+(?:objects?|targets?|instances?|items?|classes?|categories?)$/i, '')
    .trim();

  if (!normalized || /^(and|or|other|object|objects|things?)$/.test(normalized)) return null;
  if (TARGET_CLASS_ALIASES[normalized]) return TARGET_CLASS_ALIASES[normalized];

  if (normalized.endsWith('ies') && normalized.length > 3) {
    normalized = `${normalized.slice(0, -3)}y`;
  } else if (normalized.endsWith('s') && !normalized.endsWith('ss')) {
    normalized = normalized.slice(0, -1);
  }

  if (TARGET_CLASS_ALIASES[normalized]) return TARGET_CLASS_ALIASES[normalized];
  if (!normalized || /^(and|or|other|object|objects|thing)$/.test(normalized)) return null;
  return normalized
    .split(' ')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};

const extractTargetClasses = (text: string): string[] => {
  const cleanedText = text
    .replace(/\s+(?:should\s+be|to\s+be|must\s+be|need\s+to\s+be|needs\s+to\s+be|will\s+be|are\s+to\s+be)?\s*(?:identified|detected|annotated|labeled|labelled|found|tracked|segmented|extracted|classified|recognized|located).*$/gi, '')
    .replace(/\s+(?:in|from|within)\s+(?:the\s+)?(?:traffic\s+)?(?:images?|photos?|pictures?|video|frame|scene).*$/gi, '');
  const candidates = cleanedText
    .replace(/\b(and|or)\b/gi, ',')
    .split(/[,;\n]+/)
    .map((part) => part.trim())
    .filter(Boolean);
  const seen = new Set<string>();
  return candidates.reduce<string[]>((classes, candidate) => {
    const name = toDisplayClassName(candidate);
    if (name && !seen.has(classKey(name))) {
      seen.add(classKey(name));
      classes.push(name);
    }
    return classes;
  }, []);
};

export const IntakeForm: React.FC<IntakeFormProps> = ({
  formData,
  onChange,
  onSaveDraft,
  onNext,
  isLoading = false,
  onResetProject,
  aiCompleted = false,
  onViewAiResults,
  onViewProductionDashboard,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [connectUrlInput, setConnectUrlInput] = useState(formData.cloudStorageUrl || '');
  const [connectedSource, setConnectedSource] = useState<string | null>(null);
  const [newImageClassName, setNewImageClassName] = useState('');
  const [newImageClassColor, setNewImageClassColor] = useState('#06B6D4');
  const [selectedModel, setSelectedModel] = useState('auto');
  const extractionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoClassKeysRef = useRef(new Set<string>());
  const removedAutoClassKeysRef = useRef(new Set<string>());
  const classColorsRef = useRef(new Map<string, string>());

  const isTextAnnotation = formData.projectType === 'Text Annotation';
  const isImageAnnotation =
    formData.projectType === 'Image Annotation' ||
    (!formData.projectType && formData.mediaFormat === 'Image');
  const isPiiMasking = formData.annotationTypes.includes('PII Masking');
  const isObjectDetection =
    formData.annotationTypes.includes('Object Detection & Labeling') ||
    formData.annotationTypes.includes('Object Detection');
  const isTextNer =
    isTextAnnotation &&
    formData.annotationTypes.includes('NER Annotation');
  const isTextSentiment = isTextAnnotation && formData.annotationTypes.includes('Sentiment Annotation');
  const isTextClassification = isTextAnnotation && formData.annotationTypes.includes('Text Classification');
  // Vision annotation technique should only appear when the user is selecting annotation type as object detection & labelling or PII masking
  const showVisionTechniques = isObjectDetection || isPiiMasking;
  const showModelSelection = isImageAnnotation && isObjectDetection;

  const modelSelectionOptions = [
    { value: 'auto', label: 'Auto — Agent Decides' },
    { value: 'yolo26', label: 'YOLO26' },
    { value: 'faster-rcnn', label: 'Faster R-CNN' },
    { value: 'yolo26-dino', label: 'YOLO26 + DINO' },
    { value: 'yolo26-faster-rcnn', label: 'YOLO26 + Faster R-CNN' },
    { value: 'yolo26-faster-rcnn-dino', label: 'YOLO26 + Faster R-CNN + DINO' },
  ];

  // Keep the free-form instruction ("What should be identified?") visible for all
  // image workflows, including Object Detection & Labeling.
  const showImageInstruction = isImageAnnotation;
  const showTargetClasses = isTextNer;
  const showImageTargetClasses =
    isImageAnnotation &&
    (isObjectDetection ||
      formData.annotationTypes.includes('Segmentation') ||
      formData.annotationTypes.includes('Classification'));
  const activeImageClasses = formData.targetClasses || [];
  const activeImageClassesRef = useRef(activeImageClasses);
  activeImageClassesRef.current = activeImageClasses;

  useEffect(() => () => {
    if (extractionTimerRef.current) clearTimeout(extractionTimerRef.current);
  }, []);

  const getStableClassColor = (name: string, preferredColor?: string) => {
    const key = classKey(name);
    if (preferredColor) {
      classColorsRef.current.set(key, preferredColor);
      return preferredColor;
    }
    const existing = classColorsRef.current.get(key);
    if (existing) return existing;
    let hash = 0;
    for (let index = 0; index < key.length; index += 1) {
      hash = (hash * 31 + key.charCodeAt(index)) >>> 0;
    }
    const color = TARGET_CLASS_COLORS[hash % TARGET_CLASS_COLORS.length];
    classColorsRef.current.set(key, color);
    return color;
  };

  const scheduleTargetClassExtraction = (text: string, force = false) => {
    if (!force && (!isImageAnnotation || !isObjectDetection)) return;
    if (extractionTimerRef.current) clearTimeout(extractionTimerRef.current);
    extractionTimerRef.current = setTimeout(() => {
      const extracted = extractTargetClasses(text);
      const current = activeImageClassesRef.current;
      const currentKeys = new Set(current.map((item) => classKey(item.name)));
      const additions = extracted
        .filter((name) => {
          const key = classKey(name);
          return !currentKeys.has(key) && !removedAutoClassKeysRef.current.has(key);
        })
        .map((name) => {
          const key = classKey(name);
          autoClassKeysRef.current.add(key);
          return {
            id: `cls-auto-${key.replace(/[^a-z0-9]+/g, '-')}`,
            name,
            color: getStableClassColor(name),
            shortcutIndex: 0,
          };
        });

      if (additions.length > 0) {
        const merged = [...current, ...additions].map((item, index) => ({
          ...item,
          shortcutIndex: index + 1,
        }));
        onChange({ targetClasses: merged });
      }
    }, 300);
  };

  const handleAddImageClass = () => {
    const name = newImageClassName.trim();
    if (!name) return;
    const displayName = toDisplayClassName(name) || name;
    const key = classKey(displayName);
    if (activeImageClasses.some((item) => classKey(item.name) === key)) return;
    removedAutoClassKeysRef.current.delete(key);
    getStableClassColor(displayName, newImageClassColor || '#06B6D4');
    onChange({
      targetClasses: [
        ...activeImageClasses,
        {
          id: `cls-${Date.now()}`,
          name: displayName,
          color: newImageClassColor || '#06B6D4',
          shortcutIndex: activeImageClasses.length + 1,
        },
      ],
    });
    setNewImageClassName('');
  };

  const handleRemoveImageClass = (id: string) => {
    const removed = activeImageClasses.find((item) => item.id === id);
    if (removed && autoClassKeysRef.current.has(classKey(removed.name))) {
      removedAutoClassKeysRef.current.add(classKey(removed.name));
    }
    onChange({
      targetClasses: activeImageClasses
        .filter((item) => item.id !== id)
        .map((item, index) => ({ ...item, shortcutIndex: index + 1 })),
    });
  };

  // AXA and Enterprise Presets
  const handleLoadAxaDamagePreset = () => {
    onChange({
      projectName: 'AXA Insurance - Motor Claim Damage & FNOL Intake',
      description: 'Automated vehicle exterior damage assessment (dent, scratch, glass fracture, bumper deformation) and license plate PII masking for AXA Insurance motor claim FNOL intake.',
      projectType: 'Image Annotation',
      domainUseCase: 'Insurance & Claims (AXA)',
      dataType: 'Files Upload',
      mediaFormat: 'Image',
      numberOfFiles: 0,
      annotationTypes: ['Object Detection & Labeling'],
      expectedOutputFormat: 'COCO JSON',
      qualityLevel: 'High Precision (Double Blind Consensus)',
      assignedTeam: 'Core Perception Team',
      priority: 'High',
      visionTechnique: 'Polygon Segmentation',
      visionTechniques: ['Polygon Segmentation'],
      targetClasses: AXA_INSURANCE_DAMAGE_CLASSES,
      targetObjectsText: AXA_INSURANCE_DAMAGE_CLASSES.map((c) => c.name).join(', '),
    });
  };

  const handleLoadAxaNerPreset = () => {
    onChange({
      projectName: 'AXA Insurance - Policy & FNOL Claim Extraction',
      description: 'Automated entity extraction from policy schedules, police loss reports, and repair estimates for AXA Insurance claim settlement acceleration.',
      projectType: 'Text Annotation',
      domainUseCase: 'Insurance & Claims (AXA)',
      dataType: 'Files Upload',
      mediaFormat: 'Text',
      numberOfFiles: 120,
      annotationTypes: ['NER Annotation'],
      expectedOutputFormat: 'JSON',
      qualityLevel: 'High Precision (Double Blind Consensus)',
      assignedTeam: 'QA Annotation Guild',
      priority: 'High',
      visionTechnique: '',
      visionTechniques: [],
      targetClasses: AXA_INSURANCE_NER_CLASSES,
      targetObjectsText: AXA_INSURANCE_NER_CLASSES.map((c) => c.name).join(', '),
    });
  };

  const handleLoadUrbanTrafficPreset = () => {
    onChange({
      projectName: 'Urban Traffic Monitoring',
      description: 'Vehicle detection, pedestrian counting, and traffic flow monitoring across metropolitan intersections.',
      projectType: 'Image Annotation',
      domainUseCase: 'Urban Traffic',
      dataType: 'Files Upload',
      mediaFormat: 'Image',
      numberOfFiles: 0,
      annotationTypes: ['Object Detection & Labeling'],
      expectedOutputFormat: 'COCO JSON',
      qualityLevel: 'Standard (Human + AI)',
      assignedTeam: 'Urban Vision Team',
      priority: 'Medium',
      visionTechnique: '2D Bounding Box',
      visionTechniques: ['2D Bounding Box'],
      targetClasses: [],
      targetObjectsText: '',
    });
  };

  const handleResetProjectSection = () => {
    if (onResetProject) {
      onResetProject();
    } else {
      onChange({
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
    }
  };

  // Toggle Annotation Type checkbox
  const toggleAnnotationType = (type: AnnotationType) => {
    if (formData.annotationTypes.includes(type)) {
      const remainingTypes = formData.annotationTypes.filter((t) => t !== type);
      const willHaveObjDet =
        remainingTypes.includes('Object Detection & Labeling') ||
        remainingTypes.includes('Object Detection');
      const willHavePii = remainingTypes.includes('PII Masking');

      onChange({
        annotationTypes: remainingTypes,
        ...(willHaveObjDet
          ? {
              targetClasses: formData.targetClasses || [],
              targetObjectsText: (formData.targetClasses || []).map((c) => c.name).join(', '),
            }
          : willHavePii
          ? { targetClasses: [], targetObjectsText: '' }
          : { targetClasses: [], targetObjectsText: '' }),
      });
    } else {
      const nextTypes = [...formData.annotationTypes, type];
      if (type === 'PII Masking') {
        onChange({
          annotationTypes: nextTypes,
          targetClasses: [],
          targetObjectsText: '',
        });
      } else if (type === 'Object Detection & Labeling') {
        const nextClasses = formData.targetClasses || [];
        onChange({
          annotationTypes: nextTypes,
          ...(isImageAnnotation
            ? { targetClasses: [], targetObjectsText: formData.targetObjectsText || '' }
            : { targetClasses: nextClasses }),
        });
      } else {
        onChange({
          annotationTypes: nextTypes,
        });
      }
    }
  };

  const visionTechniques: {
    title: VisionAnnotationTechnique;
    description: string;
  }[] = [
    {
      title: '2D Bounding Box',
      description: 'Axis-aligned rectangular bounding',
    },
    {
      title: 'Polygon Segmentation',
      description: 'Multi-point contour delineation',
    },
    {
      title: 'Keypoints / Landmarks',
      description: 'Pose & critical coordinate anchors',
    },
    {
      title: 'Polyline',
      description: 'Continuous multi-segment linear path and boundaries',
    },
  ];

  // Drag and drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const addSelectedFiles = (files: File[]) => {
    if (isImageAnnotation) {
      const invalidFile = files.find((file) => !isSupportedImageUploadFile(file));
      if (invalidFile) {
        setUploadError(
          invalidFile.size <= 0
            ? `${invalidFile.name} is empty. Select a non-empty image or ZIP archive.`
            : `${invalidFile.name} is not a supported image or ZIP file.`
        );
        return;
      }
      setUploadError(null);
    }

    const newFiles = files.map((file) => ({
      name: file.name,
      size: (file.size / (1024 * 1024)).toFixed(2) + ' MB',
      type: file.name.toLowerCase().endsWith('.zip')
        ? 'application/zip'
        : file.type || (isImageAnnotation ? 'image/jpeg' : 'text/plain'),
      // Keep the File object for every upload mode so text/document uploads
      // can be read and analyzed after the project is created.
      file,
    }));
    const currentFiles = formData.uploadedFiles || [];
    const combinedFiles = [...currentFiles];
    newFiles.forEach((nf) => {
      const alreadyExists = combinedFiles.some(
        (cf) => cf.name === nf.name && cf.file?.size === nf.file?.size
      );
      if (!alreadyExists) {
        combinedFiles.push(nf);
      }
    });

    onChange({
      numberOfFiles: combinedFiles.length,
      uploadedFiles: combinedFiles,
    });
  };

  const handleRemoveUploadedFile = (indexToRemove: number) => {
    const updated = (formData.uploadedFiles || []).filter((_, idx) => idx !== indexToRemove);
    onChange({
      uploadedFiles: updated,
      numberOfFiles: updated.length,
    });
  };

  const handleClearAllUploadedFiles = () => {
    onChange({
      uploadedFiles: [],
      numberOfFiles: 0,
    });
  };

  const formatFileSize = (fileObj?: File, sizeStr?: string) => {
    if (fileObj && typeof fileObj.size === 'number') {
      const bytes = fileObj.size;
      if (bytes < 1024) return `${bytes} B`;
      if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
      return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
    }
    return sizeStr || '';
  };

  const renderUploadedFilesShowcase = () => {
    const filesList = formData.uploadedFiles || [];
    if (filesList.length === 0) return null;

    const totalBytes = filesList.reduce((acc, item) => acc + (item.file?.size || 0), 0);
    const formattedTotal =
      totalBytes < 1024 * 1024
        ? `${(totalBytes / 1024).toFixed(1)} KB`
        : `${(totalBytes / (1024 * 1024)).toFixed(2)} MB`;

    return (
      <div id="uploaded-files-showcase" className="mt-3 rounded-xl border border-[#E2DDD5] bg-[#FAF8F5] p-3.5 shadow-2xs space-y-2.5">
        <div className="flex items-center justify-between pb-2 border-b border-[#EBE6DE]">
          <div className="flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
              <Check className="h-3 w-3 stroke-[2.5]" />
            </span>
            <span className="text-xs font-bold text-slate-800">
              Uploaded Files ({filesList.length})
            </span>
            <span className="text-[11px] font-medium text-slate-500">
              • Total: {formattedTotal}
            </span>
          </div>
          <button
            type="button"
            onClick={handleClearAllUploadedFiles}
            className="text-[11px] font-semibold text-slate-400 hover:text-[#E31837] transition cursor-pointer"
          >
            Clear all
          </button>
        </div>

        <div className="max-h-52 overflow-y-auto space-y-1.5 pr-1">
          {filesList.map((item, idx) => {
            const ext = item.name.split('.').pop()?.toUpperCase() || 'FILE';
            const isImg = /\.(jpg|jpeg|png|webp|bmp|gif)$/i.test(item.name);
            const isZip = item.name.toLowerCase().endsWith('.zip');
            return (
              <div
                key={`${item.name}-${idx}`}
                className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-white border border-[#EBE6DE] hover:border-[#D8D2C7] transition shadow-2xs"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-100 text-slate-600 shrink-0">
                    {isImg ? (
                      <ImageIcon className="h-3.5 w-3.5 text-blue-600" />
                    ) : isZip ? (
                      <Box className="h-3.5 w-3.5 text-amber-600" />
                    ) : (
                      <FileText className="h-3.5 w-3.5 text-emerald-600" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-slate-800 truncate" title={item.name}>
                      {item.name}
                    </p>
                    <p className="text-[10px] text-slate-400">
                      {formatFileSize(item.file, item.size)} • <span className="font-semibold text-slate-500">{ext}</span>
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                    Ready
                  </span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRemoveUploadedFile(idx);
                    }}
                    className="p-1 rounded text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition cursor-pointer"
                    title="Remove file"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length > 0) {
      addSelectedFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      addSelectedFiles(Array.from(e.target.files));
      e.currentTarget.value = '';
    }
  };

  const selectedImageFiles = (formData.uploadedFiles || [])
    .map((item) => item.file)
    .filter((file): file is File => file instanceof File);

  const handleConnectSource = () => {
    if (connectUrlInput.trim()) {
      setConnectedSource(connectUrlInput);
      onChange({ cloudStorageUrl: connectUrlInput });
    }
  };

  // Helper icons for project types
  const getProjectTypeIcon = (type: ProjectType) => {
    switch (type) {
      case 'Video Annotation':
        return <Video className="h-4 w-4 text-[#E31837] shrink-0" />;
      case 'Image Annotation':
        return <ImageIcon className="h-4 w-4 text-[#E31837] shrink-0" />;
      case 'Text Annotation':
        return <FileText className="h-4 w-4 text-[#E31837] shrink-0" />;
      case 'Audio Annotation':
        return <Mic className="h-4 w-4 text-[#E31837] shrink-0" />;
      default:
        return <FolderKanban className="h-4 w-4 text-slate-400 shrink-0" />;
    }
  };

  const getAnnotationOptions = (
    projectType: ProjectType,
    format?: MediaFormat
  ): AnnotationType[] => {
    // 1. Image Annotation -> Object Detection & Labeling and PII Masking
    if (projectType === 'Image Annotation' || (!projectType && format === 'Image')) {
      return ['Object Detection & Labeling', 'PII Masking'];
    }
    // 2. Text Annotation -> Sentiment Annotation, NER Annotation, Text Classification, Relation Extraction
    if (projectType === 'Text Annotation' || (!projectType && format === 'Text')) {
      return [
        'Sentiment Annotation',
        'NER Annotation',
        'Text Classification',
        'Relation Extraction',
      ];
    }
    // 3. Video Annotation
    if (projectType === 'Video Annotation' || (!projectType && format === 'Video')) {
      return ['Object Detection', 'Object Tracking', 'Segmentation'];
    }
    // 4. Audio Annotation
    if (projectType === 'Audio Annotation' || (!projectType && format === 'Audio')) {
      return ['Speech-to-Text', 'Audio Classification'];
    }
    return [];
  };

  const annotationTypeOptions = getAnnotationOptions(
    formData.projectType,
    formData.mediaFormat
  );

  const isSingleChoice =
    formData.projectType === 'Text Annotation' ||
    formData.projectType === 'Image Annotation' ||
    (!formData.projectType &&
      (formData.mediaFormat === 'Text' || formData.mediaFormat === 'Image')) ||
    (annotationTypeOptions.includes('Object Detection & Labeling') &&
      annotationTypeOptions.includes('PII Masking')) ||
    (annotationTypeOptions.includes('Sentiment Annotation') &&
      annotationTypeOptions.includes('NER Annotation'));

  const dataTypeOptions: DataTypeOption[] = isTextAnnotation
    ? ['Files Upload', 'Input Text Field']
    : ['Files Upload', 'Cloud Storage'];

  const TEXT_OUTPUT_FORMAT_OPTIONS: OutputFormat[] = [
    'JSON',
    'JSONL',
    'CoNLL',
    'BIO Format',
    'CSV',
    'TSV',
  ];

  const VISION_OUTPUT_FORMAT_OPTIONS: OutputFormat[] = [
    'COCO JSON',
    'Pascal VOC XML',
    'YOLO TXT',
    'GeoJSON',
    'TFRecord',
    'Custom JSON',
  ];

  const isTextOutputFormat = (fmt: string) =>
    ['JSON', 'JSONL', 'CoNLL', 'BIO Format', 'CSV', 'TSV', 'Json', 'jsonl'].includes(fmt);

  const outputFormatOptions: OutputFormat[] = isTextAnnotation
    ? TEXT_OUTPUT_FORMAT_OPTIONS
    : VISION_OUTPUT_FORMAT_OPTIONS;

  const imageInstructionField = showImageInstruction ? (
    <div id="identification-instruction-container">
      <label
        htmlFor="input-image-identification-instruction"
        className="block text-xs font-semibold text-slate-700 mb-2"
      >
        What should be identified? <span className="text-rose-500">*</span>
      </label>
      <textarea
        id="input-image-identification-instruction"
        required
        rows={4}
        value={formData.targetObjectsText ?? ''}
        onChange={(e) => {
          const text = e.target.value;
          onChange({ targetObjectsText: text });
          scheduleTargetClassExtraction(text);
        }}
        placeholder="Describe what should be identified in the images..."
        className="w-full resize-y rounded-lg border border-[#E2DDD5] bg-white px-3.5 py-2.5 text-xs sm:text-sm text-slate-800 placeholder-slate-400 focus:border-[#E31837] focus:outline-none focus:ring-2 focus:ring-[#E31837]/15 shadow-2xs"
      />
    </div>
  ) : null;

  return (
    <div id="intake-form-container" className="space-y-8 font-sans">
      {/* ---------------- 1. Project Details ---------------- */}
      <section
        id="section-project-details"
        className="rounded-xl border border-[#E2DDD5] bg-white p-5 sm:p-6 shadow-xs"
      >
        <div className="flex items-center justify-between pb-4 border-b border-[#F0EBE3]">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-[#E31837]/10 text-[#E31837]">
              <FolderKanban className="h-4 w-4" />
            </div>
            <h2 className="text-base font-bold text-slate-900">1. Project Details</h2>
          </div>

          <button
            type="button"
            id="btn-reset-project-section"
            onClick={handleResetProjectSection}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#E2DDD5] bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 hover:text-[#E31837] hover:border-[#E31837]/40 hover:bg-red-50/50 transition shadow-2xs cursor-pointer active:scale-95"
            title="Reset project inputs"
          >
            <RotateCcw className="h-3 w-3 stroke-[2.2]" />
            <span>Reset</span>
          </button>
        </div>

        <div className="mt-5 space-y-5">
          {/* Row 1: Project Name and Project Type */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {/* Project Name */}
            <div>
              <label
                htmlFor="input-project-name"
                className="block text-xs font-semibold text-slate-700 mb-1.5"
              >
                Project Name <span className="text-rose-500">*</span>
              </label>
              <input
                id="input-project-name"
                type="text"
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="off"
                spellCheck={false}
                data-lpignore="true"
                data-form-type="other"
                value={formData.projectName}
                onChange={(e) => onChange({ projectName: e.target.value })}
                placeholder=""
                className="w-full rounded-lg border border-[#E2DDD5] px-3.5 py-2.5 text-sm text-slate-800 focus:border-[#E31837] focus:outline-none focus:ring-2 focus:ring-[#E31837]/15 bg-white"
              />
            </div>

            {/* Project Type (moved to place of Description) */}
            <div>
              <label
                htmlFor="select-project-type"
                className="block text-xs font-semibold text-slate-700 mb-1.5"
              >
                Project Type <span className="text-rose-500">*</span>
              </label>
              <div className="relative flex items-center">
                <div className="pointer-events-none absolute left-3 flex items-center">
                  {getProjectTypeIcon(formData.projectType)}
                </div>
                <select
                  id="select-project-type"
                  value={formData.projectType}
                  onChange={(e) => {
                    const newProjType = e.target.value as ProjectType;
                    let targetFormat: MediaFormat = formData.mediaFormat;
                    if (newProjType === 'Image Annotation') targetFormat = 'Image';
                    else if (newProjType === 'Video Annotation') targetFormat = 'Video';
                    else if (newProjType === 'Text Annotation') targetFormat = 'Text';
                    else if (newProjType === 'Audio Annotation') targetFormat = 'Audio';

                    const newOptions = getAnnotationOptions(newProjType, targetFormat);
                    let validSelected = formData.annotationTypes.filter((t) =>
                      newOptions.includes(t)
                    );
                    // For Text Annotation or Image Annotation, only 1 option can be selected at a time
                    if (
                      (newProjType === 'Text Annotation' || newProjType === 'Image Annotation') &&
                      validSelected.length > 1
                    ) {
                      validSelected = [validSelected[0]];
                    }

                    let nextDataType = formData.dataType;
                    if (newProjType === 'Text Annotation') {
                      if (formData.dataType === 'Cloud Storage' || !formData.dataType) {
                        nextDataType = 'Files Upload';
                      }
                    } else if (formData.dataType === 'Input Text Field') {
                      nextDataType = 'Files Upload';
                    }

                    let nextOutputFormat = formData.expectedOutputFormat;
                    if (newProjType === 'Text Annotation') {
                      if (!isTextOutputFormat(nextOutputFormat)) {
                        nextOutputFormat = 'JSON';
                      }
                    } else if (newProjType) {
                      if (isTextOutputFormat(nextOutputFormat) || !nextOutputFormat) {
                        nextOutputFormat = 'COCO JSON';
                      }
                    }

                    onChange({
                      projectType: newProjType,
                      mediaFormat: targetFormat,
                      annotationTypes: validSelected,
                      dataType: nextDataType,
                      expectedOutputFormat: nextOutputFormat,
                      visionTechnique:
                        newProjType === 'Image Annotation'
                          ? '2D Bounding Box'
                          : newProjType === 'Text Annotation'
                          ? ''
                          : formData.visionTechnique,
                      visionTechniques:
                        newProjType === 'Image Annotation'
                          ? ['2D Bounding Box']
                          : newProjType === 'Text Annotation'
                          ? []
                          : formData.visionTechniques,
                      ...(newProjType === 'Image Annotation'
                        ? {
                            targetClasses: [],
                            targetObjectsText: formData.targetObjectsText || '',
                          }
                        : validSelected.includes('Object Detection & Labeling') ||
                      validSelected.includes('Segmentation') ||
                      validSelected.includes('Classification')
                        ? {
                            targetClasses: formData.targetClasses || [],
                            targetObjectsText: (formData.targetClasses || [])
                              .map((c) => c.name)
                              .join(', '),
                          }
                        : { targetClasses: [], targetObjectsText: '' }),
                    });
                    if (newProjType === 'Image Annotation' && validSelected.includes('Object Detection & Labeling')) {
                      scheduleTargetClassExtraction(formData.targetObjectsText || '', true);
                    }
                  }}
                  className="w-full appearance-none rounded-lg border border-[#E2DDD5] bg-white py-2.5 pl-9 pr-8 text-sm text-slate-800 focus:border-[#E31837] focus:outline-none focus:ring-2 focus:ring-[#E31837]/15 cursor-pointer"
                >
                  <option value="">------select------</option>
                  <option value="Video Annotation">Video Annotation</option>
                  <option value="Image Annotation">Image Annotation</option>
                  <option value="Text Annotation">Text Annotation</option>
                  <option value="Audio Annotation">Audio Annotation</option>
                </select>
                <ChevronDown className="pointer-events-none absolute right-3 h-4 w-4 text-slate-400" />
              </div>
            </div>
          </div>

          {imageInstructionField}
        </div>
      </section>

      {/* ---------------- 2. Annotation Settings ---------------- */}
      <section
        id="section-annotation-settings"
        className="rounded-xl border border-[#E2DDD5] bg-white p-5 sm:p-6 shadow-xs"
      >
        <div className="flex items-center gap-2.5 pb-4 border-b border-[#F0EBE3]">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-[#E31837]/10 text-[#E31837]">
            <Settings className="h-4 w-4" />
          </div>
          <h2 className="text-base font-bold text-slate-900">2. Annotation Settings</h2>
        </div>

        <div className="mt-5 space-y-5">
          {/* Annotation Type(s) Selection */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-xs font-semibold text-slate-700">
                {isSingleChoice ? 'Annotation Type' : 'Annotation Type(s)'}{' '}
                <span className="text-rose-500">*</span>
              </label>
              {formData.projectType && (
                <span className="text-[11px] font-medium text-slate-500">
                  Options for <span className="text-slate-800 font-semibold">{formData.projectType}</span>
                </span>
              )}
            </div>

            <div id="annotation-types-options-container">
              {annotationTypeOptions.length > 0 ? (
                <div className="flex flex-wrap items-center gap-3.5 sm:gap-4">
                  {annotationTypeOptions.map((type) => {
                    const checked = isSingleChoice
                      ? formData.annotationTypes.length > 0 && formData.annotationTypes[0] === type
                      : formData.annotationTypes.includes(type);

                    if (isSingleChoice) {
                      return (
                        <label
                          key={type}
                          id={`radio-label-${type.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
                          className={`flex items-center gap-2.5 px-3.5 py-2 rounded-lg border transition cursor-pointer select-none text-xs sm:text-sm font-medium ${
                            checked
                              ? 'border-[#E31837] bg-red-50/70 text-[#E31837] font-semibold ring-1 ring-[#E31837]/20 shadow-2xs'
                              : 'border-[#E2DDD5] bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50'
                          }`}
                        >
                          <input
                            type="radio"
                            id={`radio-input-${type.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
                            name="annotationTypeOption"
                            checked={checked}
                            onChange={() => {
                              const supportsTargets =
                                type === 'Object Detection & Labeling' ||
                                type === 'Segmentation' ||
                                type === 'Classification';
                              onChange({
                                annotationTypes: [type],
                                ...(supportsTargets && isImageAnnotation
                                  ? {
                                      targetClasses: [],
                                      targetObjectsText: formData.targetObjectsText || '',
                                    }
                                  : supportsTargets
                                  ? {
                                      targetClasses: formData.targetClasses || [],
                                      targetObjectsText: (formData.targetClasses || [])
                                        .map((c) => c.name)
                                        .join(', '),
                                    }
                                  : { targetClasses: [], targetObjectsText: '' }),
                              });
                              if (type === 'Object Detection & Labeling' && isImageAnnotation) {
                                scheduleTargetClassExtraction(formData.targetObjectsText || '', true);
                              }
                            }}
                            className="sr-only"
                          />
                          <div
                            className={`flex h-4 w-4 items-center justify-center rounded-full border transition shrink-0 ${
                              checked
                                ? 'border-[#E31837] bg-white ring-2 ring-[#E31837]/30'
                                : 'border-[#D0C9BE] bg-white hover:border-slate-400'
                            }`}
                          >
                            {checked && (
                              <div className="h-2 w-2 rounded-full bg-[#E31837]" />
                            )}
                          </div>
                          <span>{type}</span>
                        </label>
                      );
                    }

                    return (
                      <label
                        key={type}
                        id={`checkbox-label-${type.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
                        className={`flex items-center gap-2.5 px-3.5 py-2 rounded-lg border transition cursor-pointer select-none text-xs sm:text-sm font-medium ${
                          checked
                            ? 'border-[#E31837] bg-red-50/70 text-[#E31837] font-semibold ring-1 ring-[#E31837]/20 shadow-2xs'
                            : 'border-[#E2DDD5] bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleAnnotationType(type)}
                          className="sr-only"
                        />
                        <div
                          className={`flex h-4 w-4 items-center justify-center rounded border transition ${
                            checked
                              ? 'border-[#E31837] bg-[#E31837] text-white'
                              : 'border-[#D0C9BE] bg-white hover:border-slate-400'
                          }`}
                        >
                          {checked && <Check className="h-3 w-3 stroke-[3]" />}
                        </div>
                        <span>{type}</span>
                      </label>
                    );
                  })}
                </div>
              ) : (
                <div className="rounded-lg border border-dashed border-[#E2DDD5] bg-slate-50/70 px-4 py-3 text-xs text-slate-500 flex items-center gap-2">
                  <span>Please select a <strong>Project Type</strong> in Section 1 (e.g. <em>Image Annotation</em> or <em>Text Annotation</em>) to configure available annotation types.</span>
                </div>
              )}
            </div>
          </div>

          {isTextSentiment && (
            <div id="sentiment-analysis-level-container">
              <label htmlFor="sentiment-analysis-level" className="block text-xs font-semibold text-slate-700 mb-2">
                Analysis Level
              </label>
              <select
                id="sentiment-analysis-level"
                value={formData.sentimentAnalysisLevel || 'document'}
                onChange={(event) => onChange({ sentimentAnalysisLevel: event.target.value as 'document' | 'page' | 'paragraph' | 'sentence' })}
                className="w-full max-w-md appearance-none rounded-lg border border-[#E2DDD5] bg-white px-3.5 py-2.5 text-sm text-slate-800 focus:border-[#E31837] focus:outline-none focus:ring-2 focus:ring-[#E31837]/15"
              >
                <option value="document">Document-Level</option>
                <option value="page">Page-Level</option>
                <option value="paragraph">Paragraph-Level</option>
                <option value="sentence">Sentence-Level</option>
              </select>
              <p className="mt-1.5 text-[11px] text-slate-500">Choose where sentiment should be evaluated. Document-Level preserves the existing behavior.</p>
            </div>
          )}

          {isTextClassification && (
            <div id="classification-analysis-level-container">
              <label htmlFor="classification-analysis-level" className="block text-xs font-semibold text-slate-700 mb-2">
                Analysis Level
              </label>
              <select
                id="classification-analysis-level"
                value={formData.classificationAnalysisLevel || 'document'}
                onChange={(event) => onChange({ classificationAnalysisLevel: event.target.value as 'document' | 'page' | 'paragraph' | 'sentence' })}
                className="w-full max-w-md appearance-none rounded-lg border border-[#E2DDD5] bg-white px-3.5 py-2.5 text-sm text-slate-800 focus:border-[#E31837] focus:outline-none focus:ring-2 focus:ring-[#E31837]/15"
              >
                <option value="document">Document-Level</option>
                <option value="page">Page-Level</option>
                <option value="paragraph">Paragraph-Level</option>
                <option value="sentence">Sentence-Level</option>
              </select>
              <p className="mt-1.5 text-[11px] text-slate-500">Choose where categories should be predicted. Document-Level preserves the existing behavior.</p>
            </div>
          )}

          {showImageTargetClasses && (
            <div id="image-target-classes-container">
              <label className="block text-xs font-semibold text-slate-700 mb-2">
                Target Objects / Classes to Identify
              </label>
              <div className="flex flex-wrap items-center gap-2 sm:gap-2.5 mb-3">
                {activeImageClasses.map((item) => (
                  <div
                    key={item.id}
                    id={`image-target-class-pill-${item.id}`}
                    style={{ borderColor: `${item.color}50`, backgroundColor: `${item.color}0D` }}
                    className="inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs sm:text-sm font-medium transition select-none shadow-2xs"
                  >
                    <span className="h-2.5 w-2.5 rounded-full shrink-0 shadow-2xs" style={{ backgroundColor: item.color }} />
                    <span className="text-slate-800 font-medium">{item.name}</span>
                    <span className="text-[11px] text-slate-400 font-mono tracking-tight">[{item.shortcutIndex}]</span>
                    <button
                      type="button"
                      onClick={() => handleRemoveImageClass(item.id)}
                      className="text-slate-400 hover:text-slate-600 transition p-0.5 rounded hover:bg-slate-200/50 cursor-pointer ml-0.5"
                      title={`Remove ${item.name}`}
                    >
                      <X className="h-3 w-3 stroke-[2.5]" />
                    </button>
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-2.5">
                <input
                  type="text"
                  value={newImageClassName}
                  onChange={(e) => setNewImageClassName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleAddImageClass();
                    }
                  }}
                  placeholder="Add new object class..."
                  className="w-64 sm:w-80 rounded-lg border border-[#E2DDD5] bg-white px-3.5 py-2 text-xs sm:text-sm text-slate-800 placeholder-slate-400 focus:border-[#E31837] focus:outline-none focus:ring-2 focus:ring-[#E31837]/15 shadow-2xs"
                />
                <label
                  className="relative flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg border border-[#E2DDD5] bg-white p-1 hover:border-slate-300 transition shadow-2xs group"
                  title="Choose class color"
                >
                  <span className="h-5 w-5 rounded shrink-0 border border-black/10 transition group-hover:scale-105" style={{ backgroundColor: newImageClassColor }} />
                  <input type="color" value={newImageClassColor} onChange={(e) => setNewImageClassColor(e.target.value)} className="sr-only" />
                </label>
                <button
                  type="button"
                  onClick={handleAddImageClass}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[#E2DDD5] bg-white hover:bg-slate-50 px-3.5 py-2 text-xs sm:text-sm font-semibold text-slate-700 hover:text-slate-900 transition shadow-2xs cursor-pointer"
                >
                  <Plus className="h-3.5 w-3.5 text-slate-500" />
                  <span>Add Class</span>
                </button>
              </div>
            </div>
          )}

          {/* User-provided identification instruction */}
          {showTargetClasses && (
            <div id="identification-instruction-container">
              <label
                htmlFor={isTextAnnotation ? 'input-target-objects-free-text' : undefined}
                className="block text-xs font-semibold text-slate-700 mb-2"
              >
                {isTextAnnotation ? 'Target Objects (NER Entities)' : 'What should be identified?'}
                {!isTextAnnotation && <span className="text-rose-500"> *</span>}
              </label>

            <>
              <div className="space-y-3">
                <div className="relative">
                  <input
                    id="input-target-objects-free-text"
                    type="text"
                    value={formData.targetObjectsText ?? ''}
                    onChange={(e) => {
                      const textVal = e.target.value;
                      const parsed = textVal
                        .split(/[,;\n]+/)
                        .map((s) => s.trim())
                        .filter(Boolean);
                      const updatedClasses: TargetObjectClass[] = parsed.map((name, idx) => ({
                        id: `cls-text-${idx + 1}`,
                        name,
                        color: [
                          '#2563EB',
                          '#10B981',
                          '#F59E0B',
                          '#8B5CF6',
                          '#EF4444',
                          '#06B6D4',
                        ][idx % 6],
                        shortcutIndex: idx + 1,
                      }));
                      onChange({
                        targetObjectsText: textVal,
                        targetClasses: updatedClasses,
                      });
                    }}
                    placeholder="Enter target objects / entities separated by commas..."
                    className="w-full rounded-lg border border-[#E2DDD5] bg-white px-3.5 py-2.5 text-xs sm:text-sm text-slate-800 placeholder-slate-400 focus:border-[#E31837] focus:outline-none focus:ring-2 focus:ring-[#E31837]/15 shadow-2xs"
                  />
                </div>

                {formData.targetClasses && formData.targetClasses.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2">
                    {formData.targetClasses.map((cls) => (
                      <span
                        key={cls.id}
                        id={`text-target-chip-${cls.id}`}
                        className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium bg-slate-50 text-slate-700 border-slate-200 shadow-2xs"
                      >
                        <span
                          className="h-2 w-2 rounded-full shrink-0"
                          style={{ backgroundColor: cls.color }}
                        />
                        <span>{cls.name}</span>
                        <button
                          type="button"
                          onClick={() => {
                            const remaining = (formData.targetClasses || []).filter(
                              (c) => c.id !== cls.id
                            );
                            const newText = remaining.map((c) => c.name).join(', ');
                            onChange({
                              targetObjectsText: newText,
                              targetClasses: remaining,
                            });
                          }}
                          className="text-slate-400 hover:text-slate-600 ml-0.5 cursor-pointer"
                          title={`Remove ${cls.name}`}
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}
                <p className="text-[11px] text-slate-500">
                  Define target entity objects for Named Entity Recognition (NER). Enter multiple objects separated by commas.
                </p>
              </div>
            </>
          </div>
        )}
        </div>
      </section>

      {/* ---------------- 3. Tool Technique (Shown only for Object Detection & Labeling or PII Masking) ---------------- */}
      {showVisionTechniques && (
        <section
          id="section-tool-technique-classes"
          className="rounded-xl border border-[#E2DDD5] bg-white p-5 sm:p-6 shadow-xs"
        >
          <div className="flex items-center gap-2.5 pb-4 border-b border-[#F0EBE3]">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-[#E31837]/10 text-[#E31837]">
              <Layers className="h-4 w-4" />
            </div>
            <h2 className="text-base font-bold text-slate-900">3. Tool Technique</h2>
          </div>

          <div className="mt-4 space-y-4">
            {/* Vision Annotation Technique */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-2">
                Vision Annotation Technique
                <span className="ml-2 font-normal text-slate-500">Select one or more</span>
              </label>
              <div className="mb-3 flex items-center justify-between text-[11px] text-slate-500">
                <span>Choose all tools needed for this image project.</span>
                <span className="font-semibold text-slate-700">
                  {(formData.visionTechniques ?? (formData.visionTechnique ? [formData.visionTechnique] : [])).length}{' '}
                  selected
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                {visionTechniques.map((tech) => {
                  const selectedTechniques = formData.visionTechniques ?? (
                    formData.visionTechnique ? [formData.visionTechnique] : []
                  );
                  const isSelected = selectedTechniques.includes(tech.title);
                  return (
                    <button
                      key={tech.title}
                      type="button"
                      onClick={() => {
                        const nextTechniques = isSelected
                          ? selectedTechniques.filter((item) => item !== tech.title)
                          : [...selectedTechniques, tech.title];
                        onChange({
                          visionTechniques: nextTechniques,
                          // Keep the first selected tool available to older consumers.
                          visionTechnique: nextTechniques[0] || '',
                        });
                      }}
                      className={`rounded-lg px-3 py-2.5 sm:px-3.5 sm:py-2.5 text-left transition cursor-pointer relative ${
                        isSelected
                          ? 'border-2 border-[#E31837] bg-red-50/40 shadow-xs ring-1 ring-[#E31837]/20'
                          : 'border border-[#E2DDD5] bg-white hover:border-slate-300 hover:bg-slate-50/50'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-1">
                        <div
                          className={`text-xs sm:text-sm ${
                            isSelected ? 'font-bold text-[#E31837]' : 'font-semibold text-slate-800'
                          }`}
                        >
                          {tech.title}
                        </div>
                        {isSelected && (
                          <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-[#E31837] text-white shrink-0">
                            <Check className="h-2 w-2 stroke-[3]" />
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] sm:text-xs text-slate-500 mt-1 leading-snug line-clamp-2">
                        {tech.description}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* ---------------- Data Section ---------------- */}
      <section
        id="section-data-media"
        className="rounded-xl border border-[#E2DDD5] bg-white p-5 sm:p-6 shadow-xs"
      >
        <div className="flex items-center gap-2.5 pb-4 border-b border-[#F0EBE3] mb-5">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-[#E31837]/10 text-[#E31837]">
            <Database className="h-4 w-4" />
          </div>
          <h2 className="text-base font-bold text-slate-900">
            {showVisionTechniques ? '4. Data' : '3. Data'}
          </h2>
        </div>

        {/* Radio options for Data Type */}
        <div className="mb-5">
          <label className="block text-xs font-semibold text-slate-700 mb-2">
            Data Type <span className="text-rose-500">*</span>
          </label>
          <div className="flex flex-wrap items-center gap-4 sm:gap-6 pt-1">
            {dataTypeOptions.map((type) => (
              <label
                key={type}
                id={`radio-label-${type.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
                className="flex items-center gap-2 cursor-pointer text-xs sm:text-sm font-medium text-slate-700"
              >
                <input
                  type="radio"
                  name="dataType"
                  value={type}
                  checked={
                    formData.dataType === type ||
                    (!formData.dataType && type === 'Files Upload')
                  }
                  onChange={() => onChange({ dataType: type })}
                  className="h-4 w-4 text-[#E31837] border-[#D0C9BE] focus:ring-[#E31837] accent-[#E31837] cursor-pointer"
                />
                <span>{type}</span>
              </label>
            ))}
          </div>
        </div>

        {/* Upload or Link Area */}
        {isTextAnnotation ? (
          formData.dataType === 'Input Text Field' ? (
            /* Text Annotation: Input Text Field */
            <div
              id="input-text-container"
              className="mb-5 rounded-xl border border-[#E2DDD5] bg-white p-5 shadow-xs space-y-3"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-[#E31837]" />
                  <label
                    htmlFor="textarea-input-text"
                    className="text-xs sm:text-sm font-semibold text-slate-800"
                  >
                    Input Text Field <span className="text-rose-500">*</span>
                  </label>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-slate-400 font-mono">
                    {(formData.inputText || '').trim().split(/\s+/).filter(Boolean).length} words &bull; {(formData.inputText || '').length} characters
                  </span>
                  {formData.inputText && (
                    <button
                      type="button"
                      onClick={() => onChange({ inputText: '' })}
                      className="text-[11px] text-slate-400 hover:text-[#E31837] underline cursor-pointer transition"
                    >
                      Clear
                    </button>
                  )}
                </div>
              </div>

              <textarea
                id="textarea-input-text"
                rows={5}
                value={formData.inputText || ''}
                onChange={(e) => {
                  const text = e.target.value;
                  const wordCount = text.trim().split(/\s+/).filter(Boolean).length;
                  onChange({
                    inputText: text,
                    numberOfFiles: Math.max(1, wordCount > 0 ? 1 : 0),
                  });
                }}
                placeholder="Paste or type text documents, user reviews, medical notes, or raw sentences to annotate..."
                className="w-full rounded-lg border border-[#E2DDD5] p-3 text-xs sm:text-sm text-slate-800 placeholder-slate-400 focus:border-[#E31837] focus:outline-none focus:ring-2 focus:ring-[#E31837]/15 bg-white font-sans leading-relaxed resize-y shadow-2xs"
              />
            </div>
          ) : (
            /* Text Annotation: Files Upload (Full Width, cloud storage card removed) */
            <div className="mb-5">
              <div
                id="drag-drop-zone"
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`flex flex-col items-center justify-center rounded-xl border border-dashed py-3.5 px-4 sm:py-4 sm:px-6 text-center transition cursor-pointer ${
                  isDragging
                    ? 'border-[#E31837] bg-[#E31837]/10 scale-[0.99]'
                    : 'border-[#E31837]/35 bg-[#E31837]/5 hover:border-[#E31837]/60 hover:bg-[#E31837]/10'
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".txt,.csv,.json,.tsv,.docx,.pdf"
                  className="hidden"
                  onChange={handleFileInputChange}
                />
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white text-[#E31837] mb-1.5 shadow-2xs border border-[#E2DDD5]">
                  <UploadCloud className="h-4 w-4 stroke-[2]" />
                </div>
                <p className="text-xs sm:text-sm text-slate-700 font-medium">
                  Drag and drop text files here, or{' '}
                  <span className="text-[#E31837] font-semibold underline underline-offset-2">
                    click to upload
                  </span>
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Supports TXT, CSV, JSON, TSV, DOCX, PDF (Max 100 MB per document)
                </p>
              </div>
              {renderUploadedFilesShowcase()}
            </div>
          )
        ) : formData.dataType === 'Cloud Storage' ? (
          /* Non-Text Annotation: Dedicated Cloud Storage Box */
          <div className="mb-5">
            <div
              id="source-link-card"
              className="flex flex-col justify-center rounded-xl border border-[#E2DDD5] bg-white p-5 sm:p-6 shadow-2xs space-y-4"
            >
              <div className="flex items-center justify-between pb-3 border-b border-[#F0EBE3]">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#E31837]/10 text-[#E31837]">
                    <Cloud className="h-4 w-4" />
                  </div>
                  <div>
                    <h3 className="text-xs sm:text-sm font-semibold text-slate-800">
                      Cloud Storage Bucket
                    </h3>
                    <p className="text-[11px] text-slate-500">
                      Connect your secure AWS S3, Google Cloud Storage, or Azure Blob bucket
                    </p>
                  </div>
                </div>
                <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
                  Read-Only IAM / SAS
                </span>
              </div>

              <div className="space-y-3">
                <label
                  htmlFor="input-data-source-url"
                  className="block text-xs font-semibold text-slate-700"
                >
                  Cloud Storage Bucket URL / S3 URI <span className="text-rose-500">*</span>
                </label>
                <div className="flex flex-col sm:flex-row gap-2.5">
                  <input
                    id="input-data-source-url"
                    type="text"
                    value={connectUrlInput}
                    onChange={(e) => setConnectUrlInput(e.target.value)}
                    placeholder="e.g. s3://my-enterprise-bucket/image-dataset/ or gs://raw-images/"
                    className="flex-1 rounded-lg border border-[#E2DDD5] px-3.5 py-2.5 text-xs sm:text-sm text-slate-800 placeholder-slate-400 focus:border-[#E31837] focus:outline-none focus:ring-2 focus:ring-[#E31837]/15 bg-white shadow-2xs"
                  />
                  <button
                    id="connect-source-btn"
                    type="button"
                    onClick={handleConnectSource}
                    className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-[#E31837] px-4 py-2.5 text-xs sm:text-sm font-semibold text-white hover:bg-[#C1122C] cursor-pointer transition shadow-2xs shrink-0"
                  >
                    <Link2 className="h-4 w-4" />
                    <span>Connect</span>
                  </button>
                </div>

                <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1">
                  <span>Supported: AWS S3 &bull; GCP Cloud Storage &bull; Azure Blob</span>
                  {connectedSource && (
                    <span className="flex items-center gap-1.5 text-xs text-[#247153] font-medium">
                      <FileCheck className="h-3.5 w-3.5" /> Connected: {connectedSource.substring(0, 30)}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        ) : (
          /* Non-Text Annotation: Files Upload (Full Width, Cloud storage card hidden) */
          <div className="mb-5">
            <div
              id="drag-drop-zone"
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`flex flex-col items-center justify-center rounded-xl border border-dashed py-3.5 px-4 sm:py-4 sm:px-6 text-center transition cursor-pointer ${
                isDragging
                  ? 'border-[#E31837] bg-[#E31837]/10 scale-[0.99]'
                  : 'border-[#E31837]/35 bg-[#E31837]/5 hover:border-[#E31837]/60 hover:bg-[#E31837]/10'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept={
                  isImageAnnotation
                    ? SUPPORTED_IMAGE_UPLOAD_EXTENSIONS.join(',')
                    : '.mp4,.mov,.avi,.mkv,.webm,.zip'
                }
                className="hidden"
                onChange={handleFileInputChange}
              />
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white text-[#E31837] mb-1.5 shadow-2xs border border-[#E2DDD5]">
                <UploadCloud className="h-4 w-4 stroke-[2]" />
              </div>
              <p className="text-xs sm:text-sm text-slate-700 font-medium">
                Drag and drop files here, or{' '}
                <span className="text-[#E31837] font-semibold underline underline-offset-2">
                  click to upload
                </span>
              </p>
              <p className="text-[11px] text-slate-400 mt-0.5">
                {isImageAnnotation
                  ? 'Supports JPG, PNG, WEBP, ZIP archives (Max 10 GB per file)'
                  : 'Supports MP4, MOV, JPG, PNG, ZIP archives (Max 10 GB per file)'}
              </p>
            </div>
            {isImageAnnotation && uploadError && (
              <p role="alert" className="mt-2 text-xs text-rose-600">
                {uploadError}
              </p>
            )}
            {renderUploadedFilesShowcase()}
          </div>
        )}

        {/* Number of Files & Expected Output Format (side by side) */}
        <div className={`grid grid-cols-1 ${showModelSelection ? 'lg:grid-cols-3' : 'lg:grid-cols-2'} gap-5`}>
          {/* Number of Files / Records (hidden when Input Text Field is selected) */}
          {formData.dataType !== 'Input Text Field' && (
            <div id="number-of-files-container">
              <label
                htmlFor="input-number-of-files"
                className="block text-xs font-semibold text-slate-700 mb-1.5"
              >
                Number of Files <span className="text-rose-500">*</span>
              </label>
              <input
                id="input-number-of-files"
                type="number"
                min={1}
                value={
                  formData.numberOfFiles && formData.numberOfFiles > 0
                    ? formData.numberOfFiles
                    : selectedImageFiles.length
                }
                onChange={(e) => onChange({ numberOfFiles: Math.max(1, parseInt(e.target.value) || 1) })}
                className="w-full rounded-lg border border-[#E2DDD5] px-3.5 py-2.5 text-sm text-slate-800 focus:border-[#E31837] focus:outline-none focus:ring-2 focus:ring-[#E31837]/15 bg-white"
              />
            </div>
          )}

          {/* Expected Output Format */}
          <div id="expected-output-format-container">
            <label
              htmlFor="select-output-format"
              className="block text-xs font-semibold text-slate-700 mb-1.5"
            >
              Expected Output Format
            </label>
            <div className="relative flex items-center">
              <select
                id="select-output-format"
                value={
                  outputFormatOptions.includes(formData.expectedOutputFormat)
                    ? formData.expectedOutputFormat
                    : formData.expectedOutputFormat === 'Json'
                    ? 'JSON'
                    : formData.expectedOutputFormat === 'jsonl'
                    ? 'JSONL'
                    : outputFormatOptions[0]
                }
                onChange={(e) => onChange({ expectedOutputFormat: e.target.value as OutputFormat })}
                className="w-full appearance-none rounded-lg border border-[#E2DDD5] bg-white py-2.5 px-3.5 pr-8 text-sm text-slate-800 focus:border-[#E31837] focus:outline-none focus:ring-2 focus:ring-[#E31837]/15 cursor-pointer shadow-2xs hover:border-slate-300 transition"
              >
                {outputFormatOptions.map((fmt) => (
                  <option key={fmt} value={fmt}>
                    {fmt}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-3 h-4 w-4 text-slate-400" />
            </div>
          </div>

          {showModelSelection && (
            <div id="model-selection-container">
              <label
                htmlFor="select-model-selection"
                className="block text-xs font-semibold text-slate-700 mb-1.5"
              >
                Model Selection
              </label>
              <div className="relative flex items-center">
                <select
                  id="select-model-selection"
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="w-full appearance-none rounded-lg border border-[#E2DDD5] bg-white py-2.5 px-3.5 pr-8 text-sm text-slate-800 focus:border-[#E31837] focus:outline-none focus:ring-2 focus:ring-[#E31837]/15 cursor-pointer shadow-2xs hover:border-slate-300 transition"
                >
                  {modelSelectionOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-3 h-4 w-4 text-slate-400" />
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ---------------- Bottom Action Buttons ---------------- */}
      <div className="flex flex-wrap items-center justify-end gap-2 pt-2 pb-8">
        {aiCompleted && (
          <>
            <button type="button" onClick={onViewAiResults} className="rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 transition">
              AI Proceed Results
            </button>
            <button type="button" onClick={onViewProductionDashboard} className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 transition">
              Production Dashboard
            </button>
          </>
        )}
        <button
          id="btn-next-step"
          type="button"
          onClick={onNext}
          disabled={isLoading}
          className="flex items-center gap-2 rounded-lg bg-[#E31837] px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-[#C1122C] transition cursor-pointer disabled:opacity-60 disabled:cursor-wait"
        >
          <span>{isLoading ? 'AI Annotating...' : 'AI Annotate'}</span>
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};
