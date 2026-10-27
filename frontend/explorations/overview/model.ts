/*
 * Sample analytics behind the Overview directions. Every figure is derived from the showcase
 * project's counts plus a per-task profile, so the numbers agree with each other and with
 * the rest of the app (badges, queues, the projects table). Illustrative, not product data.
 *
 * The measures mirror what the old dashboards report (production, text HITL, quality):
 * routing by confidence threshold, AI kept as drafted, HITL share, AHT, headcount,
 * throughput against plan, class breakdown, annotator safeguards, triage and QC.
 */
import {
  images,
  piiRegions,
  streetBoxes,
  textSamples,
  tickets,
  type Box,
  type Project,
  type TaskView,
} from '../../src/showcase/content';

/** "Today" for the showcase: Tuesday 27 October 2026. */
export const TODAY = new Date(2026, 9, 27);
const DAY = 86_400_000;

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

/* ---------- Per-task profiles ---------- */

type ClassMeta = { share: number; conf: number; corr: number; trend: number };

type Profile = {
  /** Shares of AI-drafted items by routing band at the default thresholds. */
  routing: { auto: number; review: number; audit: number };
  /** Share of AI labels reviewers kept as drafted. */
  kept: number;
  qcPass: number;
  agreement: number;
  /** Quality against QC, best band first. */
  bandsTitle: string;
  bands: [string, number][];
  fit: { name: string; value: string } | null;
  ahtSec: number;
  labelsPerItem: number;
  labelNoun: string;
  /** Share of a reviewer's items where they changed anything. */
  itemEditRate: number;
  team: number;
  due: Date;
  idPrefix: string;
  classes: ClassMeta[];
};

const profiles: Record<TaskView, Profile> = {
  detection: {
    routing: { auto: 0.58, review: 0.34, audit: 0.08 },
    kept: 0.912,
    qcPass: 0.962,
    agreement: 0.88,
    bandsTitle: 'Box fit against QC',
    bands: [['IoU 0.95 and up', 0.41], ['0.85 to 0.95', 0.39], ['0.70 to 0.85', 0.15], ['Below 0.70', 0.05]],
    fit: { name: 'Mean IoU', value: '0.88' },
    ahtSec: 38,
    labelsPerItem: 9.4,
    labelNoun: 'boxes',
    itemEditRate: 0.38,
    team: 5,
    due: new Date(2026, 10, 6),
    idPrefix: 'IMG',
    classes: [
      { share: 0.52, conf: 0.93, corr: 12, trend: 0.4 },
      { share: 0.08, conf: 0.95, corr: 2, trend: 0.2 },
      { share: 0.07, conf: 0.91, corr: 4, trend: -0.3 },
      { share: 0.06, conf: 0.74, corr: 6, trend: 2.1 },
      { share: 0.05, conf: 0.71, corr: 9, trend: 1.4 },
      { share: 0.22, conf: 0.79, corr: 31, trend: -1.2 },
    ],
  },
  pii: {
    routing: { auto: 0.71, review: 0.24, audit: 0.05 },
    kept: 0.94,
    qcPass: 0.971,
    agreement: 0.91,
    bandsTitle: 'Mask fit against QC',
    bands: [['IoU 0.95 and up', 0.36], ['0.85 to 0.95', 0.42], ['0.70 to 0.85', 0.17], ['Below 0.70', 0.05]],
    fit: { name: 'Mean IoU', value: '0.87' },
    ahtSec: 22,
    labelsPerItem: 6.1,
    labelNoun: 'regions',
    itemEditRate: 0.21,
    team: 3,
    due: new Date(2026, 9, 30),
    idPrefix: 'CAM',
    classes: [
      { share: 0.68, conf: 0.93, corr: 6, trend: 0.3 },
      { share: 0.32, conf: 0.86, corr: 14, trend: -0.8 },
    ],
  },
  ner: {
    routing: { auto: 0.52, review: 0.38, audit: 0.1 },
    kept: 0.893,
    qcPass: 0.951,
    agreement: 0.86,
    bandsTitle: 'Span match against QC',
    bands: [['Exact span', 0.71], ['One word off', 0.17], ['Partial overlap', 0.09], ['Missed', 0.03]],
    fit: { name: 'Span F1', value: '0.93' },
    ahtSec: 54,
    labelsPerItem: 7.8,
    labelNoun: 'entities',
    itemEditRate: 0.33,
    team: 6,
    due: new Date(2026, 10, 3),
    idPrefix: 'DOC',
    classes: [
      { share: 0.24, conf: 0.95, corr: 6, trend: 0.2 },
      { share: 0.31, conf: 0.84, corr: 22, trend: -1.1 },
      { share: 0.22, conf: 0.86, corr: 17, trend: 0.9 },
      { share: 0.23, conf: 0.97, corr: 3, trend: 0 },
    ],
  },
  sentiment: {
    routing: { auto: 0.66, review: 0.28, audit: 0.06 },
    kept: 0.93,
    qcPass: 0.982,
    agreement: 0.82,
    bandsTitle: 'Label match against QC',
    bands: [['Same label', 0.9], ['Neighbouring label', 0.08], ['Opposite label', 0.02]],
    fit: null,
    ahtSec: 9,
    labelsPerItem: 1,
    labelNoun: 'labels',
    itemEditRate: 0.07,
    team: 4,
    due: new Date(2026, 9, 26),
    idPrefix: 'TCK',
    classes: [
      { share: 0.41, conf: 0.92, corr: 19, trend: -0.6 },
      { share: 0.33, conf: 0.81, corr: 11, trend: 1.2 },
      { share: 0.26, conf: 0.9, corr: 7, trend: 0.3 },
    ],
  },
  tracking: {
    routing: { auto: 0.4, review: 0.45, audit: 0.15 },
    kept: 0.86,
    qcPass: 0.94,
    agreement: 0.84,
    bandsTitle: 'Track fit against QC',
    bands: [['IoU 0.95 and up', 0.28], ['0.85 to 0.95', 0.41], ['0.70 to 0.85', 0.22], ['Below 0.70', 0.09]],
    fit: { name: 'Mean IoU', value: '0.83' },
    ahtSec: 390,
    labelsPerItem: 14,
    labelNoun: 'tracks',
    itemEditRate: 0.52,
    team: 2,
    due: new Date(2026, 10, 13),
    idPrefix: 'CLIP',
    classes: [
      { share: 0.55, conf: 0.9, corr: 5, trend: 0.5 },
      { share: 0.1, conf: 0.93, corr: 1, trend: 0 },
      { share: 0.09, conf: 0.89, corr: 2, trend: -0.4 },
      { share: 0.13, conf: 0.72, corr: 3, trend: 1.8 },
      { share: 0.13, conf: 0.7, corr: 5, trend: 1.1 },
    ],
  },
};

