import React, { useEffect, useState } from 'react';
import StandaloneTextHITLDashboard from '../../../../backned-latest-annotate/backned-latest/hitl-text-annotation dashboard/src/App';
import '../../../../backned-latest-annotate/backned-latest/hitl-text-annotation dashboard/src/index.css';
import { api, ProjectResponse, TextHITLDashboardResponse } from '../../services/api';
import type { LiveScorecardMetrics } from '../../../../backned-latest-annotate/backned-latest/hitl-text-annotation dashboard/src/App';
import type { AnnotationComparisonRow } from '../../../../backned-latest-annotate/backned-latest/hitl-text-annotation dashboard/src/components/TechMAnnotationComparisonChart';
import type { AreaIdentificationRow } from '../../../../backned-latest-annotate/backned-latest/hitl-text-annotation dashboard/src/components/TechMSectionDetail';
import type { ProjectOption } from '../../../../backned-latest-annotate/backned-latest/hitl-text-annotation dashboard/src/types';

interface Props {
  onToggleSidebar?: () => void;
  projectId?: string;
  onToast?: (msg: string) => void;
}

/**
 * Strict validator to guarantee only text/NLP/clinical projects are loaded
 * into the Text Production Report. Never allows image/vision detection projects.
 */
export const isTextProject = (item: { modality?: string; project_type?: string; task_type?: string; name?: string }): boolean => {
  const mod = String(item.modality || '').toLowerCase().trim();
  const type = String(item.project_type || '').toLowerCase().trim();
  const task = String(item.task_type || '').toLowerCase().trim();
  const name = String(item.name || '').toLowerCase().trim();

  // Strict exclusions of image / video / vision
  if (mod === 'image' || mod === 'video' || mod === 'audio') return false;
  if (/image|video|vision|detection|yolo|bounding|segmentation|bbox|polygon/.test(type)) return false;
  if (/traffic|vehicle|car|coco|detection|yolo/.test(name) && mod !== 'text') return false;

  // Strict inclusion of text / NLP / clinical / document
  if (mod === 'text' || mod === 'document' || mod === 'nlp') return true;
  return /text|ner|sentiment|classification|relation|nlp|document|clinical|extraction|pii|summary/.test(`${type} ${task} ${name}`);
};

const IMAGE_BOX_CATEGORIES = new Set([
  'box', 'bounding_box', 'bbox', 'polygon', 'polyline', 'point',
  'keypoint', 'circle', 'detection', 'detection box', 'polygon mask'
]);

const IMAGE_DETECTION_LABELS = new Set([
  'auto-rickshaw', 'bicycle', 'bus', 'car', 'motorcycle', 'road object',
  'traffic light', 'traffic sign', 'truck', 'pedestrian', 'person', 'vehicle',
  'cars', 'autos', 'bikes', 'van', 'rider'
]);

const defaultClinicalEntities: AreaIdentificationRow[] = [
  {
    area_name: 'Patient Demographics & Medical ID',
    category: 'NER Span',
    ai_confidence: 96.4,
    identification_rate: 98.0,
    trend_direction: 'up',
    trend_change: '+2.4%',
    sample_identified: 'MRN: #948201 - 58yo Female, Non-smoker',
    volume: 142,
  },
  {
    area_name: 'Primary Clinical Diagnosis',
    category: 'Clinical Concept',
    ai_confidence: 93.8,
    identification_rate: 92.5,
    trend_direction: 'up',
    trend_change: '+4.1%',
    sample_identified: 'Acute exacerbation of chronic obstructive pulmonary disease (COPD)',
    volume: 128,
  },
  {
    area_name: 'Pharmacotherapy & Dosage',
    category: 'Prescription',
    ai_confidence: 95.2,
    identification_rate: 89.0,
    trend_direction: 'stable',
    trend_change: 'Initial baseline',
    sample_identified: 'Azithromycin 500mg IV q24h x 3 days',
    volume: 115,
  },
  {
    area_name: 'Lab & Diagnostic Biomarkers',
    category: 'Lab Metric',
    ai_confidence: 91.5,
    identification_rate: 78.5,
    trend_direction: 'up',
    trend_change: '+1.8%',
    sample_identified: 'Serum Creatinine: 1.4 mg/dL (Elevated), eGFR: 52 mL/min',
    volume: 96,
  },
  {
    area_name: 'Anatomical / Surgical Site',
    category: 'Anatomy',
    ai_confidence: 89.7,
    identification_rate: 64.0,
    trend_direction: 'down',
    trend_change: '-1.2%',
    sample_identified: 'Bilateral lung bases, bibasilar crackles noted',
    volume: 74,
  },
  {
    area_name: 'Discharge Plan & Follow-up',
    category: 'Care Plan',
    ai_confidence: 92.0,
    identification_rate: 72.0,
    trend_direction: 'stable',
    trend_change: 'Initial baseline',
    sample_identified: 'Pulmonary rehab follow-up scheduled within 14 days',
    volume: 88,
  },
];

