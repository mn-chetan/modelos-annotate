/*
 * The chart library: sixteen charts for annotators and their leads, rendered on the current
 * sample project so each can be judged on real-looking data. None of them uses time.
 * Pick the ones worth adding; picks persist in this browser and can be copied as a list.
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Check, Copy, Plus } from 'lucide-react';
import { images, type Project } from '../../../src/showcase/content';
import { ItemVisual, itemsFor, projectEyebrow } from '../../../src/next/pages/shared';
import { buildOverview, fmt, pctText, type Overview } from '../model';
import { Key, SampleView } from '../viz';
import { buildLibrary, type Library } from './data';
import { Columns, Diverge, DotStrip, FrameHeat, HBars, Heatmap, Reliability, SeqKey, StackRows } from './charts';
import './library.css';

type Group = 'trust' | 'fixes' | 'left' | 'people';
const GROUPS: [Group, string, string][] = [
  ['trust', 'Where to trust the AI', 'Where its annotations hold up, and where to look twice'],
  ['fixes', 'What reviewers fix', 'The mistakes the AI makes, so reviewers know what to look for'],
  ['left', 'What’s left to review', 'The work still waiting, and what makes it hard'],
  ['people', 'Reviewers', 'Whether reviewers agree, and where they differ'],
];

type Entry = {
  id: number;
  group: Group;
  title: string;
  question: string;
  why: string;
  source: string;
  wide?: boolean;
  render: (o: Overview, l: Library) => ReactNode;
  legend?: (o: Overview, l: Library) => ReactNode;
  only?: (o: Overview, l: Library) => string | null;
};

const FIX_COLORS = ['#2A57C0', '#D39B0A', '#1F8A5B', '#8D4AA6', '#D2432C'];
const pct1 = (v: number) => `${Math.round(v * 100)}%`;

const ENTRIES: Entry[] = [
  {
    id: 1,
    group: 'trust',
    title: 'Can we trust the AI’s confidence?',
    question: 'When the AI says it is 90% sure, is it right nine times in ten?',
    why: 'If the AI is overconfident, items above the approval line slip through with mistakes. Reviewers learn how much weight to give the score.',
    source: 'Reliability diagram (calibration); threshold routing in HITL tools',
    wide: true,
    render: (o, l) => <Reliability bins={l.calib} line={0.95} />,
    legend: () => (
      <>
        <Key color="#2A57C0">Approved by AI</Key>
        <Key color="#D39B0A">Sent to human review</Key>
        <Key color="var(--ink)" kind="line">
          Perfectly calibrated
        </Key>
      </>
    ),
  },
  {
    id: 2,
    group: 'trust',
    title: 'AI accuracy by class and confidence',
    question: 'For each class, how accurate is the AI at each confidence level?',
    why: 'Shows where a single approval line is unsafe: a class can stay weak even at high confidence, and needs a closer look whatever the score.',
    source: 'Per-class threshold tuning',
    render: (o, l) => (
      <Heatmap
        rows={l.names}
        cols={l.bands}
        values={l.classBand}
        format={pct1}
        rowTitle="Class"
        colTitle="AI confidence"
        describe={(r, c, v) => `${l.names[r]} at ${l.bands[c]}: right ${pctText(v)}`}
      />
    ),
    legend: () => <SeqKey low="Less accurate" high="More accurate" />,
  },
  {
    id: 3,
    group: 'trust',
    title: 'AI accuracy by size',
    question: 'Does the AI struggle with small or long items?',
    why: 'Tells reviewers where to zoom in. Small objects and long spans are where AI errors cluster.',
    source: 'Error analysis by object scale (COCO small, medium, large)',
    render: (o, l) => (
      <HBars
        rows={l.sizeRows.map((r) => ({ key: r.name, label: <span>{r.name}</span>, value: r.acc, note: `${r.name}: ${pctText(r.share)} of ${o.labelNoun}` }))}
        format={(v) => pctText(v, 1)}
        max={1}
        labelW={170}
        extra={{ name: 'Project', value: o.kept }}
      />
    ),
    legend: (o, l) => (
      <>
        <Key color="var(--blue)">AI accuracy · {l.sizeTitle.toLowerCase()}</Key>
        <Key color="var(--ink)" kind="line">
          Project average {pctText(o.kept, 1)}
        </Key>
      </>
    ),
  },
  {
    id: 4,
    group: 'trust',
    title: 'Where in the frame reviewers correct the AI',
    question: 'Are there parts of the picture where the AI keeps getting it wrong?',
    why: 'Blind spots, such as the far distance or the edges, show up as hot areas. Reviewers can scan those areas first.',
    source: 'Annotation quality heatmaps',
    render: (o, l) => <FrameHeat src={o.project.view === 'pii' ? images.buses : images.street} heat={l.heat} grid={l.heatGrid} />,
    legend: () => <SeqKey low="Fewer corrections" high="More" />,
    only: (o, l) => (l.hasFrame ? null : 'For image and video projects.'),
  },
  {
    id: 5,
    group: 'fixes',
    title: 'What the AI called it, and what reviewers changed it to',
    question: 'Which classes does the AI mix up, miss or invent?',
    why: 'The clearest single picture of AI mistakes. Each off-diagonal cell is a confusion reviewers keep fixing, and a candidate for a sharper guideline.',
    source: 'Confusion matrix (Label Studio, Dataloop); missed and extra after TIDE',
    wide: true,
    render: (o, l) => {
      const rows = [...l.names, 'Missed by AI'];
      const cols = [...l.names, 'Not an object'];
      const values: (number | null)[][] = [
        ...l.matrix.map((r, i) => [...r, l.extraCol[i]]),
        [...l.missedRow, null],
      ];
      return (
        <Heatmap
          rows={rows}
          cols={cols}
          values={values}
          neutral={(r, c) => r === c && r < l.names.length}
          rowTitle="AI said"
          colTitle="Reviewer’s final label"
          describe={(r, c, v) =>
            r === c ? `${rows[r]}: kept as is` : r === l.names.length ? `${cols[c]} the AI missed: ${fmt(v)}` : c === l.names.length ? `AI’s “${rows[r]}” was not an object: ${fmt(v)}` : `AI said ${rows[r]}, reviewer chose ${cols[c]}`
          }
        />
      );
    },
    legend: () => (
      <>
        <SeqKey low="Fewer" high="More corrections" />
        <span className="lib-note">The diagonal (kept as is) is left uncoloured.</span>
      </>
    ),
  },
  {
    id: 6,
    group: 'fixes',
    title: 'Most common mix-ups',
    question: 'Which confusions should reviewers watch for first?',
    why: 'A short, ranked watch-list with an example of each, the kind of thing to pin beside the guidelines.',
    source: 'Top confusion pairs (Label Studio)',
    render: (o, l) => (
      <HBars
        rows={l.pairs.map((p) => ({
          key: `${p.from} → ${p.to}`,
          value: p.n,
          color: '#2F52B4',
          note: `AI said ${p.from}; reviewer changed it to ${p.to}`,
          label: (
            <span className="lib-pair">
              {o.classes[p.j].sample.kind === 'crop' ? <SampleView sample={o.classes[p.j].sample} /> : null}
              <span>
                {p.from} <span className="muted">→</span> {p.to}
              </span>
            </span>
          ),
        }))}
        labelW={210}
      />
    ),
  },
  {
    id: 7,
    group: 'fixes',
    title: 'What kind of fixes reviewers make',
    question: 'Are corrections mostly wrong classes, loose boxes or missed objects?',
    why: 'Each kind needs a different habit. Wrong classes need guideline clarity, loose boxes need care at the edges, and misses need a slower scan.',
    source: 'TIDE error types (Bolya et al., 2020)',
    render: (o, l) => <HBars rows={l.fixes.map((f, i) => ({ key: f.name, label: <span>{f.name}</span>, value: f.n, color: FIX_COLORS[i], note: `${pctText(f.n / Math.max(1, o.corrections))} of corrections` }))} labelW={170} />,
  },
  {
    id: 8,
    group: 'fixes',
    title: 'Kinds of fix, class by class',
    question: 'Does each class go wrong in its own way?',
    why: 'A class that is mostly “missed” needs a different reminder than one that is mostly “wrong class”.',
    source: 'TIDE error types, per class',
    wide: true,
    render: (o, l) => <StackRows rows={l.perClassFixes.map((c) => ({ name: c.name, values: c.parts }))} parts={l.fixes.map((f) => f.name)} colors={FIX_COLORS} />,
    legend: (o, l) => (
      <>
        {l.fixes.map((f, i) => (
          <Key key={f.name} color={FIX_COLORS[i]}>
            {f.name}
          </Key>
        ))}
      </>
    ),
    only: (o, l) => (l.fixes.length > 1 ? null : 'Needs more than one kind of fix; sentiment has only one.'),
  },
  {
    id: 9,
    group: 'fixes',
    title: 'Does the AI over- or under-call each class?',
    question: 'How many of each class did the AI find, against how many there really are?',
    why: 'A class the AI under-calls means reviewers should look for what is missing, not just check what is there. An over-called class means checking for false alarms.',
    source: 'Prediction against ground-truth counts',
    render: (o, l) => (
      <Diverge
        rows={l.counts.map((c) => ({
          name: c.name,
          v: c.final ? (c.ai - c.final) / c.final : 0,
          note: `AI found ${fmt(c.ai)}; after review there are ${fmt(c.final)}`,
        }))}
        posName="AI over-calls"
        negName="AI misses"
        format={(v) => `${v > 0 ? '+' : v < 0 ? '−' : '±'}${Math.abs(v * 100).toFixed(1)}%`}
      />
    ),
  },
  {
    id: 10,
    group: 'left',
    title: 'What’s left to review, by AI confidence',
    question: 'How hard is the remaining review queue?',
    why: 'A queue piled at low confidence means slower, harder reviews ahead. Reviewers can plan for it and leads can pair people up.',
    source: 'Uncertainty-ordered review queues (active learning)',
    render: (o, l) => (
      <Columns
        rows={l.pending.filter((b) => b.lo >= 0.5).map((b) => ({ label: b.lo.toFixed(2), n: b.n, color: '#D39B0A' }))}
        xLabel="AI confidence of items waiting"
        unit={o.unit}
      />
    ),
    only: (o) => (o.states.review + o.states.qc > 0 ? null : 'Nothing left to review on this project.'),
  },
  {
    id: 11,
    group: 'left',
    title: 'Hardest items',
    question: 'Which items did the AI find most difficult?',
    why: 'Real examples of the hard cases, to calibrate on before a session, and the best candidates for retraining the model.',
    source: 'Least-confidence sampling (active learning)',
    wide: true,
    render: (o) => {
      const items = itemsFor(o.project)
        .sort((a, b) => a.conf - b.conf)
        .slice(0, 6);
      return (
        <ul className="lib-hard">
          {items.map((it) => (
            <li key={it.id}>
              <ItemVisual item={it} />
              <p>
                <span className="mono">{it.conf.toFixed(2)}</span> AI: {it.label}
                {it.fix ? (
                  <>
                    <br />
                    <b>Reviewer: {it.fix}</b>
                  </>
                ) : null}
              </p>
            </li>
          ))}
        </ul>
      );
    },
  },
  {
    id: 12,
    group: 'left',
    title: 'How crowded each item is',
    question: 'How many labels does a typical item hold?',
    why: 'Crowded items take more care and hide more misses. The long tail shows how many heavy items to expect.',
    source: 'Label density',
    render: (o, l) => <Columns rows={l.density.map((d) => ({ label: String(d.k), n: d.n }))} xLabel={`${o.labelNoun[0].toUpperCase()}${o.labelNoun.slice(1)} per ${o.unitOne}`} unit={o.unit} />,
  },
  {
    id: 13,
    group: 'left',
    title: 'Class balance',
    question: 'Are some classes rare?',
    why: 'Rare classes get fewer examples, so the AI learns them poorly and reviewers see them seldom. Both need extra attention.',
    source: 'Dataset class distribution',
    render: (o) => {
      const total = o.classes.reduce((s, c) => s + c.labels, 0);
      return (
        <HBars
          rows={[...o.classes]
            .sort((a, b) => b.labels - a.labels)
            .map((c) => ({
              key: c.name,
              value: c.labels / total,
              color: c.labels / total < 0.06 ? '#D39B0A' : '#2F52B4',
              note: `${fmt(c.labels)} ${o.labelNoun}${c.labels / total < 0.06 ? ' · rare' : ''}`,
              label: (
                <span className="ov-class">
                  <i style={{ background: c.color }} aria-hidden />
                  {c.name}
                </span>
              ),
            }))}
          format={(v) => pctText(v)}
        />
      );
    },
    legend: () => (
      <>
        <Key color="#2F52B4">Share of all labels</Key>
        <Key color="#D39B0A">Rare, under 6%</Key>
      </>
    ),
  },
  {
    id: 14,
    group: 'people',
    title: 'Do reviewers agree with each other?',
    question: 'On items two reviewers both checked, how often did they choose the same label?',
    why: 'Low agreement between two people points at an unclear guideline, not a bad reviewer. It is the fairest way to find what needs clarifying.',
    source: 'Inter-annotator agreement matrix (Label Studio, Encord)',
    render: (o, l) => {
      const names = o.people.map((p) => p.name.split(' ')[0]);
      return (
        <Heatmap
          rows={names}
          cols={names}
          values={l.agree.map((r, i) => r.map((v, j) => (i === j ? null : v)))}
          format={pct1}
          rowTitle="Reviewer"
          colTitle="Compared with"
          describe={(r, c, v) => `${o.people[r].name} and ${o.people[c].name} agree on ${pctText(v)}`}
        />
      );
    },
    legend: () => <SeqKey low="Agree less" high="Agree more" />,
    only: (o) => (o.people.length > 2 ? null : 'Needs three or more reviewers.'),
  },
  {
    id: 15,
    group: 'people',
    title: 'How often each reviewer changes the AI',
    question: 'Who changes the AI much more, or much less, than the team?',
    why: 'Someone far below the team may be approving without checking; someone far above may be over-correcting. Either way, a conversation, not a score.',
    source: 'Reviewer acceptance rate against the team (Label Studio members view)',
    render: (o) => {
      const vals = o.people.map((p) => p.editRate).sort((a, b) => a - b);
      const median = vals[Math.floor(vals.length / 2)];
      return (
        <DotStrip
          rows={o.people.map((p) => ({ name: p.name, v: p.editRate, flag: p.editRate < median * 0.5 || p.editRate > median * 1.6 }))}
          median={median}
          format={(v) => pctText(v)}
          lowNote="far from the team"
        />
      );
    },
    legend: () => (
      <>
        <Key color="#2A57C0">Within the usual range</Key>
        <Key color="#D39B0A">Far from the team</Key>
      </>
    ),
  },
  {
    id: 16,
    group: 'people',
    title: 'Who corrects which classes',
    question: 'Does one reviewer handle a class very differently from the others?',
    why: 'A reviewer with a hot cell on one class may read its guideline differently. That is a quick, specific thing to align on.',
    source: 'Reviewer by label breakdown',
    wide: true,
    render: (o, l) => (
      <Heatmap
        rows={o.people.map((p) => p.name)}
        cols={l.names}
        values={l.personClass}
        format={pct1}
        rowTitle="Reviewer"
        colTitle="Class"
        describe={(r, c, v) => `${o.people[r].name} changes the AI’s ${l.names[c]} on ${pctText(v)}`}
      />
    ),
    legend: () => <SeqKey low="Changes less" high="Changes more" />,
  },
];

const STORE = 'annotate.overview.picks';
function usePicks() {
  const [picks, setPicks] = useState<number[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(STORE) ?? '[]');
    } catch {
      return [];
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(STORE, JSON.stringify(picks));
    } catch {
      /* storage unavailable: picks last for this visit */
    }
  }, [picks]);
  const toggle = (id: number) => setPicks((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id].sort((a, b) => a - b)));
  return { picks, toggle, clear: () => setPicks([]) };
}

