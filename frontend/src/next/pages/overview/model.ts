/*
 * The Overview's figures, computed from a live project's items and labels. The page answers
 * how much the AI did on its own and how much went to people, so the model works in those
 * terms. Nothing here is measured over time, and nothing is invented: where the evidence is
 * thin, the counts behind each figure travel with it so the page can say so.
 */
import { api } from '../../../services/api';
import type { Box } from '../../../showcase/content';
import { routeOf, type Annotation, type LiveAsset, type LiveProject } from '../../store';

/* ---------- Shapes ---------- */

export type Sample =
  | { kind: 'crop'; box: Box; src: string; ratio: number }
  | { kind: 'text'; text: string };

export type ClassRow = {
  name: string;
  color: string;
  /** Labels in this class now, rejected ones excluded. */
  labels: number;
  /** Mean AI confidence of the AI's labels in this class; null when it drafted none. */
  conf: number | null;
  /** AI labels in this class a person has decided on. */
  reviewed: number;
  /** AI accuracy: the share of reviewed AI labels kept unchanged; null before any review. */
  keptRate: number | null;
  corrections: number;
  sample: Sample | null;
};

/** Items by their weakest label's confidence, in bins of 0.025 up to 1. */
export type Bin = { lo: number; hi: number; n: number; checked: number; wrong: number };

export type CalBin = { lo: number; hi: number; acc: number; items: number };

export type Hard = { id: string; name: string; conf: number; label: string; fix?: string; sample: Sample | null; route: string };

export type Overview = {
  project: LiveProject;
  line: number;
  floor: number;
  done: boolean;
  assets: number;
  unit: string;
  labels: number;
  labelNoun: string;
  approved: number;
  remaining: number;
  queued: number;
  failed: number;
  drafted: number;
  autoAccepted: number;
  toPeople: number;
  approvedAuto: number;
  approvedHuman: number;
  rejected: number;
  inReview: number;
  labelsReviewed: number;
  corrections: number;
  kept: number | null;
  bins: Bin[];
  classes: ClassRow[];
  calibration: CalBin[];
  fixes: { name: string; n: number }[];
  mixups: { from: string; to: string; toIndex: number; n: number }[];
  hardest: Hard[];
};

/* ---------- Reading a label ---------- */

const DECIDED = new Set(['approved', 'edited', 'rejected']);

const aiConfidence = (a: Annotation) => a.original_ai_confidence ?? a.confidence ?? null;
const prov = (a: Annotation) => (a.provenance ?? {}) as Record<string, unknown>;
const isAi = (a: Annotation) => a.source === 'ai' || a.source === 'human_modified' || !!a.model_id || typeof prov(a).original_ai_label === 'string';
const originalLabel = (a: Annotation) => (typeof prov(a).original_ai_label === 'string' ? (prov(a).original_ai_label as string) : a.label);
const isRejected = (a: Annotation) => a.review_status === 'rejected';
const isEdited = (a: Annotation) => a.source === 'human_modified' || prov(a).human_edited === true || a.review_status === 'edited';
const classChanged = (a: Annotation) => originalLabel(a) !== a.label;

/** A label a person has decided on, directly or by approving or rejecting its item. */
function isReviewed(a: Annotation, decidedAssets: Set<string>) {
  return DECIDED.has(a.review_status ?? '') || a.source === 'human_modified' || decidedAssets.has(a.asset_id);
}

const spanText = (a: Annotation) => a.geometry?.text ?? a.text_span?.text ?? '';

function sampleOf(a: Annotation | undefined, asset: LiveAsset | undefined, kind: LiveProject['kind']): Sample | null {
  if (!a || !asset) return null;
  if (kind === 'boxes') {
    if (!(a.w > 0 && a.h > 0)) return null;
    const ratio = asset.width && asset.height ? asset.width / asset.height : 4 / 3;
    return { kind: 'crop', box: { id: a.id, label: a.label, x: a.x, y: a.y, w: a.w, h: a.h, conf: aiConfidence(a) ?? 0 }, src: api.getAssetImageUrl(asset.id), ratio };
  }
  const text = spanText(a) || asset.text_analysis?.text?.slice(0, 140) || '';
  return text ? { kind: 'text', text } : null;
}

const labelNounFor = (kind: LiveProject['kind']) => (kind === 'boxes' ? 'boxes' : kind === 'spans' ? 'entities' : 'labels');

