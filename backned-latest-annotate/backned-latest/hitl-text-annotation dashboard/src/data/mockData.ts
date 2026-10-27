import {
  ProjectOption,
  ModelRunOption,
  DatasetSliceOption,
  AnnotatorRecord,
  DisputedItem,
  ActiveLearningItem,
  AnnotationSectionConfig,
  AnnotationType
} from '../types';

export const PROJECTS: ProjectOption[] = [
  {
    id: 'mednlp-v2',
    name: 'MedNLP Clinical Extraction v2',
    domain: 'Healthcare & EHR Clinical Notes',
    totalDocs: 124500
  },
  {
    id: 'sec-10k-v1',
    name: 'Financial SEC-10K Key-Value v1',
    domain: 'Financial Filings & Risk Disclosures',
    totalDocs: 86200
  },
  {
    id: 'legal-contracts-v3',
    name: 'Legal Contract Entity Resolver v3',
    domain: 'Corporate MSA & NDAs',
    totalDocs: 54100
  }
];

export const MODEL_RUNS: ModelRunOption[] = [
  {
    id: 'llama3-8b-v14',
    name: 'LLaMA-3-8B-Instruct (v1.4)',
    version: 'v1.4-tuned-lora',
    architecture: 'Meta-Llama-3-8B',
    baseF1: 0.892,
    date: '2026-09-28'
  },
  {
    id: 'mistral-large-v21',
    name: 'Mistral-Large-Instruct (v2.1)',
    version: 'v2.1-fp16',
    architecture: 'Mistral-Large-2407',
    baseF1: 0.908,
    date: '2026-10-02'
  },
  {
    id: 'biomedlm-7b-v09',
    name: 'BioMedLM-Clinical-7B (v0.9)',
    version: 'v0.9-pubmed-finetuned',
    architecture: 'GPT-NeoX-Clinical',
    baseF1: 0.865,
    date: '2026-09-15'
  }
];

export const DATASET_SLICES: DatasetSliceOption[] = [
  {
    id: 'q3-discharge-100k',
    name: 'Q3-Discharge-Summaries-100k',
    count: 100000,
    description: 'Inpatient discharge notes from tertiary academic medical center (ICU & Cardiology).'
  },
  {
    id: 'q2-pathology-50k',
    name: 'Q2-Pathology-Reports-50k',
    count: 50000,
    description: 'Surgical histopathology biopsies with synoptic cancer staging.'
  },
  {
    id: 'q4-radiology-75k',
    name: 'Q4-Radiology-Notes-75k',
    count: 75000,
    description: 'Multi-modal chest CT and abdominal MRI narrative impression sections.'
  }
];

// Comparison of all 5 annotation types (AI Processed vs Moved to HITL)
export const ANNOTATION_COMPARISON_DATA = [
  {
    id: 'text_extraction' as AnnotationType,
    sectionNumber: 2,
    name: '2. Text Extraction',
    shortName: 'Text Extraction',
    totalDocs: 28400,
    aiProcessedDocs: 19880,
    aiProcessedPct: 70.0,
    hitlDocs: 8520,
    hitlPct: 30.0,
    accuracy: '94.2%'
  },
  {
    id: 'ner' as AnnotationType,
    sectionNumber: 3,
    name: '3. NER Annotation',
    shortName: 'NER Annotation',
    totalDocs: 36200,
    aiProcessedDocs: 23530,
    aiProcessedPct: 65.0,
    hitlDocs: 12670,
    hitlPct: 35.0,
    accuracy: '89.6%'
  },
  {
    id: 'sentiment' as AnnotationType,
    sectionNumber: 4,
    name: '4. Sentiment Analysis',
    shortName: 'Sentiment Analysis',
    totalDocs: 18500,
    aiProcessedDocs: 14430,
    aiProcessedPct: 78.0,
    hitlDocs: 4070,
    hitlPct: 22.0,
    accuracy: '91.8%'
  },
  {
    id: 'relation' as AnnotationType,
    sectionNumber: 5,
    name: '5. Relation Extraction',
    shortName: 'Relation Extraction',
    totalDocs: 22100,
    aiProcessedDocs: 12818,
    aiProcessedPct: 58.0,
    hitlDocs: 9282,
    hitlPct: 42.0,
    accuracy: '84.5%'
  },
  {
    id: 'classification' as AnnotationType,
    sectionNumber: 6,
    name: '6. Text Classification',
    shortName: 'Text Classification',
    totalDocs: 19300,
    aiProcessedDocs: 14861,
    aiProcessedPct: 77.0,
    hitlDocs: 4439,
    hitlPct: 23.0,
    accuracy: '93.1%'
  }
];

