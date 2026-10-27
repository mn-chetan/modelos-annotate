/*
 * Sample data for the chart library. Derived from the same overview model, so every total
 * agrees with the Overview's cards (corrections, reviewed labels, classes, reviewers).
 * Illustrative only; none of it involves time.
 */
import type { TaskView } from '../../../src/showcase/content';
import type { Overview } from '../model';

function seeded(key: string) {
  let h = 2166136261;
  for (const c of key) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return () => {
    h = Math.imul(h ^ (h >>> 15), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    return ((h ^= h >>> 16) >>> 0) / 4294967296;
  };
}

/** Split an integer total by weights so the parts sum exactly (largest remainder). */
export function split(total: number, weights: number[]) {
  const sum = weights.reduce((a, b) => a + b, 0) || 1;
  const exact = weights.map((w) => (w / sum) * total);
  const ints = exact.map(Math.floor);
  let rest = total - ints.reduce((a, b) => a + b, 0);
  exact
    .map((v, i) => [v - Math.floor(v), i] as const)
    .sort((a, b) => b[0] - a[0])
    .forEach(([, i]) => {
      if (rest-- > 0) ints[i]++;
    });
  return ints;
}

/** Which classes the model tends to mix up, per task (by class index). */
const AFFINITY: Record<TaskView, [number, number, number][]> = {
  detection: [[5, 3, 5], [5, 4, 4], [3, 4, 3], [0, 2, 2], [1, 2, 2]],
  pii: [[0, 1, 1]],
  ner: [[1, 2, 5], [0, 1, 1], [2, 1, 2], [3, 1, 0.3]],
  sentiment: [[0, 1, 3], [1, 2, 2], [0, 2, 1]],
  tracking: [[3, 4, 4], [0, 2, 2], [1, 2, 1]],
};

/** Correction types, after TIDE: what kind of fix a reviewer made. */
const FIX_TYPES: Record<TaskView, [string, number][]> = {
  detection: [['Wrong class', 0.38], ['Box adjusted', 0.31], ['Missed object', 0.17], ['Not an object', 0.1], ['Duplicate box', 0.04]],
  pii: [['Mask adjusted', 0.44], ['Missed region', 0.33], ['Not personal data', 0.17], ['Wrong type', 0.06]],
  ner: [['Wrong entity type', 0.41], ['Span boundary fixed', 0.32], ['Missed entity', 0.19], ['Not an entity', 0.08]],
  sentiment: [['Wrong sentiment', 1]],
  tracking: [['Box adjusted', 0.34], ['Identity switch', 0.27], ['Wrong class', 0.18], ['Missed object', 0.15], ['Not an object', 0.06]],
};

const SIZE_BANDS: Record<TaskView, { title: string; bands: [string, number, number][] }> = {
  detection: { title: 'Object size in the frame', bands: [['Small, under 32 px', 0.31, 0.71], ['Medium', 0.46, 0.93], ['Large, over 96 px', 0.23, 0.98]] },
  pii: { title: 'Region size in the frame', bands: [['Small, under 16 px', 0.42, 0.88], ['Medium', 0.41, 0.96], ['Large', 0.17, 0.99]] },
  ner: { title: 'Entity length', bands: [['One word', 0.46, 0.93], ['Two or three words', 0.41, 0.88], ['Four words or more', 0.13, 0.74]] },
  sentiment: { title: 'Ticket length', bands: [['Short, under 15 words', 0.38, 0.95], ['Medium', 0.44, 0.94], ['Long, over 60 words', 0.18, 0.86]] },
  tracking: { title: 'Object size in the frame', bands: [['Small, under 32 px', 0.36, 0.69], ['Medium', 0.44, 0.9], ['Large, over 96 px', 0.2, 0.97]] },
};

export function buildLibrary(o: Overview) {
  const view = o.project.view;
  const rnd = seeded(`${o.project.id}:lib`);
  const names = o.classes.map((c) => c.name);
  const n = names.length;
  const fixes = FIX_TYPES[view];
  const fixCounts = split(o.corrections, fixes.map(([, w]) => w));
  const wrongClassShare = fixes[0][1];

  /* Confusion: AI label (rows) vs reviewer's final label (columns), plus missed and extra. */
  const reviewedPerClass = split(o.labelsReviewed, o.classes.map((c) => c.labels));
  const matrix: number[][] = names.map(() => names.map(() => 0));
  const extraCol: number[] = names.map(() => 0);
  const missedRow: number[] = names.map(() => 0);
  o.classes.forEach((c, i) => {
    const wrong = Math.round(c.corrections * wrongClassShare);
    const weights = names.map((_, j) => {
      if (j === i) return 0;
      const hit = AFFINITY[view].find(([a, b]) => (a === i && b === j) || (a === j && b === i));
      return hit ? hit[2] : 0.25;
    });
    split(wrong, weights).forEach((v, j) => (matrix[i][j] = v));
    extraCol[i] = Math.round(c.corrections * (fixes.find(([k]) => /Not an|Not personal/.test(k))?.[1] ?? 0));
    missedRow[i] = Math.round(c.corrections * (fixes.find(([k]) => /Missed/.test(k))?.[1] ?? 0) * (0.7 + rnd() * 0.6));
    const off = matrix[i].reduce((a, b) => a + b, 0) + extraCol[i];
    matrix[i][i] = Math.max(0, reviewedPerClass[i] - off);
  });
  const pairs = names
    .flatMap((a, i) => names.map((b, j) => ({ from: a, to: b, n: matrix[i][j], i, j })))
    .filter((p) => p.i !== p.j && p.n > 0)
    .sort((a, b) => b.n - a.n)
    .slice(0, 5);

  /* AI counts against final counts per class: what the AI over- or under-calls. */
  const counts = names.map((name, j) => {
    // The AI called it `name` (its row, plus boxes that were not objects at all) …
    const ai = matrix[j].reduce((a, b) => a + b, 0) + extraCol[j];
    // … and after review it is `name` (its column, plus objects the AI missed).
    const final = matrix.reduce((s, row) => s + row[j], 0) + missedRow[j];
    return { name, ai, final };
  });

  /* Calibration: does a 0.9 really mean right nine times in ten? */
  const calib = [
    [0.4, 0.5, 0.36],
    [0.5, 0.6, 0.46],
    [0.6, 0.7, 0.57],
    [0.7, 0.8, 0.68],
    [0.8, 0.9, 0.8],
    [0.9, 0.95, 0.89],
    [0.95, 1, 0.972],
  ].map(([lo, hi, acc]) => {
    const items = o.bins.filter((b) => b.lo >= lo - 1e-9 && b.hi <= hi + 1e-9).reduce((s, b) => s + b.n, 0);
    return { lo, hi, acc: Math.min(0.995, acc + (rnd() - 0.5) * 0.03), items };
  });

  /* Accuracy by class and confidence band. */
  const bands: [string, number, number][] = [
    ['Below 0.70', 0.4, 0.7],
    ['0.70 to 0.85', 0.7, 0.85],
    ['0.85 to 0.95', 0.85, 0.95],
    ['0.95 and up', 0.95, 1],
  ];
  const classBand = o.classes.map((c) =>
    bands.map((_, k) => Math.max(0.3, Math.min(0.995, c.keptRate + [-0.24, -0.09, 0.0, 0.05][k] + (rnd() - 0.5) * 0.04 - (0.9 - c.conf) * 0.25 * (k < 2 ? 1 : 0)))),
  );

  /* Accuracy by size (or length for text). */
  const size = SIZE_BANDS[view];
  const sizeRows = size.bands.map(([name, share, acc]) => ({ name, share, acc: Math.min(0.995, acc * (o.kept / 0.91)) }));

  /* What is left to review, by confidence band. */
  const pendingWeights = o.bins.filter((b) => b.hi <= 0.95 + 1e-9).map((b) => b.n);
  const pending = split(o.states.review + o.states.qc, pendingWeights).map((v, i) => ({ lo: o.bins[i].lo, hi: o.bins[i].hi, n: v }));

  /* How crowded each item is: labels per item. */
  const lam = o.labels / o.assets;
  const maxK = Math.max(6, Math.ceil(lam * 2.6));
  const pois = Array.from({ length: maxK + 1 }, (_, k) => {
    let v = Math.exp(-lam);
    for (let i = 1; i <= k; i++) v *= lam / i;
    return v;
  });
  const density = split(o.assets, pois).map((n2, k) => ({ k, n: n2 }));

  /* Where in the frame reviewers corrected the AI (image and video only). */
  const cols = 10;
  const rows = 6;
  const blobs = view === 'pii' ? [[0.92, 0.72, 0.1, 1], [0.12, 0.8, 0.12, 0.7]] : [[0.5, 0.32, 0.16, 1], [0.93, 0.6, 0.08, 0.8], [0.52, 0.7, 0.1, 0.6]];
  const heatW = Array.from({ length: rows * cols }, (_, idx) => {
    const x = ((idx % cols) + 0.5) / cols;
    const y = (Math.floor(idx / cols) + 0.5) / rows;
    return 0.05 + blobs.reduce((s, [bx, by, r, w]) => s + w * Math.exp(-((x - bx) ** 2 + (y - by) ** 2) / (2 * r * r)), 0);
  });
  const heat = split(o.corrections, heatW);

  /* Reviewers: pairwise agreement on items both reviewed, and change rate by class. */
  const people = o.people;
  const agree = people.map((a, i) =>
    people.map((b, j) => {
      if (i === j) return 1;
      const seed = seeded(`${o.project.id}:${Math.min(i, j)}-${Math.max(i, j)}`)();
      const low = a.flags.includes('fast') || b.flags.includes('fast') ? 0.07 : 0;
      return Math.min(0.97, o.agreement + (seed - 0.5) * 0.08 - low);
    }),
  );
  const avgFix = 1 - o.kept;
  const personClass = people.map((p) => o.classes.map((c) => Math.min(0.95, (1 - c.keptRate) * (p.editRate / Math.max(0.01, avgFix * 4)) * (0.85 + rnd() * 0.3))));

  return {
    names,
    colors: o.classes.map((c) => c.color),
    matrix,
    extraCol,
    missedRow,
    pairs,
    counts,
    fixes: fixes.map(([name], i) => ({ name, n: fixCounts[i] })),
    perClassFixes: o.classes.map((c) => ({ name: c.name, color: c.color, parts: split(c.corrections, fixes.map(([, w]) => w)) })),
    calib,
    bands: bands.map(([b]) => b),
    classBand,
    sizeTitle: size.title,
    sizeRows,
    pending,
    density,
    heat,
    heatGrid: { cols, rows },
    hasFrame: view === 'detection' || view === 'pii' || view === 'tracking',
    agree,
    personClass,
  };
}

export type Library = ReturnType<typeof buildLibrary>;