const FIX_NAMES: Record<LiveProject['kind'], [string, string, string, string]> = {
  boxes: ['Wrong class', 'Box adjusted', 'Missed object', 'Not an object'],
  spans: ['Wrong entity type', 'Span boundary fixed', 'Missed entity', 'Not an entity'],
  document: ['Wrong label', 'Label adjusted', 'Label added', 'Label removed'],
};

/* ---------- Building the figures ---------- */

export function buildOverview(p: LiveProject, items: LiveAsset[], all: Annotation[]): Overview {
  const line = p.line;
  const byAsset = new Map(items.map((a) => [a.id, a]));
  const routes = new Map(items.map((a) => [a.id, routeOf(a)]));
  const count = (r: string) => items.filter((a) => routes.get(a.id) === r).length;
  const decidedAssets = new Set(items.filter((a) => ['approved', 'rejected'].includes(routes.get(a.id)!)).map((a) => a.id));

  const failed = count('failed');
  const queued = count('notRun');
  const approvedAuto = count('approvedByAi');
  const approvedHuman = count('approved');
  const rejected = count('rejected');
  const inReview = count('toReview');
  const drafted = approvedAuto + approvedHuman + rejected + inReview;
  const toPeople = drafted - approvedAuto;
  const approved = approvedAuto + approvedHuman;

  const live = all.filter((a) => !isRejected(a));
  const aiReviewed = all.filter((a) => isAi(a) && isReviewed(a, decidedAssets));
  const corrected = aiReviewed.filter((a) => isEdited(a) || isRejected(a));
  const kept = aiReviewed.length ? 1 - corrected.length / aiReviewed.length : null;

  /* Items by their weakest AI label: the label that decides whether the AI can approve it. */
  const labelsOf = new Map<string, Annotation[]>();
  for (const a of all) labelsOf.set(a.asset_id, [...(labelsOf.get(a.asset_id) ?? []), a]);
  const weakest = new Map<string, number>();
  for (const [id, rows] of labelsOf) {
    const confs = rows.filter(isAi).map(aiConfidence).filter((c): c is number => c != null);
    if (confs.length) weakest.set(id, Math.min(...confs));
  }
  const lowest = Math.min(0.4, ...weakest.values());
  const floor = Math.max(0, Math.floor(lowest * 10) / 10);
  const binCount = Math.round((1 - floor) / 0.025);
  const bins: Bin[] = Array.from({ length: binCount }, (_, i) => ({
    lo: +(floor + i * 0.025).toFixed(3),
    hi: +(floor + (i + 1) * 0.025).toFixed(3),
    n: 0,
    checked: 0,
    wrong: 0,
  }));
  for (const [id, c] of weakest) {
    const bin = bins[Math.min(binCount - 1, Math.max(0, Math.floor((c - floor) / 0.025 + 1e-9)))];
    bin.n++;
    if (decidedAssets.has(id)) {
      bin.checked++;
      if ((labelsOf.get(id) ?? []).some((a) => isEdited(a) || isRejected(a) || a.source === 'human')) bin.wrong++;
    }
  }

  /* Can we trust the AI's confidence? Each reviewed AI label: what it claimed, and whether it held. */
  const edges = [floor, ...[0.5, 0.6, 0.7, 0.8, 0.9, 0.95].filter((e) => e > floor), 1];
  const calibration: CalBin[] = edges.slice(0, -1).map((lo, i) => {
    const hi = edges[i + 1];
    const inBin = aiReviewed.filter((a) => {
      const c = aiConfidence(a);
      return c != null && c >= lo && (c < hi || (hi === 1 && c <= 1));
    });
    const right = inBin.filter((a) => !isEdited(a) && !isRejected(a)).length;
    return { lo, hi, acc: inBin.length ? right / inBin.length : 0, items: inBin.length };
  });

  /* Classes, in project order. */
  const classes: ClassRow[] = p.classList.map(({ name, color }) => {
    const mine = all.filter((a) => originalLabel(a) === name && isAi(a));
    const confs = mine.map(aiConfidence).filter((c): c is number => c != null);
    const rev = mine.filter((a) => isReviewed(a, decidedAssets));
    const corr = rev.filter((a) => isEdited(a) || isRejected(a)).length;
    const best = [...live.filter((a) => a.label === name)].sort((a, b) => (aiConfidence(b) ?? 1) - (aiConfidence(a) ?? 1))[0];
    return {
      name,
      color,
      labels: live.filter((a) => a.label === name).length,
      conf: confs.length ? confs.reduce((s, c) => s + c, 0) / confs.length : null,
      reviewed: rev.length,
      keptRate: rev.length ? 1 - corr / rev.length : null,
      corrections: corr,
      sample: sampleOf(best, best && byAsset.get(best.asset_id), p.kind),
    };
  });

  /* What kind of fixes reviewers make. */
  const names = FIX_NAMES[p.kind];
  const wrongClass = corrected.filter((a) => !isRejected(a) && classChanged(a)).length;
  const reshaped = corrected.filter((a) => !isRejected(a) && !classChanged(a)).length;
  // A label a person added counts as a missed one only where the AI drafted that item too.
  const draftedByAi = new Set(all.filter((a) => a.source === 'ai' || !!a.model_id).map((a) => a.asset_id));
  const added = all.filter((a) => a.source === 'human' && !isRejected(a) && draftedByAi.has(a.asset_id)).length;
  const removed = corrected.filter(isRejected).length;
  const fixes = [
    { name: names[0], n: wrongClass },
    { name: names[1], n: reshaped },
    { name: names[2], n: added },
    { name: names[3], n: removed },
  ].filter((f) => f.n > 0);

  /* Most common mix-ups: what the AI called it, and what reviewers changed it to. */
  const pairs = new Map<string, { from: string; to: string; n: number }>();
  for (const a of all) {
    if (isRejected(a) || !classChanged(a)) continue;
    const key = `${originalLabel(a)}→${a.label}`;
    const hit = pairs.get(key) ?? { from: originalLabel(a), to: a.label, n: 0 };
    hit.n++;
    pairs.set(key, hit);
  }
  const mixups = [...pairs.values()]
    .sort((a, b) => b.n - a.n)
    .slice(0, 5)
    .map((m) => ({ ...m, toIndex: Math.max(0, p.classes.indexOf(m.to)) }));

  /* The hardest items: lowest weakest-label confidence first, with the reviewer's correction. */
  const hardest: Hard[] = [...weakest]
    .sort((a, b) => a[1] - b[1])
    .slice(0, 6)
    .map(([id, conf]) => {
      const rows = labelsOf.get(id) ?? [];
      const worst = rows.find((a) => aiConfidence(a) === conf) ?? rows[0];
      const asset = byAsset.get(id);
      const fix = worst && isRejected(worst) ? 'Rejected' : worst && classChanged(worst) ? worst.label : undefined;
      return {
        id,
        name: asset?.filename ?? id,
        conf,
        label: worst ? originalLabel(worst) : '—',
        fix,
        sample: sampleOf(worst, asset, p.kind),
        route: routes.get(id) ?? 'notRun',
      };
    });

  return {
    project: p,
    line,
    floor,
    done: items.length > 0 && approved === items.length,
    assets: items.length,
    unit: p.unit,
    labels: live.length,
    labelNoun: labelNounFor(p.kind),
    approved,
    remaining: items.length - approved,
    queued,
    failed,
    drafted,
    autoAccepted: approvedAuto,
    toPeople,
    approvedAuto,
    approvedHuman,
    rejected,
    inReview,
    labelsReviewed: aiReviewed.length,
    corrections: corrected.length,
    kept,
    bins,
    classes,
    calibration,
    fixes,
    mixups,
    hardest,
  };
}

/** What a given approval line does to the drafted work, and what reviewers found above it. */
export function routeAt(o: Overview, line: number) {
  let auto = 0;
  let checked = 0;
  let wrong = 0;
  for (const b of o.bins) {
    if (b.lo >= line - 1e-9) {
      auto += b.n;
      checked += b.checked;
      wrong += b.wrong;
    }
  }
  const total = o.bins.reduce((s, b) => s + b.n, 0);
  const review = total - auto;
  return { auto, review, checked, wrong, share: total ? review / total : 0 };
}

/* ---------- Formatting ---------- */

export const fmt = (n: number) => Math.round(n).toLocaleString('en-GB');
export const pctText = (v: number, digits = 0) => `${(v * 100).toFixed(digits)}%`;