/* ---------- Shapes ---------- */

export type ItemState = 'approved' | 'qc' | 'review' | 'queued';
export const STATE_ORDER: readonly ItemState[] = ['approved', 'qc', 'review', 'queued'];
export const STATE_NAME: Record<ItemState, string> = {
  approved: 'Approved',
  qc: 'In quality check',
  review: 'Waiting for review',
  queued: 'Waiting for AI',
};

export type Day = { date: Date; label: string; approved: number; weekend: boolean; today: boolean };

export type Bin = { lo: number; hi: number; n: number };

export type ClassRow = {
  name: string;
  /** Validated class palette, in fixed order (same as New project). */
  color: string;
  labels: number;
  conf: number;
  keptRate: number;
  corrections: number;
  trend: number;
  approvedPct: number;
  sample: Sample;
};

export type Sample = { kind: 'crop'; box: Box; src: string; masked?: boolean } | { kind: 'text'; text: string; mark?: string };

export type Person = {
  name: string;
  initials: string;
  assigned: number;
  done: number;
  ahtSec: number;
  editRate: number;
  qcPass: number;
  flags: ('fast' | 'qc')[];
};

export type Action = { title: string; why: string; tab: 'review' | 'quality' | 'ai' | 'reports' | 'overview'; cta: string };

export type Overview = ReturnType<typeof buildOverview>;

const CLASS_COLORS = ['#2A78D6', '#EB6834', '#1BAF7A', '#E87BA4', '#008300', '#6250D6', '#0E9BB5', '#A0652A'];
const PEOPLE = ['Marcus Lee', 'Sara Okafor', 'Daniel Costa', 'Priya Nair', 'Meera Shah', 'Tomás Reyes'];
const PERSON_SHAPE = [
  { load: 1.25, aht: 0.94, edit: 1.0, qc: 0.972 },
  { load: 1.1, aht: 1.06, edit: 1.1, qc: 0.965 },
  { load: 1.0, aht: 1.0, edit: 0.95, qc: 0.968 },
  { load: 0.9, aht: 1.14, edit: 1.05, qc: 0.921 },
  { load: 0.8, aht: 0.41, edit: 0.22, qc: 0.948 },
  { load: 0.6, aht: 0.97, edit: 0.9, qc: 0.958 },
];

