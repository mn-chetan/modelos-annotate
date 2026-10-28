/*
 * Text documents: reading a document's text and the AI's labels on it, running the AI on one
 * document, and drawing entities inline. Entities are spans of the text ([start, end) offsets);
 * sentiment and classification are one label for the whole document.
 */
import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import { request, type Annotation, type LiveAsset, type LiveProject } from '../../store';
import { OTHER_COLOUR, aiConfidence } from '../annotation-ui';

export type Doc = { text: string; annotations: Annotation[] };

/* ---------- Reading and running ---------- */

const docs = new Map<string, Promise<Doc>>();

/** A document's text, fetched once per page visit; `fresh` drops the cached copy. */
export function loadDocument(projectId: string, assetId: string, fresh = false): Promise<Doc> {
  const key = `${projectId}/${assetId}`;
  if (fresh || !docs.has(key)) {
    const p = request<{ text?: string; annotations?: Annotation[] }>(
      `/projects/${encodeURIComponent(projectId)}/text-annotation/assets/${encodeURIComponent(assetId)}`,
    ).then((r) => ({ text: r.text ?? '', annotations: r.annotations ?? [] }));
    p.catch(() => docs.delete(key));
    docs.set(key, p);
  }
  return docs.get(key)!;
}

export function useDocument(projectId: string, assetId: string, version = '') {
  const [doc, setDoc] = useState<Doc | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    setError('');
    loadDocument(projectId, assetId, !!version)
      .then((d) => alive && setDoc(d))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [projectId, assetId, version]);
  return { doc, error };
}

/** Ask the AI to label one document. The result is saved with the document. */
export async function analyseDocument(p: LiveProject, a: LiveAsset) {
  const form = new FormData();
  form.set('project_id', p.id);
  form.set('asset_id', a.id);
  form.set('analysis_type', p.raw.task_type || 'ENTITY_EXTRACTION');
  form.set('assessment_name', p.name);
  if (p.classes.length) form.set('identification_name', p.classes.join(', '));
  await request(`/text-annotation/analyze`, { method: 'POST', body: form });
  docs.delete(`${p.id}/${a.id}`);
}

/* ---------- Reading labels ---------- */

export type Span = { id: string; start: number; end: number; text: string; label: string; annotation: Annotation };

/** Entity spans with usable offsets, in reading order. */
export function spansOf(rows: Annotation[]): Span[] {
  return rows
    .filter((a) => (a.geometry_type ?? 'text_span') === 'text_span')
    .map((a) => {
      const g = a.geometry ?? a.text_span ?? {};
      return { id: a.id, start: g.start ?? -1, end: g.end ?? -1, text: g.text ?? '', label: a.label, annotation: a };
    })
    .filter((s) => s.start >= 0 && s.end > s.start)
    .sort((x, y) => x.start - y.start || y.end - x.end);
}

/** The document-level label (sentiment or category), the most confident one when there are several. */
export function docLabel(rows: Annotation[]): Annotation | undefined {
  const docRows = rows.filter((a) => a.geometry_type === 'text_classification' && a.review_status !== 'rejected');
  return docRows.sort((x, y) => (aiConfidence(y) ?? 0) - (aiConfidence(x) ?? 0))[0];
}

/* ---------- Drawing entities inline ---------- */

/**
 * Text with entities marked. The text is cut at every entity boundary and each piece is marked
 * with the most specific entity covering it, so overlapping entities are all shown (a ring marks
 * the overlap) and nothing is dropped. The class tag is drawn by CSS from data-label on an
 * entity's last piece, so the rendered text is exactly the document's text and selection
 * offsets can be read straight off it.
 */
export function EntityRun({
  text,
  spans,
  colours,
  focus,
  line,
  limit,
  onPick,
}: {
  text: string;
  spans: Span[];
  colours: Record<string, string>;
  focus?: string;
  line?: number;
  limit?: number;
  onPick?: (id: string) => void;
}) {
  const end = limit ? Math.min(text.length, limit) : text.length;
  const inView = spans.filter((s) => s.start < end && s.end <= text.length);
  const cuts = [...new Set([0, end, ...inView.flatMap((s) => [s.start, Math.min(s.end, end)])])].filter((c) => c <= end).sort((a, b) => a - b);
  const out: ReactNode[] = [];
  for (let i = 0; i < cuts.length - 1; i++) {
    const from = cuts[i];
    const to = cuts[i + 1];
    const piece = text.slice(from, to);
    const covering = inView.filter((s) => s.start <= from && s.end >= to);
    if (!covering.length) {
      out.push(piece);
      continue;
    }
    const s = covering.reduce((best, x) => (x.end - x.start < best.end - best.start ? x : best));
    const c = aiConfidence(s.annotation);
    const cls = [
      'ent',
      covering.length > 1 ? 'is-overlap' : '',
      s.annotation.review_status === 'rejected' ? 'is-rejected' : '',
      c != null && line != null && c < line && (!s.annotation.review_status || s.annotation.review_status === 'pending') ? 'is-low' : '',
      focus === s.id ? 'is-focus' : '',
      onPick ? 'is-pickable' : '',
      from > s.start ? 'is-cont' : '',
    ]
      .filter(Boolean)
      .join(' ');
    out.push(
      <mark
        key={`${s.id}:${from}`}
        className={cls}
        data-span={s.id}
        data-label={to === Math.min(s.end, end) ? s.label : undefined}
        style={{ '--ent': colours[s.label] ?? OTHER_COLOUR } as CSSProperties}
        onClick={onPick ? () => onPick(s.id) : undefined}
      >
        {piece}
      </mark>,
    );
  }
  if (end < text.length) out.push(<span key="more" aria-hidden>…</span>);
  return <>{out}</>;
}

/** A document on the contact sheet or in the inspector: its opening, or all of it, with entities. */
export function TextSnippet({
  project: p,
  asset: a,
  labels,
  colours,
  full = false,
  focus,
}: {
  project: LiveProject;
  asset: LiveAsset;
  labels: Annotation[];
  colours: Record<string, string>;
  full?: boolean;
  focus?: string;
}) {
  const { doc, error } = useDocument(p.id, a.id, a.updated_at ?? '');
  if (error) return <span className="doc-snippet is-missing">Text unavailable</span>;
  if (!doc) return <span className="doc-snippet is-loading">Reading…</span>;
  if (!doc.text) return <span className="doc-snippet is-missing">No text extracted yet</span>;
  return (
    <span className={`doc-snippet${full ? ' is-full' : ''}`}>
      <EntityRun text={doc.text} spans={spansOf(labels)} colours={colours} focus={focus} line={p.line} limit={full ? undefined : 320} />
    </span>
  );
}