// Configuration and area identification trend for each of the 5 sections
export const ANNOTATION_SECTIONS_MAP: Record<AnnotationType, AnnotationSectionConfig> = {
  text_extraction: {
    id: 'text_extraction',
    sectionNumber: 2,
    title: '2. Text Extraction',
    shortName: 'Text Extraction',
    description: 'Key-value extraction of structured clinical parameters from freeform physician discharge summaries.',
    scorecard: {
      totalDocs: 28400,
      aiProcessedDocs: 19880,
      aiProcessedRate: 70.0,
      hitlDocs: 8520,
      hitlRate: 30.0,
      accuracyRate: 94.2,
      costSaved: '$2,140'
    },
    areas: [
      {
        areaName: 'Patient MRN & Identifiers',
        category: 'Demographics Header',
        aiConfidence: 98.4,
        identificationRate: 99.1,
        volume: 28400,
        trendDirection: 'up',
        trendChange: '+0.8% this week',
        sampleIdentified: 'MRN: #9902-441-A | DOB: 1964-11-04'
      },
      {
        areaName: 'Prescription Regimen Tables',
        category: 'Medication Orders',
        aiConfidence: 89.2,
        identificationRate: 88.4,
        volume: 24100,
        trendDirection: 'up',
        trendChange: '+3.1% this week',
        sampleIdentified: 'Metformin 500mg PO BID with meals #60 tabs'
      },
      {
        areaName: 'Lab Panels & Biomarkers',
        category: 'Diagnostics Key-Value',
        aiConfidence: 92.5,
        identificationRate: 91.8,
        volume: 21300,
        trendDirection: 'up',
        trendChange: '+1.9% this week',
        sampleIdentified: 'Hemoglobin A1c: 7.2% | Serum Creatinine: 1.1 mg/dL'
      },
      {
        areaName: 'Primary ICD-10 Diagnostic Codes',
        category: 'Billing Taxonomy',
        aiConfidence: 81.6,
        identificationRate: 82.3,
        volume: 18900,
        trendDirection: 'down',
        trendChange: '-1.2% (complex comorbidity notes)',
        sampleIdentified: 'I50.22 (Chronic systolic heart failure, decompensated)',
        difficultyNote: 'Secondary complications often require human verification'
      },
      {
        areaName: 'Post-Discharge Follow-Up Schedule',
        category: 'Care Plan',
        aiConfidence: 86.8,
        identificationRate: 87.5,
        volume: 17200,
        trendDirection: 'up',
        trendChange: '+2.4% this week',
        sampleIdentified: 'Follow up Cardiology clinic in 14 days with repeat ECG'
      }
    ],
    weeklyTrend: [
      { day: 'Mon', aiProcessed: 2750, hitlMoved: 1200 },
      { day: 'Tue', aiProcessed: 2890, hitlMoved: 1220 },
      { day: 'Wed', aiProcessed: 3020, hitlMoved: 1190 },
      { day: 'Thu', aiProcessed: 3180, hitlMoved: 1240 },
      { day: 'Fri', aiProcessed: 3340, hitlMoved: 1180 },
      { day: 'Sat', aiProcessed: 2320, hitlMoved: 1120 },
      { day: 'Sun', aiProcessed: 2380, hitlMoved: 1170 }
    ]
  },

  ner: {
    id: 'ner',
    sectionNumber: 3,
    title: '3. NER Annotation',
    shortName: 'NER Annotation',
    description: 'Token span boundary detection and entity taxonomy classification across complex clinical prose.',
    scorecard: {
      totalDocs: 36200,
      aiProcessedDocs: 23530,
      aiProcessedRate: 65.0,
      hitlDocs: 12670,
      hitlRate: 35.0,
      accuracyRate: 89.6,
      costSaved: '$2,780'
    },
    areas: [
      {
        areaName: 'Medication Names (Rx/Chemical)',
        category: 'Pharmacology Entities',
        aiConfidence: 94.6,
        identificationRate: 95.2,
        volume: 48900,
        trendDirection: 'up',
        trendChange: '+2.1% this week',
        sampleIdentified: '[Lisinopril], [Atorvastatin calcium], [Enoxaparin]'
      },
      {
        areaName: 'Dosage Strengths & Routes',
        category: 'Administration Protocol',
        aiConfidence: 96.1,
        identificationRate: 96.8,
        volume: 38200,
        trendDirection: 'up',
        trendChange: '+1.4% this week',
        sampleIdentified: '[20 mg PO daily], [100 mcg IV push]'
      },
      {
        areaName: 'Clinical Diagnoses & Syndromes',
        category: 'Pathology & Disease',
        aiConfidence: 87.2,
        identificationRate: 86.4,
        volume: 34100,
        trendDirection: 'stable',
        trendChange: '+0.3% this week',
        sampleIdentified: '[Acute non-ST elevation myocardial infarction (NSTEMI)]'
      },
      {
        areaName: 'Anatomical Locations & Laterality',
        category: 'Anatomy Entities',
        aiConfidence: 91.8,
        identificationRate: 92.4,
        volume: 22400,
        trendDirection: 'up',
        trendChange: '+1.8% this week',
        sampleIdentified: '[Left lower lung lobe], [Proximal LAD coronary artery]'
      },
      {
        areaName: 'Surgical & Bedside Procedures',
        category: 'Clinical Interventions',
        aiConfidence: 79.4,
        identificationRate: 78.1,
        volume: 16800,
        trendDirection: 'down',
        trendChange: '-2.4% (narrative operative reports)',
        sampleIdentified: '[Endovascular stent graft placement]',
        difficultyNote: 'Past surgical history narrative frequently triggers HITL review'
      }
    ],
    weeklyTrend: [
      { day: 'Mon', aiProcessed: 3250, hitlMoved: 1810 },
      { day: 'Tue', aiProcessed: 3380, hitlMoved: 1820 },
      { day: 'Wed', aiProcessed: 3510, hitlMoved: 1790 },
      { day: 'Thu', aiProcessed: 3620, hitlMoved: 1780 },
      { day: 'Fri', aiProcessed: 3790, hitlMoved: 1760 },
      { day: 'Sat', aiProcessed: 2880, hitlMoved: 1690 },
      { day: 'Sun', aiProcessed: 3100, hitlMoved: 1620 }
    ]
  },

  sentiment: {
    id: 'sentiment',
    sectionNumber: 4,
    title: '4. Sentiment Analysis',
    shortName: 'Sentiment Analysis',
    description: 'Detection of physician narrative urgency, clinical stability, and patient trajectory confidence.',
    scorecard: {
      totalDocs: 18500,
      aiProcessedDocs: 14430,
      aiProcessedRate: 78.0,
      hitlDocs: 4070,
      hitlRate: 22.0,
      accuracyRate: 91.8,
      costSaved: '$1,390'
    },
    areas: [
      {
        areaName: 'Stable Clinical Progress / Favorable Tone',
        category: 'Routine Recovery',
        aiConfidence: 95.8,
        identificationRate: 96.5,
        volume: 9800,
        trendDirection: 'up',
        trendChange: '+1.7% this week',
        sampleIdentified: '"Patient ambulating well on room air, vital signs stable, tolerating diet."'
      },
      {
        areaName: 'Acute Instability / Guarded Prognosis',
        category: 'High Acuity Alert',
        aiConfidence: 91.2,
        identificationRate: 90.8,
        volume: 3800,
        trendDirection: 'up',
        trendChange: '+3.8% this week',
        sampleIdentified: '"Respiratory status precarious; remains on borderline pressor support."'
      },
      {
        areaName: 'Discharge Hesitation / Social Barriers',
        category: 'Care Coordination',
        aiConfidence: 82.4,
        identificationRate: 81.2,
        volume: 2700,
        trendDirection: 'stable',
        trendChange: '+0.5% this week',
        sampleIdentified: '"Family expresses hesitation regarding home oxygen management."'
      },
      {
        areaName: 'Pain Management Refractory Distress',
        category: 'Symptom Distress',
        aiConfidence: 88.0,
        identificationRate: 87.6,
        volume: 2200,
        trendDirection: 'up',
        trendChange: '+2.1% this week',
        sampleIdentified: '"Pain remains inadequately controlled despite multimodal intravenous analgesia."'
      }
    ],
    weeklyTrend: [
      { day: 'Mon', aiProcessed: 1980, hitlMoved: 580 },
      { day: 'Tue', aiProcessed: 2060, hitlMoved: 590 },
      { day: 'Wed', aiProcessed: 2150, hitlMoved: 570 },
      { day: 'Thu', aiProcessed: 2220, hitlMoved: 580 },
      { day: 'Fri', aiProcessed: 2290, hitlMoved: 560 },
      { day: 'Sat', aiProcessed: 1810, hitlMoved: 570 },
      { day: 'Sun', aiProcessed: 1920, hitlMoved: 520 }
    ]
  },

  relation: {
    id: 'relation',
    sectionNumber: 5,
    title: '5. Relation Extraction',
    shortName: 'Relation Extraction',
    description: 'Extracting semantic links between clinical entities (e.g. Medication TREATS Diagnosis, Drug ADVERSE_EVENT).',
    scorecard: {
      totalDocs: 22100,
      aiProcessedDocs: 12818,
      aiProcessedRate: 58.0,
      hitlDocs: 9282,
      hitlRate: 42.0,
      accuracyRate: 84.5,
      costSaved: '$1,020'
    },
    areas: [
      {
        areaName: 'TREATS_CONDITION (Medication -> Disease)',
        category: 'Therapeutic Indication',
        aiConfidence: 91.4,
        identificationRate: 92.0,
        volume: 18400,
        trendDirection: 'up',
        trendChange: '+2.6% this week',
        sampleIdentified: '[Metoprolol succinate] ──TREATS──> [Atrial fibrillation]'
      },
      {
        areaName: 'CAUSES_ADVERSE_EVENT (Medication -> Side Effect)',
        category: 'Drug Safety Warning',
        aiConfidence: 81.8,
        identificationRate: 80.5,
        volume: 6800,
        trendDirection: 'stable',
        trendChange: '+0.9% this week',
        sampleIdentified: '[Lisinopril] ──CAUSES──> [Dry intractable cough]'
      },
      {
        areaName: 'CONTRAINDICATED_WITH (Drug -> Drug / Condition)',
        category: 'Clinical Contraindication',
        aiConfidence: 77.2,
        identificationRate: 75.9,
        volume: 4200,
        trendDirection: 'down',
        trendChange: '-2.1% (complex drug-drug interactions)',
        sampleIdentified: '[Clopidogrel] ──CONTRAINDICATED──> [Omeprazole]',
        difficultyNote: 'Strict rule: Any contraindication below 0.90 is sent to HITL'
      },
      {
        areaName: 'MANIFESTS_SYMPTOM (Disease -> Finding)',
        category: 'Symptom Association',
        aiConfidence: 86.5,
        identificationRate: 87.2,
        volume: 11200,
        trendDirection: 'up',
        trendChange: '+1.8% this week',
        sampleIdentified: '[Heart Failure] ──MANIFESTS──> [Bilateral peripheral edema]'
      }
    ],
    weeklyTrend: [
      { day: 'Mon', aiProcessed: 1740, hitlMoved: 1330 },
      { day: 'Tue', aiProcessed: 1810, hitlMoved: 1320 },
      { day: 'Wed', aiProcessed: 1890, hitlMoved: 1310 },
      { day: 'Thu', aiProcessed: 1940, hitlMoved: 1300 },
      { day: 'Fri', aiProcessed: 2020, hitlMoved: 1290 },
      { day: 'Sat', aiProcessed: 1680, hitlMoved: 1350 },
      { day: 'Sun', aiProcessed: 1738, hitlMoved: 1382 }
    ]
  },

  classification: {
    id: 'classification',
    sectionNumber: 6,
    title: '6. Text Classification',
    shortName: 'Text Classification',
    description: 'Document-level categorization into admission disposition, clinical service, and urgency acuity tiers.',
    scorecard: {
      totalDocs: 19300,
      aiProcessedDocs: 14861,
      aiProcessedRate: 77.0,
      hitlDocs: 4439,
      hitlRate: 23.0,
      accuracyRate: 93.1,
      costSaved: '$1,090'
    },
    areas: [
      {
        areaName: 'Elective Surgical vs Emergency Inpatient',
        category: 'Admission Type',
        aiConfidence: 97.2,
        identificationRate: 98.0,
        volume: 19300,
        trendDirection: 'up',
        trendChange: '+0.5% this week',
        sampleIdentified: 'Classification: EMERGENCY_INPATIENT (Confidence: 99.1%)'
      },
      {
        areaName: 'Cardiology vs Med-Surg Service Routing',
        category: 'Specialty Department',
        aiConfidence: 94.6,
        identificationRate: 95.1,
        volume: 19300,
        trendDirection: 'up',
        trendChange: '+1.4% this week',
        sampleIdentified: 'Service: CARDIOLOGY_INPATIENT_SERVICE'
      },
      {
        areaName: 'ICU Stepdown vs Telemetry Observation',
        category: 'Acuity Bed Allocation',
        aiConfidence: 86.8,
        identificationRate: 85.9,
        volume: 12400,
        trendDirection: 'down',
        trendChange: '-1.8% (ambiguous nursing notes)',
        sampleIdentified: 'Level of Care: TELEMETRY_OBSERVATION',
        difficultyNote: 'Borderline hemodynamics trigger lead clinician review'
      },
      {
        areaName: 'Home with Home Health vs SNF Facility',
        category: 'Discharge Disposition',
        aiConfidence: 91.5,
        identificationRate: 92.1,
        volume: 17800,
        trendDirection: 'up',
        trendChange: '+2.8% this week',
        sampleIdentified: 'Disposition: DISCHARGED_HOME_WITH_HEALTH_SERVICES'
      }
    ],
    weeklyTrend: [
      { day: 'Mon', aiProcessed: 2050, hitlMoved: 630 },
      { day: 'Tue', aiProcessed: 2130, hitlMoved: 620 },
      { day: 'Wed', aiProcessed: 2210, hitlMoved: 610 },
      { day: 'Thu', aiProcessed: 2280, hitlMoved: 640 },
      { day: 'Fri', aiProcessed: 2360, hitlMoved: 620 },
      { day: 'Sat', aiProcessed: 1890, hitlMoved: 650 },
      { day: 'Sun', aiProcessed: 1941, hitlMoved: 669 }
    ]
  }
};

