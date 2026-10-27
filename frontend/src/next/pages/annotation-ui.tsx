import type { CSSProperties } from 'react';
import type { Annotation } from '../store';

export const BOX_COLOURS = [
  '#47B8E0',
  '#F0AB55',
  '#77CEA6',
  '#B4A0F5',
  '#E59BC4',
  '#DCD178',
];
export function classColours(
  classes: string[],
  ontology: { name?: string; color?: string }[] = [],
) {
  return Object.fromEntries(
    classes.map((name, i) => [
      name,
      ontology.find((c) => c.name === name)?.color ||
        BOX_COLOURS[i % BOX_COLOURS.length],
    ]),
  );
}
export function modelName(annotation: Annotation) {
  const id = annotation.model_id?.toLowerCase() || '';
  if (id.includes('yolo')) return 'YOLO26';
  if (id.includes('dino')) return 'Grounding DINO';
  if (id.includes('florence')) return 'Florence';
  return annotation.source === 'human' || annotation.source === 'human_modified'
    ? 'Human annotation'
    : 'AI prediction';
}
export function decisionName(status?: string) {
  return (
    (
      {
        approved: 'Accepted',
        edited: 'Corrected',
        rejected: 'Rejected',
        final_approved: 'Approved',
        human_rejected: 'Rejected',
        needs_review: 'Needs review',
        pending: 'Not reviewed',
        ready: 'Ready',
        uploaded: 'Uploaded',
        processing: 'Processing',
        queued: 'Queued',
        failed: 'Failed',
      } as Record<string, string>
    )[status || 'pending'] ||
    status?.replaceAll('_', ' ') ||
    'Not reviewed'
  );
}
export function DecisionBadge({ status }: { status?: string }) {
  return (
    <span className={`decision-badge is-${status || 'pending'}`}>
      <i />
      {decisionName(status)}
    </span>
  );
}
export const colourStyle = (colour: string) =>
  ({ '--box-colour': colour }) as CSSProperties;