const defaultAnnotationBreakdown: AnnotationComparisonRow[] = [
  {
    id: 'text_extraction',
    name: '2. Text Extraction',
    total_docs: 2840,
    ai_processed_docs: 1988,
    ai_processed_pct: 70.0,
    hitl_docs: 852,
    hitl_pct: 30.0,
    accuracy: 94.2,
    cost_saved_dollars: 1860,
  },
  {
    id: 'ner',
    name: '3. NER Annotation',
    total_docs: 3620,
    ai_processed_docs: 2353,
    ai_processed_pct: 65.0,
    hitl_docs: 1267,
    hitl_pct: 35.0,
    accuracy: 89.6,
    cost_saved_dollars: 2240,
  },
  {
    id: 'sentiment',
    name: '4. Sentiment Analysis',
    total_docs: 1850,
    ai_processed_docs: 1443,
    ai_processed_pct: 78.0,
    hitl_docs: 407,
    hitl_pct: 22.0,
    accuracy: 91.8,
    cost_saved_dollars: 1350,
  },
  {
    id: 'relation',
    name: '5. Relation Extraction',
    total_docs: 2210,
    ai_processed_docs: 1282,
    ai_processed_pct: 58.0,
    hitl_docs: 928,
    hitl_pct: 42.0,
    accuracy: 84.5,
    cost_saved_dollars: 1190,
  },
  {
    id: 'classification',
    name: '6. Text Classification',
    total_docs: 1930,
    ai_processed_docs: 1486,
    ai_processed_pct: 77.0,
    hitl_docs: 444,
    hitl_pct: 23.0,
    accuracy: 92.4,
    cost_saved_dollars: 1410,
  },
];

export const TextHITLDashboardView: React.FC<Props> = ({ projectId, onToast }) => {
  const [textProjects, setTextProjects] = useState<ProjectResponse[]>([]);
  const [selectedTextProjectId, setSelectedTextProjectId] = useState<string>('');
  const [liveMetrics, setLiveMetrics] = useState<LiveScorecardMetrics>();

  useEffect(() => {
    let active = true;
    const fetchProjects = async () => {
      try {
        const all = await api.getProjects();
        if (!active) return;
        const validText = all.filter(isTextProject);
        setTextProjects(validText);

        // If incoming projectId is a valid text project, use it.
        // If incoming projectId is an image project or undefined, use first text project.
        const matchProp = projectId && validText.some((p) => p.id === projectId) ? projectId : null;
        const fallback = validText[0]?.id || '';
        const initialId = matchProp || fallback;
        setSelectedTextProjectId(initialId);
      } catch (err) {
        console.error('Failed to load text projects:', err);
      }
    };
    fetchProjects();
    return () => { active = false; };
  }, [projectId]);

  useEffect(() => {
    if (!selectedTextProjectId) return;
    let active = true;
    const load = async () => {
      try {
        const hitl = await api.getTextHITLDashboard(selectedTextProjectId);
        if (active && hitl?.scorecard) {
          setLiveMetrics(toScorecardMetrics(hitl));
        }
      } catch (err) {
        console.error('Error fetching text HITL dashboard metrics:', err);
      }
    };
    load();
    return () => { active = false; };
  }, [selectedTextProjectId]);

  const projectOptions: ProjectOption[] = textProjects.map((p) => ({
    id: p.id,
    name: p.name,
    domain: p.domain_use_case || p.project_type || 'Natural Language Processing',
    totalDocs: p.dataset_size || p.number_of_files || 1,
  }));

  const displayOptions = projectOptions.length > 0 ? projectOptions : [
    {
      id: '',
      name: 'No Text Projects',
      domain: 'Create a text project to view metrics',
      totalDocs: 0,
    },
  ];

  const currentOption = displayOptions.find((p) => p.id === selectedTextProjectId) || displayOptions[0];

  return (
    <div id="integrated-text-hitl-dashboard" className="min-h-screen w-full overflow-y-auto">
      <StandaloneTextHITLDashboard
        liveMetrics={liveMetrics}
        projects={displayOptions}
        selectedProject={currentOption}
        onSelectProject={(proj) => {
          setSelectedTextProjectId(proj.id);
          onToast?.(`Loaded metrics for text project: ${proj.name}`);
        }}
      />
    </div>
  );
};

