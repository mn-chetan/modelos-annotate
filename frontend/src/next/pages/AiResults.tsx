import { useState } from 'react';
import { Search, Send } from 'lucide-react';
import type { Project } from '../../showcase/content';
import { EntityText } from '../../showcase/specimens';
import { PageHead, ItemVisual, SentimentChip, fmt, itemsFor, projectEyebrow, textSamples } from './shared';

const THRESHOLD = 0.7;
type Filter = 'all' | 'low' | 'high';

export function AiResultsPage({ project: p }: { project: Project }) {
  const [filter, setFilter] = useState<Filter>('all');
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const keep = (conf: number) => filter === 'all' || (filter === 'low' ? conf < THRESHOLD : conf >= THRESHOLD);

  const cards =
    p.view === 'ner'
      ? textSamples
          .map((d) => ({ d, conf: Math.min(...d.spans.filter((s) => s.conf).map((s) => s.conf!)) }))
          .filter(({ conf }) => keep(conf))
          .map(({ d, conf }) => (
            <button key={d.id} className={`card asset${selected.has(d.id) ? ' is-selected' : ''}`} onClick={() => toggle(d.id)} aria-pressed={selected.has(d.id)}>
              <div className="asset-text">
                <EntityText stage="ai" spans={d.spans} />
              </div>
              <div className="asset-body">
                <div className="asset-row">
                  <b className="mono">{d.id}</b>
                  <span className={`chip ${conf < THRESHOLD ? 'is-review' : 'is-ai'}`}>{conf < THRESHOLD ? 'Low confidence' : 'AI draft'}</span>
                </div>
              </div>
            </button>
          ))
      : itemsFor(p)
          .filter((it) => keep(it.conf))
          .map((it) => (
            <button
              key={it.id}
              className={`card asset${selected.has(it.id) ? ' is-selected' : ''}${it.conf < THRESHOLD ? ' is-low' : ''}`}
              onClick={() => toggle(it.id)}
              aria-pressed={selected.has(it.id)}
            >
              {it.text ? (
                <div className="asset-text">“{it.text}”</div>
              ) : (
                <div className="asset-media">
                  <ItemVisual item={it} />
                </div>
              )}
              <div className="asset-body">
                <div className="asset-row">
                  {p.view === 'sentiment' ? <SentimentChip s={it.label as 'Positive'} /> : <b>{p.view === 'tracking' ? `${it.id} ${it.label}` : it.label}</b>}
                  <span className="mono muted">{it.conf.toFixed(2)}</span>
                </div>
                <div className="asset-row">
                  <span className="muted">{p.view === 'tracking' ? '84 frames' : p.view === 'sentiment' ? it.id : 'street_0412.jpg'}</span>
                  <span className={`chip ${it.conf < THRESHOLD ? 'is-review' : 'is-ai'}`}>{it.conf < THRESHOLD ? 'Low confidence' : 'AI draft'}</span>
                </div>
              </div>
            </button>
          ));

  return (
    <div className="page">
      <PageHead
        eyebrow={projectEyebrow(p)}
        title="AI results"
        lede={`${fmt(p.aiDone)} ${p.unit} drafted by AI. Anything below ${THRESHOLD.toFixed(2)} confidence is sent to review first.`}
      />
      <div className="toolbar">
        <div className="seg" role="group" aria-label="Filter by confidence">
          <button aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>
            All
          </button>
          <button aria-pressed={filter === 'low'} onClick={() => setFilter('low')}>
            Below {THRESHOLD.toFixed(2)}
          </button>
          <button aria-pressed={filter === 'high'} onClick={() => setFilter('high')}>
            Confident
          </button>
        </div>
        <span className="search" role="search">
          <Search size={15} aria-hidden /> Search labels
        </span>
        <span className="spacer" />
        <button className="btn btn-primary btn-sm" disabled={!selected.size} style={{ opacity: selected.size ? 1 : 0.45 }}>
          <Send size={15} aria-hidden /> Send {selected.size || ''} to review
        </button>
      </div>
      <div className="grid-assets">{cards}</div>
    </div>
  );
}