export const ANNOTATOR_RECORDS: AnnotatorRecord[] = [
  {
    id: 'ann-001',
    name: 'Devon Vance',
    email: 'devon.vance@techmahindra.com',
    role: 'Tier 1 Reviewer',
    avatarSeed: 'DV',
    assignedDocs: 1840,
    completedDocs: 1820,
    avgTimeSec: 11, // Outlier!
    aiEditRate: 1.1, // Suspiciously low!
    auditPassRate: 72.4, // Failed recent audits!
    status: 'flagged',
    flagReason: 'Rubber-Stamping Alert: Abnormally low review latency (11s vs team median 54s) with near-zero edit rate (1.1%) and 72.4% QA pass rate.',
    recentAudits: [
      { id: 'aud-901', date: 'Oct 06', docId: 'DOC-91823', result: 'fail', notes: 'Missed 4 missed drug contraindications; accepted hallucinated dosage.' },
      { id: 'aud-902', date: 'Oct 05', docId: 'DOC-91404', result: 'fail', notes: 'Completed in 8 seconds; obvious anatomical misclassification left unchanged.' },
      { id: 'aud-903', date: 'Oct 04', docId: 'DOC-90912', result: 'pass', notes: 'Verified correctly on simple standard prescription note.' }
    ]
  },
  {
    id: 'ann-002',
    name: 'Dr. Aris Thorne',
    email: 'aris.thorne@techmahindra.com',
    role: 'Lead Clinical Reviewer',
    avatarSeed: 'AT',
    assignedDocs: 1250,
    completedDocs: 1240,
    avgTimeSec: 58,
    aiEditRate: 18.2,
    auditPassRate: 98.6,
    status: 'star',
    recentAudits: [
      { id: 'aud-891', date: 'Oct 06', docId: 'DOC-91811', result: 'pass', notes: 'Exemplary boundary trimming on compound oncology diagnoses.' },
      { id: 'aud-892', date: 'Oct 05', docId: 'DOC-91330', result: 'pass', notes: 'Accurate distinction between past vs present medical history.' }
    ]
  },
  {
    id: 'ann-003',
    name: 'Elena Rostova',
    email: 'elena.rostova@techmahindra.com',
    role: 'Senior BioNLP Specialist',
    avatarSeed: 'ER',
    assignedDocs: 1600,
    completedDocs: 1580,
    avgTimeSec: 47,
    aiEditRate: 14.5,
    auditPassRate: 96.2,
    status: 'normal',
    recentAudits: [
      { id: 'aud-884', date: 'Oct 06', docId: 'DOC-91776', result: 'pass', notes: 'High precision on complex ICU discharge notes.' },
      { id: 'aud-885', date: 'Oct 03', docId: 'DOC-90881', result: 'minor_adjustment', notes: 'Slightly conservative on lab biomarker abbreviations.' }
    ]
  },
  {
    id: 'ann-004',
    name: 'Marcus Brody',
    email: 'marcus.brody@techmahindra.com',
    role: 'Clinical QA Auditor',
    avatarSeed: 'MB',
    assignedDocs: 1420,
    completedDocs: 1390,
    avgTimeSec: 52,
    aiEditRate: 16.0,
    auditPassRate: 94.8,
    status: 'normal',
    recentAudits: [
      { id: 'aud-877', date: 'Oct 05', docId: 'DOC-91219', result: 'pass', notes: 'Solid review performance across surgical notes.' }
    ]
  },
  {
    id: 'ann-005',
    name: 'Priya Sen',
    email: 'priya.sen@techmahindra.com',
    role: 'Junior Annotator (Probation)',
    avatarSeed: 'PS',
    assignedDocs: 850,
    completedDocs: 720,
    avgTimeSec: 68,
    aiEditRate: 21.4,
    auditPassRate: 88.5,
    status: 'in_calibration',
    flagReason: 'In Calibration Phase: High review latency (68s) and higher edit rate. Currently paired with shadow auditor.',
    recentAudits: [
      { id: 'aud-862', date: 'Oct 06', docId: 'DOC-91690', result: 'minor_adjustment', notes: 'Over-splitting combined medication/dosage into non-standard tokens.' }
    ]
  },
  {
    id: 'ann-006',
    name: 'Carlos Mendez',
    email: 'carlos.mendez@techmahindra.com',
    role: 'Tier 1 Reviewer',
    avatarSeed: 'CM',
    assignedDocs: 1510,
    completedDocs: 1490,
    avgTimeSec: 44,
    aiEditRate: 13.9,
    auditPassRate: 92.1,
    status: 'normal',
    recentAudits: [
      { id: 'aud-850', date: 'Oct 04', docId: 'DOC-91040', result: 'pass', notes: 'Consistent throughput and adherence to annotation guideline v2.3.' }
    ]
  }
];

