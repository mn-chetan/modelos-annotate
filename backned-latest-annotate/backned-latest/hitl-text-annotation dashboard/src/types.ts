export type AnnotationType = 'text_extraction' | 'ner' | 'sentiment' | 'relation' | 'classification';

export interface ProjectOption {
  id: string;
  name: string;
  domain: string;
  totalDocs: number;
}

export interface ModelRunOption {
  id: string;
  name: string;
  version: string;
  architecture: string;
  baseF1: number;
  date: string;
}

export interface DatasetSliceOption {
  id: string;
  name: string;
  count: number;
  description: string;
}

export interface DateFilter {
  id: '7d' | '30d' | 'custom';
  label: string;
  startDate?: string;
  endDate?: string;
}

export interface AnnotatorRecord {
  id: string;
  name: string;
  email: string;
  role: string;
  avatarSeed: string;
  assignedDocs: number;
  completedDocs: number;
  avgTimeSec: number;
  aiEditRate: number; // percentage
  auditPassRate: number; // percentage
  status: 'normal' | 'flagged' | 'star' | 'in_calibration';
  flagReason?: string;
  recentAudits: {
    id: string;
    date: string;
    docId: string;
    result: 'pass' | 'fail' | 'minor_adjustment';
    notes: string;
  }[];
}

export interface DisputedItem {
  id: string;
  docId: string;
  textSnippet: string;
  context: string;
  sourceSlice: string;
  annotatorA: {
    name: string;
    label: string;
    spanText: string;
    startIndex: number;
    endIndex: number;
    confidence: number;
    timeSpentSec: number;
  };
  annotatorB: {
    name: string;
    label: string;
    spanText: string;
    startIndex: number;
    endIndex: number;
    confidence: number;
    timeSpentSec: number;
  };
  modelPrediction: {
    label: string;
    spanText: string;
    confidence: number;
  };
  status: 'unresolved' | 'resolved';
  resolution?: string;
}

export interface ActiveLearningItem {
  id: string;
  docId: string;
  snippet: string;
  uncertaintyScore: number;
  entropy: number;
  dominantClass: string;
  suggestedAction: string;
}

export interface AnnotationAreaTrend {
  areaName: string;
  category: string;
  aiConfidence: number; // e.g. 94.2
  identificationRate: number; // e.g. 91.5%
  volume: number;
  trendDirection: 'up' | 'down' | 'stable';
  trendChange: string; // e.g. "+4.2% vs baseline"
  sampleIdentified: string;
  difficultyNote?: string;
}

export interface AnnotationSectionConfig {
  id: AnnotationType;
  sectionNumber: number;
  title: string;
  shortName: string;
  description: string;
  scorecard: {
    totalDocs: number;
    aiProcessedDocs: number;
    aiProcessedRate: number;
    hitlDocs: number;
    hitlRate: number;
    accuracyRate: number;
    costSaved: string;
  };
  areas: AnnotationAreaTrend[];
  weeklyTrend: {
    day: string;
    aiProcessed: number;
    hitlMoved: number;
  }[];
}
