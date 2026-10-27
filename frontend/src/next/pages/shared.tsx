/*
 * Shared page pieces: headers, project-aware specimens and the per-task sample items the
 * static showcase draws from. Everything here is illustrative sample data.
 */
import type { ReactNode } from 'react';
import {
  images,
  piiRegions,
  streetBoxes,
  textSample,
  textSamples,
  tickets,
  tracks,
  type Box,
  type Project,
  type Sentiment,
  type Span,
} from '../../showcase/content';
import { DetectionFrame, EntityText, Filmstrip, ObjectCrop, PiiFrame, TrackFrame, type Stage } from '../../showcase/specimens';
import { modalityLabel } from '../nav';

export const fmt = (n: number) => n.toLocaleString('en-GB');
export const pct = (a: number, b: number) => (b === 0 ? 0 : Math.round((a / b) * 100));

export function PageHead({
  eyebrow,
  title,
  lede,
  actions,
}: {
  eyebrow?: string;
  title: string;
  lede?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div>
        {eyebrow ? <p className="page-eyebrow">{eyebrow}</p> : null}
        <h1 className="page-title">{title}</h1>
        {lede ? <p className="page-lede">{lede}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

export const projectEyebrow = (p: Project) => `${modalityLabel[p.modality]} · ${p.task}`;

const sentimentChip: Record<Sentiment, string> = { Positive: 'is-pass', Neutral: 'is-neutral', Negative: 'is-fail' };

export function SentimentChip({ s }: { s: Sentiment }) {
  return <span className={`chip ${sentimentChip[s]}`}>{s}</span>;
}

/** The main specimen for a project at a given stage of the workflow. */
export function ProjectSpecimen({ project, stage }: { project: Project; stage: Stage }) {
  switch (project.view) {
    case 'detection':
      return <DetectionFrame stage={stage} />;
    case 'pii':
      return <PiiFrame masked={stage === 'qc'} />;
    case 'ner':
      return (
        <div className="bench-doc">
          <EntityText stage={stage} spans={textSample} />
        </div>
      );
    case 'sentiment': {
      const t = tickets.find((x) => x.fix)!;
      return (
        <div className="bench-doc">
          <p className="mono muted" style={{ fontSize: 12, margin: '0 0 12px' }}>
            {t.id}
          </p>
          “{t.text}”
          <p style={{ margin: '18px 0 0', display: 'flex', gap: 8, alignItems: 'center', fontFamily: 'var(--sans)', fontSize: 13 }}>
            {stage === 'review' || stage === 'qc' ? (
              <>
                <s className="muted">AI: {t.ai}</s> <SentimentChip s={t.fix!} />
              </>
            ) : (
              <>
                AI: <SentimentChip s={t.ai} /> <span className="mono muted">{t.conf.toFixed(2)}</span>
              </>
            )}
          </p>
        </div>
      );
    }
    case 'tracking':
      return (
        <>
          <TrackFrame />
          <Filmstrip frames={10} />
        </>
      );
  }
}

/* ---------- Per-task sample items (labels, regions, entities, tickets, tracks) ---------- */

export type Item = {
  id: string;
  label: string;
  fix?: string;
  conf: number;
  /** Visual for grids and comparisons. */
  crop?: { box: Box; src: string; masked?: boolean };
  spans?: Span[];
  text?: string;
};

export function itemsFor(project: Project): Item[] {
  switch (project.view) {
    case 'detection':
      return streetBoxes.map((b) => ({ id: b.id, label: b.label, fix: b.fix, conf: b.conf, crop: { box: b, src: images.street } }));
    case 'pii':
      return piiRegions.map((r) => ({ id: r.id, label: r.label, conf: r.conf, crop: { box: r, src: images.buses } }));
    case 'ner':
      return textSample
        .filter((s) => s.type)
        .map((s, i) => ({ id: `e${i}`, label: `${s.text} · ${s.type}`, fix: s.fix ? `${s.text} · ${s.fix}` : undefined, conf: s.conf ?? 1, spans: [s] }));
    case 'sentiment':
      return tickets.map((t) => ({ id: t.id, label: t.ai, fix: t.fix, conf: t.conf, text: t.text }));
    case 'tracking':
      return tracks.map((t) => {
        const box = streetBoxes.find((b) => b.id === t.boxId)!;
        return { id: `#${t.id}`, label: box.label, fix: box.fix ? t.label : undefined, conf: box.conf, crop: { box, src: images.street } };
      });
  }
}

export { textSamples };

export function ItemVisual({ item, masked }: { item: Item; masked?: boolean }) {
  if (item.crop) return <ObjectCrop box={item.crop.box} src={item.crop.src} pad={item.crop.box.w < 5 ? 2.5 : 1.5} masked={masked} />;
  if (item.text) return <div className="asset-text">“{item.text}”</div>;
  if (item.spans) return <div className="asset-text">{item.spans[0].text}</div>;
  return null;
}
