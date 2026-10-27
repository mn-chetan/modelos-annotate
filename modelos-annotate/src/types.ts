export type ProjectType = 
  | ''
  | 'Video Annotation'
  | 'Image Annotation'
  | 'Text Annotation'
  | 'Audio Annotation';

export type DomainUseCase =
  | ''
  | 'Insurance & Claims (AXA)'
  | 'Urban Traffic'
  | 'Autonomous Driving'
  | 'Retail & E-commerce'
  | 'Healthcare & Medical'
  | 'Security & Surveillance';

export type DataTypeOption = '' | 'Files Upload' | 'Cloud Storage' | 'Dataset Link' | 'Input Text Field';

export const SUPPORTED_IMAGE_UPLOAD_EXTENSIONS = [
  '.avif', '.bmp', '.jpeg', '.jpg', '.png', '.tif', '.tiff', '.webp', '.zip',
] as const;

export const isSupportedImageUploadFile = (file: File): boolean => {
  const extension = `.${file.name.split('.').pop()?.toLowerCase() || ''}`;
  return file.size > 0 && SUPPORTED_IMAGE_UPLOAD_EXTENSIONS.includes(extension as typeof SUPPORTED_IMAGE_UPLOAD_EXTENSIONS[number]);
};

export type MediaFormat = '' | 'Video' | 'Image' | 'Text' | 'Audio';

export type AnnotationType =
  | 'Object Detection & Labeling'
  | 'PII Masking'
  | 'NER Annotation'
  | 'All Text Features'
  | 'Sentiment Annotation'
  | 'Text Classification'
  | 'Relation Extraction'
  | 'Object Detection'
  | 'Object Tracking'
  | 'Classification'
  | 'Segmentation'
  | 'OCR'
  | 'Action Recognition'
  | 'Speech-to-Text'
  | 'Audio Classification'
  | '3D Bounding Box'
  | 'LiDAR Segmentation';

export type OutputFormat =
  | ''
  | 'COCO JSON'
  | 'Pascal VOC XML'
  | 'YOLO TXT'
  | 'GeoJSON'
  | 'TFRecord'
  | 'Custom JSON'
  | 'JSON'
  | 'Json'
  | 'JSONL'
  | 'jsonl'
  | 'CoNLL'
  | 'BIO Format'
  | 'CSV'
  | 'TSV';

export type QualityLevel =
  | ''
  | 'Standard (Human + AI)'
  | 'High Precision (Double Blind Consensus)'
  | 'Fast Automated (AI Pre-labeling)';

export type TeamName =
  | ''
  | 'Urban Vision Team'
  | 'Core Perception Team'
  | 'QA Annotation Guild'
  | 'Global Labeling Ops';

export type PriorityLevel = '' | 'Low' | 'Medium' | 'High' | 'Critical';

export type VisionAnnotationTechnique =
  | ''
  | '2D Bounding Box'
  | 'Polygon Segmentation'
  | 'Keypoints / Landmarks'
  | 'Polyline'
  | 'Semantic Brush';

export interface TargetObjectClass {
  id: string;
  name: string;
  color: string;
  shortcutIndex: number;
}

export const AXA_INSURANCE_DAMAGE_CLASSES: TargetObjectClass[] = [
  { id: 'cls-axa-1', name: 'Vehicle Dent & Deformation', color: '#EF4444', shortcutIndex: 1 },
  { id: 'cls-axa-2', name: 'Paint Scratch / Abrasion', color: '#F59E0B', shortcutIndex: 2 },
  { id: 'cls-axa-3', name: 'Broken Windshield / Glass', color: '#06B6D4', shortcutIndex: 3 },
  { id: 'cls-axa-4', name: 'Bumper Dislodgement', color: '#8B5CF6', shortcutIndex: 4 },
  { id: 'cls-axa-5', name: 'License Plate (PII Mask)', color: '#2563EB', shortcutIndex: 5 },
];

export const AXA_INSURANCE_NER_CLASSES: TargetObjectClass[] = [
  { id: 'cls-axa-ner-1', name: 'Policy Number', color: '#2563EB', shortcutIndex: 1 },
  { id: 'cls-axa-ner-2', name: 'Claim ID / FNOL Ref', color: '#EF4444', shortcutIndex: 2 },
  { id: 'cls-axa-ner-3', name: 'Claimant Name', color: '#10B981', shortcutIndex: 3 },
  { id: 'cls-axa-ner-4', name: 'Incident Date', color: '#F59E0B', shortcutIndex: 4 },
  { id: 'cls-axa-ner-5', name: 'Claim Amount Estimate', color: '#8B5CF6', shortcutIndex: 5 },
  { id: 'cls-axa-ner-6', name: 'Vehicle VIN / Reg', color: '#EC4899', shortcutIndex: 6 },
];

export interface IntakeFormData {
  projectName: string;
  description: string;
  projectType: ProjectType;
  domainUseCase: DomainUseCase;
  dataType: DataTypeOption;
  cloudStorageUrl: string;
  mediaFormat: MediaFormat;
  numberOfFiles: number;
  annotationTypes: AnnotationType[];
  expectedOutputFormat: OutputFormat;
  qualityLevel: QualityLevel;
  assignedTeam: TeamName;
  priority: PriorityLevel;
  dueDate: string;
  uploadedFiles?: { name: string; size: string; type: string; file?: File }[];
  visionTechnique?: VisionAnnotationTechnique;
  /** Selected vision tools. visionTechnique is retained as the primary/backward-compatible value. */
  visionTechniques?: VisionAnnotationTechnique[];
  targetClasses?: TargetObjectClass[];
  targetObjectsText?: string;
  inputText?: string;
  sentimentAnalysisLevel?: 'document' | 'page' | 'paragraph' | 'sentence';
  classificationAnalysisLevel?: 'document' | 'page' | 'paragraph' | 'sentence';
}

export type StepId = 1 | 2 | 3 | 4;

export interface StepItem {
  id: StepId;
  label: string;
}

export type AnnotationToolType =
  | 'select'
  | 'bbox'
  | 'polygon'
  | 'mask'
  | 'keypoint'
  | 'polyline'
  | 'eraser'
  | 'pan'
  | 'point'
  | 'zoom'
  | 'undo'
  | 'redo'
  | 'settings';

export interface BoundingBoxData {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface AnnotationItem {
  id: number;
  label: string;
  tagLabel: string;
  type: string;
  confidence: number;
  status: 'Approved' | 'Needs Review' | 'Rejected';
  visible: boolean;
  color: string;
  badgeBg: string;
  textColor: string;
  borderColor: string;
  bbox: BoundingBoxData;
}

export interface LabelChip {
  id: string;
  name: string;
  color: string;
  dotColor: string;
  count?: number;
}

export type ReviewDecision =
  | 'accept'
  | 'corrected'
  | 'reject'
  | 'second_review'
  | 'escalate';

export interface FilmstripItem {
  id: number;
  filename: string;
  active: boolean;
  imageSrc: string;
}