const short = (d: Date) => d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
export const longDate = (d: Date) => d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });

/* ---------- Builders ---------- */

function buildDays(p: Project, prof: Profile, done: boolean): Day[] {
  const rnd = seeded(`${p.id}:days`);
  const n = 56;
  const raw = Array.from({ length: n }, (_, i) => {
    const date = new Date(TODAY.getTime() - (n - 1 - i) * DAY);
    const dow = date.getDay();
    const weekend = dow === 0 || dow === 6;
    const ramp = 0.35 + 0.65 * (i / (n - 1));
    let w = (weekend ? (dow === 6 ? 0.34 : 0.22) : 1) * ramp * (0.86 + rnd() * 0.28);
    if (i === n - 1) w *= 0.52; // today, so far
    if (done && i >= n - 2) w = i === n - 1 ? 0 : w * 0.6; // finished yesterday
    return { date, weekend, w };
  });
  const sum = raw.reduce((s, d) => s + d.w, 0);
  const total = Math.round(p.approved * 0.97);
  const exact = raw.map((d) => (d.w / sum) * total);
  const ints = exact.map(Math.floor);
  let rest = total - ints.reduce((a, b) => a + b, 0);
  exact
    .map((v, i) => [v - Math.floor(v), i] as const)
    .sort((a, b) => b[0] - a[0])
    .forEach(([, i]) => {
      if (rest-- > 0) ints[i]++;
    });
  return raw.map((d, i) => ({ date: d.date, label: short(d.date), approved: ints[i], weekend: d.weekend, today: i === n - 1 }));
}

function buildBins(aiDone: number, prof: Profile): Bin[] {
  // 24 bins of 0.025 from 0.40 to 1.00: 12 below 0.70, 10 in review, 2 auto-accepted.
  const shape = (k: number, len: number, rise: number) => Array.from({ length: len }, (_, i) => Math.exp((rise * i) / len) * (1 + 0.08 * Math.sin(i * 1.7 + k)));
  const parts = [
    { share: prof.routing.audit, w: shape(1, 12, 2.4) },
    { share: prof.routing.review, w: shape(2, 10, 1.3) },
    { share: prof.routing.auto, w: [0.43, 0.57] },
  ];
  const counts: number[] = [];
  for (const part of parts) {
    const s = part.w.reduce((a, b) => a + b, 0);
    for (const w of part.w) counts.push((w / s) * part.share * aiDone);
  }
  // Integer counts that still sum to aiDone.
  const ints = counts.map(Math.floor);
  let rest = aiDone - ints.reduce((a, b) => a + b, 0);
  counts
    .map((c, i) => [c - Math.floor(c), i] as const)
    .sort((a, b) => b[0] - a[0])
    .forEach(([, i]) => {
      if (rest-- > 0) ints[i]++;
    });
  return ints.map((n, i) => ({ lo: +(0.4 + i * 0.025).toFixed(3), hi: +(0.425 + i * 0.025).toFixed(3), n }));
}

/** What a pair of thresholds does to the work: the simulator behind every routing view. */
export function routeAt(o: Overview, lo: number, hi: number) {
  let auto = 0;
  let audit = 0;
  let missed = 0;
  for (const b of o.bins) {
    const mid = (b.lo + b.hi) / 2;
    if (b.lo >= hi - 1e-9) {
      auto += b.n;
      // Assumes calibrated confidence: a 0.96 label is wrong about 4% of the time.
      missed += b.n * (1 - mid) * 0.9;
    } else if (b.hi <= lo + 1e-9) audit += b.n;
  }
  const review = o.drafted - auto - audit;
  const people = review + audit;
  const hours = ((review + audit * 1.6) * o.ahtSec) / 3600;
  return { auto, review, audit, people, hours, missed: Math.round(missed), share: o.drafted ? people / o.drafted : 0 };
}