export const DISPUTED_ITEMS: DisputedItem[] = [
  {
    id: 'disp-101',
    docId: 'DOC-MED-44029',
    sourceSlice: 'Q3-Discharge-Summaries-100k',
    textSnippet: 'Patient was initiated on oral Carvedilol 12.5 mg BID for progressive decompensated heart failure with reduced ejection fraction (HFrEF).',
    context: 'Cardiology Discharge Summary, Hospital Day 6',
    annotatorA: {
      name: 'Dr. Aris Thorne',
      label: 'DIAGNOSIS',
      spanText: 'decompensated heart failure with reduced ejection fraction (HFrEF)',
      startIndex: 53,
      endIndex: 120,
      confidence: 0.94,
      timeSpentSec: 62
    },
    annotatorB: {
      name: 'Carlos Mendez',
      label: 'DIAGNOSIS',
      spanText: 'decompensated heart failure',
      startIndex: 53,
      endIndex: 80,
      confidence: 0.78,
      timeSpentSec: 28
    },
    modelPrediction: {
      label: 'DIAGNOSIS',
      spanText: 'heart failure',
      confidence: 0.71
    },
    status: 'unresolved'
  },
  {
    id: 'disp-102',
    docId: 'DOC-MED-44115',
    sourceSlice: 'Q3-Discharge-Summaries-100k',
    textSnippet: 'Post-operative wound showed erythema and purulent drainage, suspicious for MRSA surgical site infection.',
    context: 'General Surgery Operative Course',
    annotatorA: {
      name: 'Elena Rostova',
      label: 'DIAGNOSIS',
      spanText: 'MRSA surgical site infection',
      startIndex: 76,
      endIndex: 104,
      confidence: 0.96,
      timeSpentSec: 48
    },
    annotatorB: {
      name: 'Priya Sen',
      label: 'LAB_TEST',
      spanText: 'MRSA',
      startIndex: 76,
      endIndex: 80,
      confidence: 0.65,
      timeSpentSec: 55
    },
    modelPrediction: {
      label: 'DIAGNOSIS',
      spanText: 'surgical site infection',
      confidence: 0.62
    },
    status: 'unresolved'
  },
  {
    id: 'disp-103',
    docId: 'DOC-MED-44280',
    sourceSlice: 'Q3-Discharge-Summaries-100k',
    textSnippet: 'Administered 1 g IV vancomycin every 12 hours adjusted per nephrology trough protocol.',
    context: 'Infectious Disease Consult Note',
    annotatorA: {
      name: 'Devon Vance',
      label: 'MEDICINE',
      spanText: 'vancomycin',
      startIndex: 21,
      endIndex: 31,
      confidence: 0.88,
      timeSpentSec: 9
    },
    annotatorB: {
      name: 'Marcus Brody',
      label: 'MEDICINE',
      spanText: 'IV vancomycin',
      startIndex: 18,
      endIndex: 31,
      confidence: 0.92,
      timeSpentSec: 44
    },
    modelPrediction: {
      label: 'MEDICINE',
      spanText: 'vancomycin',
      confidence: 0.82
    },
    status: 'unresolved'
  }
];

