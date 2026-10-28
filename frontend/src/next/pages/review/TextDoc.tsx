/*
 * The document half of the review bench. Entities are read in place: click one to correct
 * it, or select any run of text and pick a class (or press its number) to add one the AI
 * missed. Sentiment and classification put one decision on the whole document.
 */
import { useEffect, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import type { Annotation, LiveAsset, LiveProject } from '../../store';
import { OTHER_COLOUR, aiConfidence, colourStyle } from '../annotation-ui';
import { EntityRun, spansOf, useDocument } from '../text/text-model';
import type { Edits } from './useEdits';

type Pending = { start: number; end: number; text: string; x: number; y: number };

/** Character offset of a DOM position within the container's text. */
function offsetIn(container: HTMLElement, node: Node, offset: number) {
  const r = document.createRange();
  r.setStart(container, 0);
  r.setEnd(node, offset);
  return r.toString().length;
}

export function TextDoc({
  project: p,
  asset,
  edits,
  colours,
  selected,
  onSelect,
}: {
  project: LiveProject;
  asset: LiveAsset;
  edits: Edits;
  colours: Record<string, string>;
  selected: string;
  onSelect: (id: string) => void;
}) {
  const { doc, error } = useDocument(p.id, asset.id);
  const page = useRef<HTMLDivElement>(null);
  const reading = useRef<HTMLParagraphElement>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const text = doc?.text ?? '';

  // Scroll the selected entity into view when it's picked from the list.
  useEffect(() => {
    if (!selected) return;
    reading.current?.querySelector(`[data-span="${CSS.escape(selected)}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [selected]);

  function onMouseUp() {
    const sel = document.getSelection();
    const el = reading.current;
    if (!sel || sel.isCollapsed || !el || !el.contains(sel.anchorNode) || !el.contains(sel.focusNode)) {
      setPending(null);
      return;
    }
    const range = sel.getRangeAt(0);
    let start = offsetIn(el, range.startContainer, range.startOffset);
    let end = offsetIn(el, range.endContainer, range.endOffset);
    // Trim surrounding whitespace so the span is the words that were meant.
    while (start < end && /\s/.test(text[start])) start++;
    while (end > start && /\s/.test(text[end - 1])) end--;
    if (end <= start) return setPending(null);
    const box = range.getBoundingClientRect();
    const host = page.current!.getBoundingClientRect();
    setPending({ start, end, text: text.slice(start, end), x: box.left - host.left + box.width / 2, y: box.bottom - host.top + 6 });
  }

  function add(label: string) {
    if (!pending) return;
    const span: Annotation = {
      id: crypto.randomUUID(),
      asset_id: asset.id,
      label,
      geometry_type: 'text_span',
      geometry: { start: pending.start, end: pending.end, text: pending.text },
      x: 0,
      y: 0,
      w: 0,
      h: 0,
      source: 'human',
      review_status: 'approved',
      provenance: {},
    };
    edits.change([...edits.rows, span]);
    onSelect(span.id);
    setPending(null);
    document.getSelection()?.removeAllRanges();
  }

  // A number key adds the selection as that class.
  useEffect(() => {
    if (!pending) return;
    const onKey = (e: KeyboardEvent) => {
      if (/^[1-9]$/.test(e.key) && p.classes[+e.key - 1]) {
        e.preventDefault();
        e.stopImmediatePropagation();
        add(p.classes[+e.key - 1]);
      } else if (e.key === 'Escape') setPending(null);
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  });

  if (error) return <p className="error-note">The document’s text couldn’t be loaded. {error}</p>;
  if (!doc) {
    return (
      <p className="page-status" role="status">
        <Loader2 size={16} className="spin" aria-hidden /> Reading the document…
      </p>
    );
  }

  return (
    <div className="rv-doc" ref={page}>
      {p.kind === 'document' ? <DocDecision project={p} asset={asset} edits={edits} colours={colours} /> : null}
      <div className="rv-sheet">
        {text ? (
          <p className="rv-reading" ref={reading} onMouseUp={p.kind === 'spans' ? onMouseUp : undefined}>
            <EntityRun text={text} spans={spansOf(edits.rows)} colours={colours} focus={selected} line={p.line} onPick={p.kind === 'spans' ? onSelect : undefined} />
          </p>
        ) : (
          <p className="muted">No text could be extracted from this file.</p>
        )}
      </div>
      {p.kind === 'spans' ? <p className="rv-doc-hint">Select any words to add an entity the AI missed; click an entity to correct it.</p> : null}
      {pending ? (
        <div className="rv-picker" role="dialog" aria-label="Add entity" style={{ left: pending.x, top: pending.y }}>
          <p>
            Add “{pending.text.length > 40 ? `${pending.text.slice(0, 40)}…` : pending.text}” as
          </p>
          <ul>
            {p.classes.map((c, i) => (
              <li key={c}>
                <button style={colourStyle(colours[c] ?? OTHER_COLOUR)} onMouseDown={(e) => e.preventDefault()} onClick={() => add(c)}>
                  <i aria-hidden />
                  {i < 9 ? <kbd>{i + 1}</kbd> : null}
                  {c}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/** Set the document's one label: correct the AI's when there is one, else add a person's. */
export function setDocLabel(edits: Edits, asset: LiveAsset, label: string) {
  const rows = edits.rows.filter((a) => a.geometry_type === 'text_classification');
  const current = rows.find((a) => a.review_status !== 'rejected') ?? rows[0];
  if (current) {
    const original = typeof current.provenance?.original_ai_label === 'string' ? (current.provenance.original_ai_label as string) : (edits.savedLabels.get(current.id) ?? current.label);
    edits.update(current.id, { label, review_status: label === original && current.source === 'ai' ? 'approved' : 'edited' });
    return;
  }
  const row: Annotation = {
    id: crypto.randomUUID(),
    asset_id: asset.id,
    label,
    geometry_type: 'text_classification',
    geometry: {},
    x: 0,
    y: 0,
    w: 0,
    h: 0,
    source: 'human',
    review_status: 'approved',
    provenance: {},
  };
  edits.change([...edits.rows, row]);
}

/** One label for the whole document: the AI's call, and the classes to change it to. */
function DocDecision({ project: p, asset, edits, colours }: { project: LiveProject; asset: LiveAsset; edits: Edits; colours: Record<string, string> }) {
  const rows = edits.rows.filter((a) => a.geometry_type === 'text_classification');
  const current = rows.find((a) => a.review_status !== 'rejected') ?? rows[0];
  // What the AI said: recorded once saved, and the last saved label until then.
  const original = !current ? null : typeof current.provenance?.original_ai_label === 'string' ? (current.provenance.original_ai_label as string) : current.source === 'ai' ? (edits.savedLabels.get(current.id) ?? null) : null;
  const c = current ? aiConfidence(current) : null;
  const choose = (label: string) => setDocLabel(edits, asset, label);
  const choices = p.classes.length ? p.classes : [...new Set(rows.map((r) => r.label))];
  return (
    <div className="rv-decision">
      <p className="rv-decision-ai">
        <span>{p.task}</span>
        {current ? (
          <>
            AI: {original && original !== current.label ? <s>{original}</s> : null} <b>{current.label}</b>
            {c != null ? <span className={`mono${c < p.line ? ' is-low' : ''}`}>{c.toFixed(2)}</span> : null}
          </>
        ) : (
          <>The AI gave no label. Choose one.</>
        )}
      </p>
      <div className="rv-decision-choices" role="group" aria-label="Label for this document">
        {choices.map((name, i) => (
          <button key={name} style={colourStyle(colours[name] ?? OTHER_COLOUR)} aria-pressed={current?.label === name && current.review_status !== 'rejected'} onClick={() => choose(name)}>
            <i aria-hidden />
            {i < 9 ? <kbd>{i + 1}</kbd> : null}
            {name}
          </button>
        ))}
      </div>
    </div>
  );
}