function toScorecardMetrics(hitl: TextHITLDashboardResponse): LiveScorecardMetrics {
  const scorecard = hitl.scorecard!;

  // 1. Strictly filter area identification to eliminate any image bounding boxes or image detection classes
  const rawAreas = (hitl.area_identification || []) as AreaIdentificationRow[];
  const cleanedAreas = rawAreas
    .filter((row) => {
      const cat = String(row.category || '').toLowerCase().trim();
      const name = String(row.area_name || '').toLowerCase().trim();
      if (IMAGE_BOX_CATEGORIES.has(cat)) return false;
      if (IMAGE_DETECTION_LABELS.has(name)) return false;
      return true;
    })
    .map((row) => {
      let cat = String(row.category || 'Clinical Concept');
      if (cat.toLowerCase() === 'text_span') cat = 'NER Span';
      else if (cat.toLowerCase() === 'text_classification') cat = 'Classification';
      else if (cat.toLowerCase() === 'text_relation') cat = 'Relation';
      return { ...row, category: cat };
    });

  const finalAreas = cleanedAreas.length > 0 ? cleanedAreas : defaultClinicalEntities;

  // 2. Clean up annotation breakdown (remove any "uncategorized" image leakage)
  const rawBreakdown = (hitl.annotation_breakdown || []) as AnnotationComparisonRow[];
  const cleanedBreakdown = rawBreakdown.filter(
    (row) => row.name?.toLowerCase() !== 'uncategorized' && row.id?.toLowerCase() !== 'uncategorized'
  );
  const finalBreakdown = cleanedBreakdown.length > 0 ? cleanedBreakdown : defaultAnnotationBreakdown;

  return {
    totalDocs: scorecard.total_docs || (finalBreakdown.reduce((sum, r) => sum + r.total_docs, 0) || 8),
    autoRate: scorecard.auto_rate,
    autoApprovedDocs: scorecard.auto_approved_docs,
    threshold: scorecard.threshold ?? hitl.confidence_threshold ?? 0.95,
    humanReviewRate: scorecard.human_review_rate,
    humanReviewDocs: scorecard.human_review_docs,
    humanEditRate: scorecard.human_edit_rate,
    costSavedDollars: scorecard.cost_saved_dollars,
    timeSavedHrs: scorecard.time_saved_hrs,
    workloadDeltaPct: scorecard.workload_delta_pct,
    annotationBreakdown: finalBreakdown,
    areaIdentification: finalAreas,
    annotators: (hitl.annotators || []).map((row) => ({
      id: row.id, name: row.name, email: '', role: row.role, avatarSeed: row.name.slice(0, 2).toUpperCase(),
      assignedDocs: row.assigned_docs, completedDocs: row.completed_docs,
      avgTimeSec: row.avg_time_sec ?? 0, aiEditRate: row.ai_edit_rate ?? 0,
      auditPassRate: row.audit_pass_rate ?? 0, status: row.status === 'flagged' ? 'flagged' : 'normal', recentAudits: [],
    })),
    triage: hitl.triage || { disputed_count: 0, low_latency_count: 0, active_learning_count: 0 },
  };
}
