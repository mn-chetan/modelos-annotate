/*
 * Shared pieces for showing labels: class colours, where a label came from, and the chips
 * that say where an item stands. Yellow always means "below the line, a person should look";
 * the AI's own approval is blue; a person's approval is green.
 */
import type { CSSProperties } from 'react';
import type { Annotation, LiveProject, Route } from '../store';
import { colourAt } from './new-project/model';

/** Each class's colour: the one saved with the project, else the palette's in fixed order. */
export function classColours(project: Pick<LiveProject, 'classList'>): Record<string, string> {
  return Object.fromEntries(project.classList.map((c, i) => [c.name, c.color || colourAt(i)]));
}

/** A label outside the project's classes (an older run, a renamed class) still gets a quiet colour. */
export const OTHER_COLOUR = '#8C909A';

export const colourStyle = (colour: string) => ({ '--box-colour': colour }) as CSSProperties;

const MODEL_NAMES: [string, string][] = [
  ['yolo', 'YOLO26'],
  ['dino', 'Grounding DINO'],
  ['florence', 'Florence-2'],
  ['fasterrcnn', 'Faster R-CNN'],
  ['faster_rcnn', 'Faster R-CNN'],
  ['gemini', 'Gemini'],
];

const nameOf = (id: string) => MODEL_NAMES.find(([k]) => id.toLowerCase().includes(k))?.[1];

/** Who drafted a label: a model by name, or a person. */
export function modelName(a: Annotation) {
  if (a.source === 'human') return 'Added by reviewer';
  const model = nameOf(a.model_id ?? '') ?? nameOf(String((a.provenance ?? {}).model_key ?? ''));
  if (a.source === 'human_modified') return model ? `${model}, corrected` : 'Corrected by reviewer';
  return model ?? 'AI';
}

/** The models that found the same object, when more than one did. */
export function agreeingModels(a: Annotation): string[] {
  const contributing = (a.provenance ?? {}).contributing_models;
  if (!Array.isArray(contributing)) return [];
  const names = contributing.map((m) => nameOf(String((m as { model_key?: string }).model_key ?? ''))).filter((n): n is string => !!n);
  return [...new Set(names)];
}

/** The AI's confidence, kept even after a person edits the label. */
export const aiConfidence = (a: Annotation) => a.original_ai_confidence ?? a.confidence ?? null;

export const pct = (v: number) => `${Math.round(v * 100)}%`;

const ROUTES: Record<Route, [string, string]> = {
  approvedByAi: ['is-ai', 'Approved by AI'],
  toReview: ['is-review', 'Below the line'],
  approved: ['is-pass', 'Approved'],
  rejected: ['is-neutral', 'Rejected'],
  failed: ['is-fail', 'AI failed'],
  notRun: ['is-queued', 'Not drafted'],
};

export const routeName = (r: Route) => ROUTES[r][1];

export function RouteChip({ route, running = false }: { route: Route; running?: boolean }) {
  if (running) return <span className="chip is-queued">Drafting…</span>;
  const [cls, text] = ROUTES[route];
  return <span className={`chip ${cls}`}>{text}</span>;
}

/** A label's decision: pending, accepted, corrected or rejected. */
export type Decision = 'pending' | 'approved' | 'edited' | 'rejected';

export const decisionOf = (a: Annotation): Decision =>
  a.review_status === 'approved' || a.review_status === 'edited' || a.review_status === 'rejected' ? a.review_status : 'pending';
