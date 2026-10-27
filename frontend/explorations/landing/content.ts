/*
 * Shared content for the landing-page explorations. Every variant draws on the same
 * capabilities and specimens so the comparison is about direction, not copy.
 * Specimen data is illustrative sample output, not product metrics.
 */
import streetUrl from './assets/street.webp';
import busesUrl from './assets/buses.webp';

export const images = { street: streetUrl, buses: busesUrl };

export const WORKSPACE_HREF = '/app1/';

export type Modality = 'image' | 'text' | 'video';

export const capabilities: Record<
  Modality,
  { title: string; line: string; tasks: string[] }
> = {
  image: {
    title: 'Image',
    line: 'Boxes, classes and masks drafted by vision models, then checked object by object.',
    tasks: ['Object detection', 'Labelling', 'PII masking'],
  },
  text: {
    title: 'Text',
    line: 'Entities, sentiment and categories marked in context, with every span open to correction.',
    tasks: ['Named entities', 'Sentiment', 'Classification', 'Relation extraction'],
  },
  video: {
    title: 'Video',
    line: 'Objects detected frame by frame and followed as tracks, so identities hold across a clip.',
    tasks: ['Detection', 'Object tracking', 'Frame review'],
  },
};

export type Step = { key: string; name: string; actor: 'AI' | 'Reviewer' | 'QC' | 'Team'; line: string };

export const workflow: Step[] = [
  { key: 'intake', name: 'Intake', actor: 'Team', line: 'Define the project: data, classes, guidelines and the quality bar.' },
  { key: 'ai', name: 'AI pre\u2011annotation', actor: 'AI', line: 'Models draft every label with a confidence score attached.' },
  { key: 'review', name: 'Human review', actor: 'Reviewer', line: 'People accept, correct or reject; uncertain calls come first.' },
  { key: 'qc', name: 'Quality check', actor: 'QC', line: 'An independent audit samples the work and sends back what fails.' },
  { key: 'export', name: 'Export', actor: 'Team', line: 'Approved labels leave with their full review trail.' },
];

/* ---------- Image specimen: urban street, boxes in % of the frame ---------- */

export type Box = {
  id: string;
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
  conf: number;
  /** Reviewer's corrected label, when the AI draft was wrong. */
  fix?: string;
};

export const streetBoxes: Box[] = [
  { id: 'b1', label: 'bus', x: 43.7, y: 22.8, w: 8.6, h: 22.0, conf: 0.97 },
  { id: 'b2', label: 'truck', x: 57.7, y: 24.2, w: 10.0, h: 25.5, conf: 0.95 },
  { id: 'b3', label: 'person', x: 52.3, y: 63.6, w: 4.9, h: 18.8, conf: 0.58, fix: 'motorcycle' },
  { id: 'b4', label: 'person', x: 92.0, y: 57.3, w: 3.5, h: 15.8, conf: 0.64, fix: 'cyclist' },
  { id: 'b5', label: 'car', x: 35.3, y: 57.9, w: 10.7, h: 20.4, conf: 0.96 },
  { id: 'b6', label: 'car', x: 19.6, y: 53.4, w: 12.4, h: 19.7, conf: 0.94 },
  { id: 'b7', label: 'car', x: 28.2, y: 42.7, w: 8.5, h: 12.9, conf: 0.91 },
  { id: 'b8', label: 'car', x: 40.0, y: 49.5, w: 8.4, h: 14.2, conf: 0.89 },
  { id: 'b9', label: 'car', x: 27.0, y: 82.8, w: 15.3, h: 17.2, conf: 0.93 },
  { id: 'b10', label: 'bus', x: 36.5, y: 15.1, w: 5.6, h: 9.4, conf: 0.88 },
  { id: 'b11', label: 'person', x: 93.5, y: 32.8, w: 4.0, h: 9.3, conf: 0.81 },
  { id: 'b12', label: 'car', x: 5.0, y: 39.4, w: 9.0, h: 15.2, conf: 0.9 },
];

/* ---------- PII specimen: plates and faces on the buses frame ---------- */

export const piiRegions: Box[] = [
  { id: 'p1', label: 'plate', x: 8.6, y: 80.8, w: 3.7, h: 2.3, conf: 0.96 },
  { id: 'p2', label: 'plate', x: 37.9, y: 78.6, w: 3.1, h: 2.2, conf: 0.95 },
  { id: 'p3', label: 'plate', x: 54.7, y: 84.7, w: 3.7, h: 2.2, conf: 0.97 },
  { id: 'p4', label: 'plate', x: 72.5, y: 85.2, w: 3.6, h: 2.3, conf: 0.97 },
  { id: 'p5', label: 'plate', x: 22.6, y: 73.5, w: 2.9, h: 1.9, conf: 0.9 },
  { id: 'p6', label: 'plate', x: 1.0, y: 78.2, w: 3.0, h: 2.1, conf: 0.86 },
  { id: 'p7', label: 'plate', x: 74.4, y: 69.0, w: 2.4, h: 1.5, conf: 0.82 },
  { id: 'f1', label: 'face', x: 92.2, y: 69.4, w: 1.8, h: 2.9, conf: 0.88 },
  { id: 'f2', label: 'face', x: 96.0, y: 70.0, w: 1.7, h: 2.9, conf: 0.86 },
  { id: 'f3', label: 'face', x: 96.2, y: 76.3, w: 1.7, h: 3.1, conf: 0.84 },
];

/* ---------- Text specimen ---------- */

export type EntityType = 'PERSON' | 'ORG' | 'LOC' | 'DATE';

export type Span = { text: string; type?: EntityType; fix?: EntityType; conf?: number };

/** One sentence split into spans; typed spans are entities. */
export const textSample: Span[] = [
  { text: 'Anika Rao', type: 'PERSON', conf: 0.98 },
  { text: ', who runs operations at ' },
  { text: 'Halden Freight', type: 'ORG', conf: 0.95 },
  { text: ', said on ' },
  { text: '14 March', type: 'DATE', conf: 0.97 },
  { text: ' that the ' },
  { text: 'Pune', type: 'ORG', fix: 'LOC', conf: 0.61 },
  { text: ' depot cleared its backlog two days early and that she expects the new routing to hold through the monsoon.' },
];

export const textVerdicts = {
  sentiment: { label: 'Positive', conf: 0.91 },
  category: { label: 'Operations update', conf: 0.88 },
  relation: { from: 'Anika Rao', rel: 'works_at', to: 'Halden Freight' },
};

export const entityColor: Record<EntityType, string> = {
  PERSON: 'var(--c-acc)',
  ORG: 'var(--c-task)',
  LOC: 'var(--c-cx)',
  DATE: 'var(--c-qual)',
};

/* ---------- Video specimen: tracks follow a slow pan over the street frame ---------- */

export const tracks = [
  { id: 12, boxId: 'b1', label: 'bus' },
  { id: 7, boxId: 'b2', label: 'truck' },
  { id: 31, boxId: 'b3', label: 'motorcycle' },
  { id: 18, boxId: 'b5', label: 'car' },
  { id: 44, boxId: 'b4', label: 'cyclist' },
];

export const exportSample = `{
  "asset": "street_0412.jpg",
  "label": "motorcycle",
  "bbox": [719, 488, 67, 144],
  "source": "ai",
  "ai_label": "person",
  "confidence": 0.58,
  "review": { "action": "corrected" },
  "qc": { "status": "approved" }
}`;