export const LOW_LATENCY_SUBMISSIONS = [
  {
    id: 'lat-501',
    docId: 'DOC-91823',
    annotatorName: 'Devon Vance',
    submittedAt: 'Today, 09:14 AM',
    elapsedSec: 7,
    spansReviewed: 14,
    editsMade: 0,
    confidenceMean: 0.68,
    riskLevel: 'Critical'
  },
  {
    id: 'lat-502',
    docId: 'DOC-91829',
    annotatorName: 'Devon Vance',
    submittedAt: 'Today, 09:16 AM',
    elapsedSec: 9,
    spansReviewed: 11,
    editsMade: 0,
    confidenceMean: 0.71,
    riskLevel: 'Critical'
  },
  {
    id: 'lat-503',
    docId: 'DOC-91834',
    annotatorName: 'Devon Vance',
    submittedAt: 'Today, 09:19 AM',
    elapsedSec: 11,
    spansReviewed: 18,
    editsMade: 1,
    confidenceMean: 0.64,
    riskLevel: 'High'
  },
  {
    id: 'lat-504',
    docId: 'DOC-91845',
    annotatorName: 'Carlos Mendez',
    submittedAt: 'Today, 10:02 AM',
    elapsedSec: 16,
    spansReviewed: 6,
    editsMade: 0,
    confidenceMean: 0.79,
    riskLevel: 'Moderate'
  }
];