export default function LibraryVariant({ project }: { project: Project }) {
  const o = useMemo(() => buildOverview(project), [project]);
  const l = useMemo(() => buildLibrary(o), [o]);
  const [group, setGroup] = useState<Group | 'all'>('all');
  const { picks, toggle, clear } = usePicks();
  const [copied, setCopied] = useState(false);
  const shown = ENTRIES.filter((e) => group === 'all' || e.group === group);

  const copy = async () => {
    const text = picks.map((id) => `${id}. ${ENTRIES.find((e) => e.id === id)!.title}`).join('\n');
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked: the list stays visible in the bar */
    }
  };

  return (
    <div className="lib">
      <header className="lib-head">
        <p className="page-eyebrow">{projectEyebrow(project)} · chart library</p>
        <h1 className="page-title">Charts for annotators</h1>
        <p className="page-lede">
          Sixteen charts drawn on this project’s sample data, none of them about time. Pick the ones worth adding to the Overview; switch projects in the rail to see
          each on images, text or video.
        </p>
      </header>

      <nav className="lib-groups" aria-label="Chart groups">
        <button aria-pressed={group === 'all'} onClick={() => setGroup('all')}>
          All <b>{ENTRIES.length}</b>
        </button>
        {GROUPS.map(([id, name]) => (
          <button key={id} aria-pressed={group === id} onClick={() => setGroup(id)}>
            {name} <b>{ENTRIES.filter((e) => e.group === id).length}</b>
          </button>
        ))}
      </nav>

      {GROUPS.filter(([id]) => group === 'all' || group === id).map(([id, name, line]) => (
        <section key={id} className="lib-group" aria-labelledby={`lib-${id}`}>
          <div className="lib-group-head">
            <h2 id={`lib-${id}`}>{name}</h2>
            <p>{line}</p>
          </div>
          <div className="lib-grid">
            {shown
              .filter((e) => e.group === id)
              .map((e) => {
                const off = e.only?.(o, l);
                const on = picks.includes(e.id);
                return (
                  <article key={e.id} className={`lib-card${e.wide ? ' is-wide' : ''}${on ? ' is-picked' : ''}`} aria-labelledby={`lib-t-${e.id}`}>
                    <header className="lib-card-head">
                      <span className="lib-num">{e.id}</span>
                      <div>
                        <h3 id={`lib-t-${e.id}`}>{e.title}</h3>
                        <p className="lib-q">{e.question}</p>
                      </div>
                      <button className="lib-pick" aria-pressed={on} onClick={() => toggle(e.id)}>
                        {on ? <Check size={14} aria-hidden /> : <Plus size={14} aria-hidden />}
                        {on ? 'Picked' : 'Pick'}
                      </button>
                    </header>
                    {e.legend && !off ? <div className="ov-legend">{e.legend(o, l)}</div> : null}
                    <div className="lib-body">{off ? <p className="lib-off">{off}</p> : e.render(o, l)}</div>
                    <footer className="lib-card-foot">
                      <p>
                        <b>Why it helps.</b> {e.why}
                      </p>
                      <p className="lib-source">From: {e.source}</p>
                    </footer>
                  </article>
                );
              })}
          </div>
        </section>
      ))}

      <div className={`lib-tray${picks.length ? ' is-on' : ''}`} role="region" aria-label="Your picks" aria-live="polite">
        {picks.length ? (
          <>
            <span>
              <b>{picks.length} picked</b> {picks.map((id) => `#${id}`).join(', ')}
            </span>
            <button className="btn btn-ghost btn-sm" onClick={copy}>
              {copied ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />} {copied ? 'Copied' : 'Copy list'}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={clear}>
              Clear
            </button>
          </>
        ) : null}
      </div>
      <p className="ov-sample-note">Sample data. Figures are illustrative and agree with the Overview’s totals.</p>
    </div>
  );
}
