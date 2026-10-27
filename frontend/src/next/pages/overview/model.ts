/*
 * Sample analytics for the Overview. Every figure derives from the showcase project's
 * counts plus a per-task profile, so the numbers agree with each other and with the rest
 * of the app (badges, queues, the projects table). Illustrative, not product data: the real
 * values come from the production dashboard endpoints.
 *
 * The page answers how much the AI did on its own and how much went to people, so the
 * model works in those terms. Nothing here is measured over time.
 */
import { images, piiRegions, streetBoxes, textSamples, tickets, type Box, type Project, type TaskView } from '../../../showcase/content';

/** The confidence at or above which the AI's annotation is approved without review. */
export const AI_LINE = 0.95;

/* ---------- Deterministic noise ---------- */

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
function split(total: number, weights: number[]) {
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

/* ---------- Per-task profiles ---------- */

type Profile = {
  /** Share of AI annotations at or above the approval line. */
  approvedByAi: number;
  /** Share of the AI's labels reviewers kept unchanged. */
  kept: number;
  labelsPerItem: number;
  labelNoun: string;
  /** Share of a reviewer's items where they changed anything. */
  itemEditRate: number;
  team: number;
  /** Per class, in project order: share of labels, mean AI confidence, weight of corrections. */
  classes: { share: number; conf: number; corr: number }[];
  /** Which classes the model mixes up: [class a, class b, weight]. */
  confusions: [number, number, number][];
  /** Kinds of fix reviewers make, after TIDE's error types, with their shares. */
  fixes: [string, number][];
};

const profiles: Record<TaskView, Profile> = {
  detection: {
    approvedByAi: 0.58,
    kept: 0.912,
    labelsPerItem: 9.4,
    labelNoun: 'boxes',
    itemEditRate: 0.38,
    team: 5,
    classes: [
      { share: 0.52, conf: 0.93, corr: 12 },
      { share: 0.08, conf: 0.95, corr: 2 },
      { share: 0.07, conf: 0.91, corr: 4 },
      { share: 0.06, conf: 0.74, corr: 6 },
      { share: 0.05, conf: 0.71, corr: 9 },
      { share: 0.22, conf: 0.79, corr: 31 },
    ],
    confusions: [[5, 3, 5], [5, 4, 4], [3, 4, 3], [0, 2, 2], [1, 2, 2]],
    fixes: [['Wrong class', 0.38], ['Box adjusted', 0.31], ['Missed object', 0.17], ['Not an object', 0.1], ['Duplicate box', 0.04]],
  },
  pii: {
    approvedByAi: 0.71,
    kept: 0.94,
    labelsPerItem: 6.1,
    labelNoun: 'regions',
    itemEditRate: 0.21,
    team: 3,
    classes: [
      { share: 0.68, conf: 0.93, corr: 6 },
      { share: 0.32, conf: 0.86, corr: 14 },
    ],
    confusions: [[0, 1, 1]],
    fixes: [['Mask adjusted', 0.44], ['Missed region', 0.33], ['Not personal data', 0.17], ['Wrong type', 0.06]],
  },
  ner: {
    approvedByAi: 0.52,
    kept: 0.893,
    labelsPerItem: 7.8,
    labelNoun: 'entities',
    itemEditRate: 0.33,
    team: 6,
    classes: [
      { share: 0.24, conf: 0.95, corr: 6 },
      { share: 0.31, conf: 0.84, corr: 22 },
      { share: 0.22, conf: 0.86, corr: 17 },
      { share: 0.23, conf: 0.97, corr: 3 },
    ],
    confusions: [[1, 2, 5], [0, 1, 1], [2, 1, 2], [3, 1, 0.3]],
    fixes: [['Wrong entity type', 0.41], ['Span boundary fixed', 0.32], ['Missed entity', 0.19], ['Not an entity', 0.08]],
  },
  sentiment: {
    approvedByAi: 0.66,
    kept: 0.93,
    labelsPerItem: 1,
    labelNoun: 'labels',
    itemEditRate: 0.07,
    team: 4,
    classes: [
      { share: 0.41, conf: 0.92, corr: 19 },
      { share: 0.33, conf: 0.81, corr: 11 },
      { share: 0.26, conf: 0.9, corr: 7 },
    ],
    confusions: [[0, 1, 3], [1, 2, 2], [0, 2, 1]],
    fixes: [['Wrong sentiment', 1]],
  },
  tracking: {
    approvedByAi: 0.4,
    kept: 0.86,
    labelsPerItem: 14,
    labelNoun: 'tracks',
    itemEditRate: 0.52,
    team: 2,
    classes: [
      { share: 0.55, conf: 0.9, corr: 5 },
      { share: 0.1, conf: 0.93, corr: 1 },
      { share: 0.09, conf: 0.89, corr: 2 },
      { share: 0.13, conf: 0.72, corr: 3 },
      { share: 0.13, conf: 0.7, corr: 5 },
    ],
    confusions: [[3, 4, 4], [0, 2, 2], [1, 2, 1]],
    fixes: [['Box adjusted', 0.34], ['Identity switch', 0.27], ['Wrong class', 0.18], ['Missed object', 0.15], ['Not an object', 0.06]],
  },
};

/* ---------- Shapes ---------- */

export type Sample = { kind: 'crop'; box: Box; src: string } | { kind: 'text'; text: string };

export type ClassRow = {
  name: string;
  /** Validated class palette, in fixed order (same as New project). */
  color: string;
  labels: number;
  conf: number;
  /** AI accuracy: share of the AI's labels in this class reviewers kept unchanged. */
  keptRate: number;
  corrections: number;
  sample: Sample;
};

export type Person = { name: string; initials: string; assigned: number; done: number; editRate: number };

/** Items by AI confidence: 24 bins of 0.025 from 0.40 to 1.00. */
export type Bin = { lo: number; hi: number; n: number };

const CLASS_COLORS = ['#2A78D6', '#EB6834', '#1BAF7A', '#E87BA4', '#008300', '#6250D6', '#0E9BB5', '#A0652A'];
const PEOPLE = ['Marcus Lee', 'Sara Okafor', 'Daniel Costa', 'Priya Nair', 'Meera Shah', 'Tomás Reyes'];
const PERSON_SHAPE = [
  { load: 1.25, edit: 1.0 },
  { load: 1.1, edit: 1.1 },
  { load: 1.0, edit: 0.95 },
  { load: 0.9, edit: 1.05 },
  { load: 0.8, edit: 0.22 },
  { load: 0.6, edit: 0.9 },
];

function buildBins(drafted: number, approvedByAi: number): Bin[] {
  // Below the line, counts rise toward it; above it, two bins share what the AI approved.
  const below = Array.from({ length: 22 }, (_, i) => Math.exp((2.2 * i) / 22) * (1 + 0.08 * Math.sin(i * 1.7)));
  const sumBelow = below.reduce((a, b) => a + b, 0);
  const weights = [...below.map((w) => (w / sumBelow) * (1 - approvedByAi)), approvedByAi * 0.43, approvedByAi * 0.57];
  return split(drafted, weights).map((n, i) => ({ lo: +(0.4 + i * 0.025).toFixed(3), hi: +(0.425 + i * 0.025).toFixed(3), n }));
}

/** What a given approval line does to the work. */
export function routeAt(o: Overview, line: number) {
  let auto = 0;
  let missed = 0;
  for (const b of o.bins) {
    if (b.lo >= line - 1e-9) {
      auto += b.n;
      // Assumes calibrated confidence: a 0.96 label is wrong about 4% of the time.
      missed += b.n * (1 - (b.lo + b.hi) / 2) * 0.9;
    }
  }
  const review = o.drafted - auto;
  return { auto, review, missed: Math.round(missed), share: o.drafted ? review / o.drafted : 0 };
}

function sampleFor(p: Project, name: string, i: number): Sample {
  const lower = name.toLowerCase();
  switch (p.view) {
    case 'detection':
    case 'tracking': {
      const box = streetBoxes.find((b) => (b.fix ?? b.label) === lower) ?? streetBoxes[i % streetBoxes.length];
      return { kind: 'crop', box, src: images.street };
    }
    case 'pii':
      return { kind: 'crop', box: piiRegions.find((r) => (lower.includes('plate') ? r.label === 'plate' : r.label === 'face'))!, src: images.buses };
    case 'ner': {
      const type = { person: 'PERSON', organisation: 'ORG', location: 'LOC', date: 'DATE' }[lower];
      for (const s of textSamples) {
        const span = s.spans.find((x) => (x.fix ?? x.type) === type);
        if (span) return { kind: 'text', text: span.text };
      }
      return { kind: 'text', text: name };
    }
    case 'sentiment':
      return { kind: 'text', text: (tickets.find((x) => (x.fix ?? x.ai) === name) ?? tickets[0]).text };
  }
}

export type Overview = ReturnType<typeof buildOverview>;

export function buildOverview(p: Project) {
  const prof = profiles[p.view];
  const rnd = seeded(p.id);
  const done = p.reviewPending === 0 && p.qcPending === 0 && p.aiDone === p.assets;

  const queued = p.assets - p.aiDone;
  const drafted = p.aiDone;
  const bins = buildBins(drafted, prof.approvedByAi);
  const autoAccepted = bins.filter((b) => b.lo >= AI_LINE - 1e-9).reduce((s, b) => s + b.n, 0);
  const toPeople = drafted - autoAccepted;
  const approvedAuto = Math.min(autoAccepted, p.approved);
  const approvedHuman = p.approved - approvedAuto;
  // Items in quality check are still with people, so they count as in review here.
  const inReview = p.reviewPending + p.qcPending;
  const reviewed = approvedHuman + p.qcPending;

  const labels = Math.round(p.assets * prof.labelsPerItem);
  const labelsReviewed = Math.round(reviewed * prof.labelsPerItem);
  const corrections = Math.round(labelsReviewed * (1 - prof.kept));

  /* Classes */
  const corrW = prof.classes.reduce((s, c) => s + c.corr, 0);
  const classes: ClassRow[] = p.classes.map((name, i) => {
    const m = prof.classes[i];
    const labRev = Math.max(1, Math.round(labelsReviewed * m.share));
    const corr = Math.round((corrections * m.corr) / corrW);
    return {
      name,
      color: CLASS_COLORS[i % CLASS_COLORS.length],
      labels: Math.round(labels * m.share),
      conf: m.conf,
      keptRate: Math.max(0.4, 1 - corr / labRev),
      corrections: corr,
      sample: sampleFor(p, name, i),
    };
  });

  /* Reviewers */
  const shapes = PERSON_SHAPE.slice(0, prof.team);
  const loadSum = shapes.reduce((s, x) => s + x.load, 0);
  const people: Person[] = PEOPLE.slice(0, prof.team).map((name, i) => {
    const doneN = Math.round((reviewed * shapes[i].load) / loadSum);
    return {
      name,
      initials: name
        .split(' ')
        .map((w) => w[0])
        .join(''),
      assigned: doneN + Math.round((p.reviewPending * shapes[i].load) / loadSum),
      done: doneN,
      editRate: Math.min(0.95, prof.itemEditRate * shapes[i].edit),
    };
  });

  /* Can we trust the AI's confidence? Stated confidence against how often it was right. */
  const calibration = [
    [0.4, 0.5, 0.36],
    [0.5, 0.6, 0.46],
    [0.6, 0.7, 0.57],
    [0.7, 0.8, 0.68],
    [0.8, 0.9, 0.8],
    [0.9, 0.95, 0.89],
    [0.95, 1, 0.972],
  ].map(([lo, hi, acc]) => ({
    lo,
    hi,
    acc: Math.min(0.995, acc + (rnd() - 0.5) * 0.03),
    items: bins.filter((b) => b.lo >= lo - 1e-9 && b.hi <= hi + 1e-9).reduce((s, b) => s + b.n, 0),
  }));

  /* What kind of fixes reviewers make. */
  const fixes = prof.fixes.map(([name], i) => ({ name, n: split(corrections, prof.fixes.map(([, w]) => w))[i] }));

  /* Most common mix-ups: wrong-class corrections, split across the class pairs the model confuses. */
  const wrongShare = prof.fixes[0][1];
  const mixups = classes
    .flatMap((c, i) => {
      const weights = classes.map((_, j) => {
        if (j === i) return 0;
        const hit = prof.confusions.find(([a, b]) => (a === i && b === j) || (a === j && b === i));
        return hit ? hit[2] : 0.25;
      });
      return split(Math.round(c.corrections * wrongShare), weights).map((n, j) => ({ from: c.name, to: classes[j].name, toIndex: j, n }));
    })
    .filter((m) => m.n > 0 && m.from !== m.to)
    .sort((a, b) => b.n - a.n)
    .slice(0, 5);

  /* Who corrects which classes: each reviewer's change rate, class by class. */
  const avgFix = Math.max(0.01, 1 - prof.kept);
  const byReviewer = people.map((person) =>
    classes.map((c) => Math.min(0.95, (1 - c.keptRate) * (person.editRate / (avgFix * 4)) * (0.85 + rnd() * 0.3))),
  );

  return {
    project: p,
    done,
    assets: p.assets,
    unit: p.unit,
    unitOne: p.unit.replace(/s$/, ''),
    labels,
    labelNoun: prof.labelNoun,
    approved: p.approved,
    remaining: p.assets - p.approved,
    queued,
    drafted,
    autoAccepted,
    toPeople,
    approvedAuto,
    approvedHuman,
    inReview,
    labelsReviewed,
    corrections,
    kept: prof.kept,
    bins,
    classes,
    people,
    calibration,
    fixes,
    mixups,
    byReviewer,
  };
}

/* ---------- Formatting ---------- */

export const fmt = (n: number) => Math.round(n).toLocaleString('en-GB');
export const pctText = (v: number, digits = 0) => `${(v * 100).toFixed(digits)}%`;