export const ACTIVE_LEARNING_ITEMS: ActiveLearningItem[] = [
  {
    id: 'al-301',
    docId: 'DOC-AL-8821',
    snippet: 'Patient reports intermittent orthostatic lightheadedness following titrating hydralazine to 50mg TID.',
    uncertaintyScore: 0.942,
    entropy: 1.84,
    dominantClass: 'MEDICINE / ADVERSE_EVENT',
    suggestedAction: 'Dual annotator consensus required for epistemic margin sample'
  },
  {
    id: 'al-302',
    docId: 'DOC-AL-8829',
    snippet: 'Echocardiogram: LVEF 30-35%, moderate aortic stenosis with peak gradient 38 mmHg.',
    uncertaintyScore: 0.918,
    entropy: 1.76,
    dominantClass: 'DIAGNOSIS / LAB_MEASUREMENT',
    suggestedAction: 'Threshold boundary ambiguity between diagnosis and quantitative metric'
  },
  {
    id: 'al-303',
    docId: 'DOC-AL-8834',
    snippet: 'Discontinued enoxaparin bridging given elevated anti-Xa assay and occult melena.',
    uncertaintyScore: 0.887,
    entropy: 1.69,
    dominantClass: 'PROCEDURE / CONTRAINDICATION',
    suggestedAction: 'High uncertainty in relation extraction linking'
  }
];