function sampleFor(p: Project, name: string, i: number): Sample {
  const lower = name.toLowerCase();
  switch (p.view) {
    case 'detection':
    case 'tracking': {
      const box = streetBoxes.find((b) => (b.fix ?? b.label) === lower) ?? streetBoxes[i % streetBoxes.length];
      return { kind: 'crop', box, src: images.street };
    }
    case 'pii': {
      const box = piiRegions.find((r) => (lower.includes('plate') ? r.label === 'plate' : r.label === 'face'))!;
      return { kind: 'crop', box, src: images.buses, masked: false };
    }
    case 'ner': {
      const type = { person: 'PERSON', organisation: 'ORG', location: 'LOC', date: 'DATE' }[lower];
      for (const s of textSamples) {
        const span = s.spans.find((x) => (x.fix ?? x.type) === type);
        if (span) return { kind: 'text', text: span.text, mark: type };
      }
      return { kind: 'text', text: name };
    }
    case 'sentiment': {
      const t = tickets.find((x) => (x.fix ?? x.ai) === name) ?? tickets[0];
      return { kind: 'text', text: t.text };
    }
  }
}

export function buildOverview(p: Project) {
  const prof = profiles[p.view];
  const rnd = seeded(p.id);
  const done = p.reviewPending === 0 && p.qcPending === 0 && p.aiDone === p.assets;

  const queued = p.assets - p.aiDone;
  const drafted = p.aiDone;
  const bins = buildBins(drafted, prof);
  const autoAccepted = bins.slice(22).reduce((s, b) => s + b.n, 0);
  const audited = bins.slice(0, 12).reduce((s, b) => s + b.n, 0);
  const toPeople = drafted - autoAccepted;
  const approvedAuto = Math.min(autoAccepted, p.approved);
  const approvedHuman = p.approved - approvedAuto;
  const reviewed = approvedHuman + p.qcPending;
  const sentBack = Math.round(p.reviewPending * 0.14);

  const labels = Math.round(p.assets * prof.labelsPerItem);
  const labelsReviewed = Math.round(reviewed * prof.labelsPerItem);
  const corrections = Math.round(labelsReviewed * (1 - prof.kept));

  const qcChecked = Math.round(reviewed * 0.25 + approvedAuto * 0.05);
  const qcFailed = Math.round(qcChecked * (1 - prof.qcPass));

  /* Production over time */
  const days = buildDays(p, prof, done);
  const recent = days.slice(-8, -1).filter((d) => !d.weekend);
  const perWorkingDay = recent.length ? recent.reduce((s, d) => s + d.approved, 0) / recent.length : 0;
  // The plan set at kickoff: every item over the working days from the start to the due date.
  let workingDays = 0;
  for (let t = days[0].date.getTime(); t <= prof.due.getTime(); t += DAY) {
    const dow = new Date(t).getDay();
    if (dow !== 0 && dow !== 6) workingDays++;
  }
  const planned = Math.max(1, Math.round(p.assets / workingDays));
  const remaining = p.assets - p.approved;
  let eta: Date | null = null;
  if (remaining > 0 && perWorkingDay > 0) {
    let need = remaining;
    const d = new Date(TODAY);
    // Today's remaining hours count as half a day.
    need -= perWorkingDay * 0.45;
    while (need > 0) {
      d.setTime(d.getTime() + DAY);
      if (d.getDay() !== 0 && d.getDay() !== 6) need -= perWorkingDay;
    }
    eta = d;
  }
  const status: 'done' | 'ahead' | 'on track' | 'at risk' =
    remaining === 0 ? 'done' : eta && eta.getTime() <= prof.due.getTime() - 2 * DAY ? 'ahead' : eta && eta <= prof.due ? 'on track' : 'at risk';

  /* Weekly series for the trend lines (eight weeks, oldest first) */
  const drift = (end: number, step: number, wobble: number) =>
    Array.from({ length: 8 }, (_, i) => end - step * (7 - i) + (rnd() - 0.5) * wobble * (i === 7 ? 0 : 1));
  const weekly = {
    kept: drift(prof.kept, 0.004, 0.006),
    qcPass: drift(prof.qcPass, 0.002, 0.008),
    hitl: drift(toPeople / Math.max(1, drafted), -0.006, 0.01),
    ahtSec: drift(prof.ahtSec, -prof.ahtSec * 0.015, prof.ahtSec * 0.05),
  };

  /* Classes */
  const classes: ClassRow[] = p.classes.map((name, i) => {
    const m = prof.classes[i];
    const corrW = prof.classes.reduce((s, c) => s + c.corr, 0);
    const lab = Math.round(labels * m.share);
    const labRev = Math.max(1, Math.round(labelsReviewed * m.share));
    const corr = Math.round((corrections * m.corr) / corrW);
    return {
      name,
      color: CLASS_COLORS[i % CLASS_COLORS.length],
      labels: lab,
      conf: m.conf,
      keptRate: Math.max(0.4, 1 - corr / labRev),
      corrections: corr,
      trend: m.trend,
      approvedPct: Math.min(1, (p.approved / p.assets) * (1 + (m.conf - 0.86) * 0.12)),
      sample: sampleFor(p, name, i),
    };
  });

  /* People */
  const team = PEOPLE.slice(0, prof.team);
  const shapes = PERSON_SHAPE.slice(0, prof.team);
  const loadSum = shapes.reduce((s, x) => s + x.load, 0);
  const people: Person[] = team.map((name, i) => {
    const s = shapes[i];
    const doneN = Math.round((reviewed * s.load) / loadSum);
    const pending = Math.round((p.reviewPending * s.load) / loadSum);
    return {
      name,
      initials: name
        .split(' ')
        .map((w) => w[0])
        .join(''),
      assigned: doneN + pending,
      done: doneN,
      ahtSec: prof.ahtSec * s.aht,
      editRate: Math.min(0.95, prof.itemEditRate * s.edit),
      qcPass: s.qc,
      flags: [],
    };
  });
  const medianAht = [...people].sort((a, b) => a.ahtSec - b.ahtSec)[Math.floor(people.length / 2)]?.ahtSec ?? prof.ahtSec;
  for (const person of people) {
    // The old safeguard: very fast and rarely edits suggests rubber-stamping.
    if (person.ahtSec < medianAht * 0.5 && person.editRate < prof.itemEditRate * 0.4) person.flags.push('fast');
    if (person.qcPass < 0.93) person.flags.push('qc');
  }

  /* Triage */
  const triage = {
    disputed: done ? 0 : Math.max(1, Math.round(reviewed * 0.006)),
    fast: people.filter((x) => x.flags.includes('fast')).reduce((s, x) => s + Math.round(x.done * 0.18), 0),
    edge: audited,
  };

  /* The items, one square each (or one per group on large projects) */
  const unit = [1, 2, 4, 5, 10, 20].find((u) => p.assets / u <= 1300) ?? 50;
  const squares = Math.ceil(p.assets / unit);
  const counts = {
    approved: Math.round(p.approved / unit),
    qc: Math.max(p.qcPending ? 1 : 0, Math.round(p.qcPending / unit)),
    review: Math.max(p.reviewPending ? 1 : 0, Math.round(p.reviewPending / unit)),
  };
  const queuedSq = Math.max(0, squares - counts.approved - counts.qc - counts.review);
  const frnd = seeded(`${p.id}:field`);
  const active = squares - queuedSq;
  const order = Array.from({ length: active }, (_, i) => ({ i, k: i / active + (frnd() - 0.5) * 0.55 * (i / active) ** 1.6 })).sort((a, b) => a.k - b.k);
  const field: { state: ItemState; back: boolean; conf: number }[] = Array.from({ length: squares }, () => ({ state: 'queued', back: false, conf: 0 }));
  order.forEach(({ i }, rank) => {
    const state: ItemState = rank < counts.approved ? 'approved' : rank < counts.approved + counts.qc ? 'qc' : 'review';
    const conf = state === 'approved' ? 0.9 + frnd() * 0.1 : 0.5 + frnd() * 0.45;
    field[i] = { state, back: false, conf };
  });
  const reviewIdx = field.map((f, i) => (f.state === 'review' ? i : -1)).filter((i) => i >= 0);
  for (let k = 0; k < Math.round(sentBack / unit); k++) field[reviewIdx[Math.floor(frnd() * reviewIdx.length)]].back = true;

  /* What to do next */
  const avgCorrRate = corrections / Math.max(1, labelsReviewed);
  const weakest = [...classes].sort((a, b) => a.keptRate - b.keptRate)[0];
  const flagged = people.find((x) => x.flags.length);
  const actions: Action[] = [];
  if (p.reviewPending)
    actions.push({
      title: `Clear the ${p.reviewPending.toLocaleString('en-GB')} ${p.unit} waiting for review`,
      why: `About ${hoursText((p.reviewPending * prof.ahtSec) / 3600)} of reviewer time at ${ahtText(prof.ahtSec)} each, lowest confidence first.`,
      tab: 'review',
      cta: 'Open review',
    });
  if (weakest && 1 - weakest.keptRate > avgCorrRate * 1.6)
    actions.push({
      title: `Tighten the guideline for “${weakest.name}”`,
      why: `Reviewers correct it ${((1 - weakest.keptRate) / avgCorrRate).toFixed(1)}× as often as the average class; it carries ${Math.round((weakest.corrections / Math.max(1, corrections)) * 100)}% of all corrections.`,
      tab: 'ai',
      cta: 'See AI results',
    });
  if (flagged)
    actions.push({
      title: `Look over ${flagged.name}’s recent work`,
      why: flagged.flags.includes('fast')
        ? `${ahtText(flagged.ahtSec)} per ${p.unit.replace(/s$/, '')} with edits on ${pctText(flagged.editRate)}: fast enough to suggest approvals without a real check.`
        : `QC pass rate ${pctText(flagged.qcPass)}, below the 93% bar.`,
      tab: 'quality',
      cta: 'Open quality check',
    });
  if (p.qcPending)
    actions.push({
      title: `Audit ${p.qcPending} sampled ${p.unit}`,
      why: 'Independent checks keep the pass rate honest; each one takes about a minute.',
      tab: 'quality',
      cta: 'Open quality check',
    });
  if (done)
    actions.unshift({
      title: 'Export the approved labels',
      why: `All ${p.assets.toLocaleString('en-GB')} ${p.unit} are reviewed and passed quality check; each label leaves with its review trail.`,
      tab: 'overview',
      cta: 'Export labels',
    });

  return {
    project: p,
    done,
    assets: p.assets,
    unit: p.unit,
    unitOne: p.unit.replace(/s$/, ''),
    states: { approved: p.approved, qc: p.qcPending, review: p.reviewPending, queued } as Record<ItemState, number>,
    sentBack,
    drafted,
    autoAccepted,
    audited,
    toPeople,
    approvedAuto,
    approvedHuman,
    reviewed,
    labels,
    labelNoun: prof.labelNoun,
    labelsReviewed,
    corrections,
    kept: prof.kept,
    qcPass: prof.qcPass,
    qcChecked,
    qcFailed,
    agreement: prof.agreement,
    bandsTitle: prof.bandsTitle,
    bands: prof.bands,
    fit: prof.fit,
    leakage: 0.004 + rnd() * 0.004,
    ahtSec: prof.ahtSec,
    perReviewerHour: 3600 / prof.ahtSec,
    hoursSaved: (approvedAuto * prof.ahtSec) / 3600,
    reviewHours: (reviewed * prof.ahtSec) / 3600,
    team: prof.team,
    due: prof.due,
    days,
    planned,
    perWorkingDay,
    remaining,
    eta,
    status,
    weekly,
    bins,
    classes,
    people,
    triage,
    unitPerSquare: unit,
    field,
    idPrefix: prof.idPrefix,
    actions: actions.slice(0, 3),
  };
}

