/*
 * "What annotators will see": the project's classes drawn on sample work in their own
 * colours. Sample objects that no class covers stay visible, hatched, so a missing class
 * is noticed before the project exists. Sample content is illustrative.
 */
import { useEffect, useState } from 'react';
import { images, piiRegions, streetBoxes, textSamples, tickets, tracks, type Box, type EntityType } from '../../src/showcase/content';
import { extOf, inkOn, type LabelClass, type StagedFile } from './model';
import { ClassChip } from './parts';
import type { Draft } from './useDraft';

const aliases: Record<string, string[]> = {
  plate: ['number plate', 'plate', 'licence plate', 'license plate'],
  PERSON: ['person', 'people', 'name'],
  ORG: ['organisation', 'organization', 'org', 'company'],
  LOC: ['location', 'place', 'city', 'loc'],
  DATE: ['date', 'time', 'date/time'],
};

function classFor(label: string, classes: LabelClass[]): LabelClass | undefined {
  const names = (aliases[label] ?? [label]).map((n) => n.toLowerCase());
  return classes.find((c) => names.includes(c.name.trim().toLowerCase()));
}

function Boxes({ boxes, classes, hover, ids }: { boxes: Box[]; classes: LabelClass[]; hover: string | null; ids?: Record<string, number> }) {
  return (
    <div className="pv-layer" aria-hidden>
      {boxes.map((b) => {
        const label = b.fix ?? b.label;
        const c = classFor(label, classes);
        const dim = hover && c?.id !== hover;
        return (
          <div
            key={b.id}
            className={`pv-box${c ? '' : ' is-none'}${dim ? ' is-dim' : ''}${b.x + b.w > 86 ? ' is-right' : ''}`}
            style={{
              left: `${b.x}%`,
              top: `${b.y}%`,
              width: `${b.w}%`,
              height: `${b.h}%`,
              ['--c' as string]: c?.colour ?? '#FFFFFF',
              ['--ci' as string]: c ? inkOn(c.colour) : '#15181E',
            }}
          >
            <span className="pv-tag">
              {c ? c.name : label}
              {ids?.[b.id] !== undefined ? <em>#{ids[b.id]}</em> : null}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function Uncovered({ labels }: { labels: string[] }) {
  if (!labels.length) return <p className="pv-note">Every object in this sample has a class.</p>;
  return (
    <p className="pv-note">
      <span className="pv-hatch" aria-hidden />
      <span>
        No class yet for <b>{labels.join(', ')}</b> in this sample. Add one if your data has them.
      </span>
    </p>
  );
}

const uncovered = (labels: string[], classes: LabelClass[]) =>
  [...new Set(labels)].filter((l) => !classFor(l, classes)).map((l) => (l === 'plate' ? 'number plates' : l));

const ticketCategory: Record<string, string> = {
  'TCK-40121': 'Delivery',
  'TCK-40122': 'Billing',
  'TCK-40125': 'Product',
  'TCK-40127': 'Product',
  'TCK-40130': 'Delivery',
};

function SampleWork({ draft, hover }: { draft: Draft; hover: string | null }) {
  const { task, classes } = draft;

  if (task === 'Object detection' || task === 'Detection' || task === 'Object tracking') {
    const ids = task === 'Object tracking' ? Object.fromEntries(tracks.map((t) => [t.boxId, t.id])) : undefined;
    return (
      <>
        <div className="pv-frame">
          <img src={images.street} alt="Sample street frame with buses, a truck, cars, a motorcyclist and a cyclist" />
          <Boxes boxes={streetBoxes} classes={classes} hover={hover} ids={ids} />
        </div>
        <Uncovered labels={uncovered(streetBoxes.map((b) => b.fix ?? b.label), classes)} />
      </>
    );
  }

  if (task === 'PII masking') {
    return (
      <>
        <div className="pv-frame">
          <div className="pv-zoom">
            <img src={images.buses} alt="Sample street frame with buses, number plates and pedestrians" />
            <Boxes boxes={piiRegions} classes={classes} hover={hover} />
          </div>
        </div>
        <Uncovered labels={uncovered(piiRegions.map((b) => b.label), classes)} />
      </>
    );
  }

  if (task === 'Named entities') {
    const all: string[] = [];
    return (
      <>
        <div className="pv-doc">
          {textSamples.slice(0, 3).map((s) => (
            <p key={s.id}>
              <span className="pv-doc-id mono">{s.id}</span>
              {s.spans.map((sp, i) => {
                const t = (sp.fix ?? sp.type) as EntityType | undefined;
                if (!t) return <span key={i}>{sp.text}</span>;
                all.push(t);
                const c = classFor(t, classes);
                const dim = hover && c?.id !== hover;
                return (
                  <mark key={i} className={`pv-ent${c ? '' : ' is-none'}${dim ? ' is-dim' : ''}`} style={{ ['--c' as string]: c?.colour ?? '#8C909A' }}>
                    {sp.text}
                    <small>{c ? c.name : t.toLowerCase()}</small>
                  </mark>
                );
              })}
            </p>
          ))}
        </div>
        <Uncovered labels={uncovered(all, classes).map((l) => l.toLowerCase())} />
      </>
    );
  }

  if (task === 'Relation extraction') {
    const rels: [string, string, string][] = [
      ['Anika Rao', 'works_at', 'Halden Freight'],
      ['Halden Freight', 'located_in', 'Pune'],
      ['Meera Shah', 'works_at', 'Chennai team'],
    ];
    return (
      <div className="pv-doc">
        {rels.map(([a, r, b]) => {
          const c = classFor(r, classes);
          const dim = hover && c?.id !== hover;
          return (
            <p key={a + r} className={`pv-rel${dim ? ' is-dim' : ''}`}>
              <b>{a}</b>
              {c ? <ClassChip c={c} /> : <span className="pv-rel-none">{r}: no class</span>}
              <b>{b}</b>
            </p>
          );
        })}
      </div>
    );
  }

  // Sentiment and classification: one label per item.
  return (
    <ul className="pv-items">
      {tickets.map((t) => {
        const want = task === 'Sentiment' ? (t.fix ?? t.ai) : ticketCategory[t.id];
        const c = classFor(want, classes);
        const dim = hover && c?.id !== hover;
        return (
          <li key={t.id} className={dim ? 'is-dim' : ''}>
            <span className="mono">{t.id}</span>
            <p>{t.text}</p>
            {c ? <ClassChip c={c} /> : <span className="pv-rel-none">{want}: no class</span>}
          </li>
        );
      })}
    </ul>
  );
}

function useTextHead(f: StagedFile | undefined) {
  const [text, setText] = useState('');
  useEffect(() => {
    if (!f) return setText('');
    let live = true;
    f.file
      .slice(0, 1400)
      .text()
      .then((t) => live && setText(t));
    return () => {
      live = false;
    };
  }, [f]);
  return text;
}

function YourWork({ draft }: { draft: Draft }) {
  const imgs = draft.files.filter((f) => f.thumb);
  const txt = draft.files.find((f) => ['.txt', '.csv', '.tsv', '.json'].includes(extOf(f.file.name)));
  const head = useTextHead(draft.modality === 'text' ? txt : undefined);
  const [i, setI] = useState(0);
  const f = imgs[Math.min(i, imgs.length - 1)];

  if (draft.modality === 'image' && f) {
    return (
      <>
        <div className="pv-frame is-yours">
          <img src={f.thumb} alt={`Your file ${f.file.name}`} />
        </div>
        <div className="pv-yours-bar">
          <span className="mono">{f.file.name}</span>
          {imgs.length > 1 ? (
            <span>
              <button type="button" className="np-link" onClick={() => setI((i - 1 + imgs.length) % imgs.length)}>
                Previous
              </button>{' '}
              <span className="muted mono">
                {Math.min(i, imgs.length - 1) + 1}/{imgs.length}
              </span>{' '}
              <button type="button" className="np-link" onClick={() => setI((i + 1) % imgs.length)}>
                Next
              </button>
            </span>
          ) : null}
        </div>
        <p className="pv-note">AI draws its first boxes after the project is created. Here you can check the files are the ones you meant.</p>
      </>
    );
  }
  if (draft.modality === 'text' && txt) {
    return (
      <>
        <pre className="pv-text">{head || ' '}</pre>
        <p className="pv-note">
          Opening of <span className="mono">{txt.file.name}</span>. AI marks it up after the project is created.
        </p>
      </>
    );
  }
  return <p className="pv-note">Nothing of yours to show yet: add {draft.modality === 'text' ? 'a .txt or .csv file' : 'images'} to see them here.</p>;
}

export function Preview({ draft, hover, compact = false }: { draft: Draft; hover: string | null; compact?: boolean }) {
  const canShowYours =
    (draft.modality === 'image' && draft.files.some((f) => f.thumb)) ||
    (draft.modality === 'text' && draft.files.some((f) => ['.txt', '.csv', '.tsv', '.json'].includes(extOf(f.file.name))));
  const [mode, setMode] = useState<'sample' | 'yours'>('sample');
  const showing = mode === 'yours' && canShowYours ? 'yours' : 'sample';

  return (
    <div className={`pv${compact ? ' is-compact' : ''}`}>
      <div className="pv-head">
        <div className="pv-legend" aria-label="Classes as annotators will see them">
          {draft.classes.length ? draft.classes.map((c, k) => <ClassChip key={c.id} c={c} k={k} />) : <span className="muted">No classes yet</span>}
        </div>
        <div className="seg pv-seg" role="group" aria-label="Preview">
          <button type="button" aria-pressed={showing === 'sample'} onClick={() => setMode('sample')}>
            Sample
          </button>
          <button type="button" aria-pressed={showing === 'yours'} disabled={!canShowYours} onClick={() => setMode('yours')}>
            Your files
          </button>
        </div>
      </div>
      {showing === 'sample' ? <SampleWork draft={draft} hover={hover} /> : <YourWork draft={draft} />}
    </div>
  );
}
