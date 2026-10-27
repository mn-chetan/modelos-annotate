/*
 * The new-project draft: what a project needs before it can be created, shared by all
 * three directions so they differ in composition only. Limits mirror the live client
 * (src/services/api.ts uploadAssets, src/types.ts, IntakeForm accept lists).
 */
import type { Modality } from '../../src/showcase/content';

export type { Modality };

export const modalities: { key: Modality; title: string; line: string; unit: string }[] = [
  { key: 'image', title: 'Image', line: 'Photos and frames: boxes, classes and masks.', unit: 'images' },
  { key: 'text', title: 'Text', line: 'Documents and messages: entities, sentiment, categories.', unit: 'documents' },
  { key: 'video', title: 'Video', line: 'Clips: objects detected and followed across frames.', unit: 'clips' },
];

export const tasks: Record<Modality, string[]> = {
  image: ['Object detection', 'PII masking'],
  text: ['Named entities', 'Sentiment', 'Classification', 'Relation extraction'],
  video: ['Object tracking', 'Detection'],
};

export const suggestedClasses: Record<string, string[]> = {
  'Object detection': ['car', 'bus', 'truck', 'person'],
  'PII masking': ['number plate', 'face'],
  'Named entities': ['Person', 'Organisation', 'Location', 'Date'],
  Sentiment: ['Positive', 'Neutral', 'Negative'],
  Classification: ['Billing', 'Delivery', 'Product'],
  'Relation extraction': ['works_at', 'located_in'],
  'Object tracking': ['car', 'bus', 'cyclist'],
  Detection: ['car', 'person'],
};

/* ---------- Class colours ---------- */

/*
 * Assigned in this fixed order. Validated with the dataviz palette validator on --paper
 * (light): lightness band and chroma pass; worst adjacent CVD ΔE 6.1 (deutan), normal
 * vision 21.5. The 6–8 band is legal because every box, span and chip also carries its
 * class name as text. Yellow (flagged) and red (brand, rejected) are left out on purpose.
 */
export const palette: { hex: string; name: string }[] = [
  { hex: '#2A78D6', name: 'Blue' },
  { hex: '#EB6834', name: 'Orange' },
  { hex: '#1BAF7A', name: 'Aqua' },
  { hex: '#E87BA4', name: 'Pink' },
  { hex: '#008300', name: 'Green' },
  { hex: '#6250D6', name: 'Violet' },
  { hex: '#0E9BB5', name: 'Cyan' },
  { hex: '#A0652A', name: 'Brown' },
];

export const colourName = (hex: string) =>
  palette.find((p) => p.hex.toLowerCase() === hex.toLowerCase())?.name ?? hex.toUpperCase();

/** Ink or white, whichever reads better on the swatch (WCAG relative luminance). */
export function inkOn(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  const l = 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
  // Contrast with white vs with --ink (#15181E, L≈0.0094).
  return (1.05 / (l + 0.05)) >= ((l + 0.05) / 0.0594) ? '#FFFFFF' : '#15181E';
}

export type LabelClass = { id: string; name: string; colour: string };

let seq = 0;
export const newId = (p: string) => `${p}${Date.now().toString(36)}${(seq++).toString(36)}`;

/** The first palette colour no class uses yet; once all eight are taken, the least used. */
export function nextColour(classes: LabelClass[]): string {
  const counts = new Map(palette.map((p) => [p.hex, 0]));
  for (const c of classes) if (counts.has(c.colour)) counts.set(c.colour, counts.get(c.colour)! + 1);
  let best = palette[0].hex;
  for (const p of palette) if (counts.get(p.hex)! < counts.get(best)!) best = p.hex;
  return best;
}

export function classesFrom(names: string[]): LabelClass[] {
  const out: LabelClass[] = [];
  for (const name of names) out.push({ id: newId('c'), name, colour: nextColour(out) });
  return out;
}

export const MAX_CLASS_NAME = 40;

/** Why a class name can't be added, or null when it can. */
export function classNameProblem(name: string, classes: LabelClass[], exceptId?: string): string | null {
  const n = name.trim();
  if (!n) return 'Type a name for the class.';
  if (n.length > MAX_CLASS_NAME) return `Keep class names under ${MAX_CLASS_NAME} characters.`;
  const clash = classes.find((c) => c.id !== exceptId && c.name.trim().toLowerCase() === n.toLowerCase());
  if (clash) return `“${clash.name}” is already a class.`;
  return null;
}

/* ---------- Files ---------- */

export const accepts: Record<Modality, string[]> = {
  image: ['.avif', '.bmp', '.jpeg', '.jpg', '.png', '.tif', '.tiff', '.webp', '.zip'],
  text: ['.txt', '.csv', '.json', '.tsv', '.docx', '.pdf'],
  video: ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.zip'],
};

/** Direct uploads are batched below this per request; a single larger file is refused. */
export const MAX_FILE_BYTES = 24 * 1024 * 1024;

export type StagedFile = { id: string; file: File; path: string; thumb?: string };

export const extOf = (name: string) => `.${name.split('.').pop()?.toLowerCase() ?? ''}`;

/** Why this file won't upload for the chosen data type, or null when it will. */
export function fileProblem(f: File, modality: Modality): string | null {
  if (f.size === 0) return 'Empty file';
  if (f.size > MAX_FILE_BYTES) return 'Over 24 MB';
  if (!accepts[modality].includes(extOf(f.name))) return `Not a ${modality} file`;
  return null;
}

/** Best guess at the data type from what was dropped; null when nothing is recognisable. */
export function inferModality(files: File[]): Modality | null {
  const score: Record<Modality, number> = { image: 0, text: 0, video: 0 };
  for (const f of files) {
    const e = extOf(f.name);
    if (e === '.zip') continue;
    for (const m of ['image', 'text', 'video'] as Modality[]) if (accepts[m].includes(e)) score[m]++;
  }
  const best = (Object.keys(score) as Modality[]).sort((a, b) => score[b] - score[a])[0];
  return score[best] > 0 ? best : null;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(n < 10 * 1024 * 1024 ? 1 : 0)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(1)} GB`;
}