/* ---------- Formatting shared by the directions ---------- */

export const fmt = (n: number) => Math.round(n).toLocaleString('en-GB');
export const pctText = (v: number, digits = 0) => `${(v * 100).toFixed(digits)}%`;
export function ahtText(sec: number) {
  return sec >= 90 ? `${(sec / 60).toFixed(1)} min` : `${Math.round(sec)} s`;
}
export function hoursText(h: number) {
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} minutes`;
  if (h < 10) return `${h.toFixed(1)} hours`;
  return `${Math.round(h)} hours`;
}
export const itemId = (o: Overview, i: number) => {
  const pad = (n: number) => String(n).padStart(4, '0');
  const first = i * o.unitPerSquare + 1;
  const last = Math.min(o.assets, first + o.unitPerSquare - 1);
  return o.unitPerSquare === 1 ? `${o.idPrefix}-${pad(first)}` : `${o.idPrefix}-${pad(first)} to ${pad(last)}`;
};
export const statusText: Record<Overview['status'], string> = {
  done: 'Complete',
  ahead: 'Ahead of plan',
  'on track': 'On track',
  'at risk': 'At risk',
};

/** Item-state colours, validated together (all-pairs CVD ≥ 8.3); waiting-for-AI is drawn hollow. */
export const STATE_COLOR: Record<ItemState, string> = {
  approved: '#1F8A5B',
  qc: '#8D4AA6',
  review: '#D39B0A',
  queued: 'transparent',
};
export const SENT_BACK = '#D2432C';
/** Ordinal quality ramp, best band darkest (validated: monotone L, light end 2.16:1). */
export const BAND_RAMP = ['#1A3480', '#3559BE', '#6A88D6', '#9AB0E6'];

export { profiles };
export type { Profile };