// Helper to compute overall pipeline metrics dynamically based on threshold
export function computeMetricsForThreshold(threshold: number, totalDocs = 124500) {
  const delta = (0.90 - threshold) * 100;
  const autoRate = Math.min(Math.max(64.2 + (delta * 1.86), 28.0), 88.5);
  const humanReviewRate = Math.max(100 - autoRate, 11.5);
  
  const autoApprovedDocs = Math.round((autoRate / 100) * totalDocs);
  const humanReviewDocs = totalDocs - autoApprovedDocs;

  // Baseline manual review: 44,400 docs
  const baselineManual = 44400;
  const workloadDeltaPct = Math.round(((humanReviewDocs - baselineManual) / baselineManual) * 100);

  // Time & cost savings
  const manualSeconds = humanReviewDocs * 45;
  const totalPotentialManualSeconds = totalDocs * 45;
  const timeSavedHrs = Math.round((totalPotentialManualSeconds - manualSeconds) / 3600);
  const costSavedDollars = Math.round(autoApprovedDocs * 0.22);

  return {
    threshold,
    totalDocs,
    autoRate: Number(autoRate.toFixed(1)),
    humanReviewRate: Number(humanReviewRate.toFixed(1)),
    autoApprovedDocs,
    humanReviewDocs,
    workloadDeltaPct,
    timeSavedHrs,
    costSavedDollars
  };
}
