import {
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCheck,
  ChevronDown,
  Download,
  Maximize,
  Loader2,
  MousePointer2,
  Redo2,
  Search,
  SquareDashed,
  Trash2,
  Undo2,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { BoxOverlay } from './BoxOverlay';
import {
  classColours,
  colourStyle,
  DecisionBadge,
  modelName,
} from './annotation-ui';
import { api } from '../../services/api';
import {
  getAnnotations,
  exportLabels,
  isApproved,
  refreshAssets,
  refreshProjects,
  request,
  useAssets,
  type Annotation,
  type LiveProject,
} from '../store';
import { PageHead, projectEyebrow } from './shared';
import { setNavigationGuard } from '../router';
import './review.css';

type Point = { x: number; y: number };
type Gesture = { start: Point; original: Annotation; kind: string };
const clamp = (v: number, min = 0, max = 100) =>
  Math.max(min, Math.min(max, v));
const snapshot = (rows: Annotation[]) =>
  rows.map((a) => ({ ...a, provenance: { ...a.provenance } }));
export function ReviewPage({ project: p }: { project: LiveProject }) {
  const assets = useAssets(p.id);
  const [assetId, setAssetId] = useState('');
  const asset = assets?.find((a) => a.id === assetId) || assets?.[0];
  const [rows, setRows] = useState<Annotation[]>([]);
  const [saved, setSaved] = useState('[]');
  const [selected, setSelected] = useState('');
  const [hovered, setHovered] = useState('');
  const [names, setNames] = useState(false);
  const [query, setQuery] = useState('');
  const [objectFilter, setObjectFilter] = useState('all');
  const [tool, setTool] = useState<'select' | 'draw'>('select');
  const [label, setLabel] = useState(p.classes[0] || '');
  const [zoom, setZoom] = useState(1);
  const [activity, setActivity] = useState<
    'save' | 'approve' | 'reject' | null
  >(null);
  const busy = activity !== null;
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [imageReady, setImageReady] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [past, setPast] = useState<Annotation[][]>([]),
    [future, setFuture] = useState<Annotation[][]>([]);
  const gesture = useRef<Gesture | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const dirty = JSON.stringify(rows) !== saved;
  const index = assets?.findIndex((a) => a.id === asset?.id) ?? 0;
  const selectedRow = rows.find((a) => a.id === selected);
  const colours = classColours(p.classes, p.raw.label_ontology);
  const remaining = rows.filter(
    (a) => !['approved', 'edited', 'rejected'].includes(a.review_status || ''),
  ).length;
  const visibleRows = rows.filter(
    (a) =>
      a.label.toLowerCase().includes(query.toLowerCase()) &&
      (objectFilter === 'all' ||
        (objectFilter === 'pending' &&
          !['approved', 'edited', 'rejected'].includes(
            a.review_status || '',
          )) ||
        (objectFilter === 'low' &&
          a.confidence != null &&
          a.confidence < (p.raw.confidence_threshold ?? 0.7))),
  );
  const objectList = useRef<HTMLUListElement>(null);
  useEffect(() => {
    objectList.current
      ?.querySelector(`[data-object-id="${selected}"]`)
      ?.scrollIntoView?.({ block: 'nearest' });
  }, [selected]);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setLoaded(false);
    setError('');
    setNote('');
    setRows([]);
    setSaved('[]');
    setPast([]);
    setFuture([]);
    setSelected('');
    setHovered('');
    if (!asset) {
      setLoading(false);
      return;
    }
    getAnnotations(asset.id)
      .then((a) => {
        if (alive) {
          setRows(a);
          setSaved(JSON.stringify(a));
          setLoading(false);
          setLoaded(true);
        }
      })
      .catch((e) => {
        if (alive) {
          setError(String(e));
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [asset?.id, loadAttempt]);
  useEffect(() => {
    setImageReady(false);
  }, [asset?.id]);
  useEffect(() => {
    const confirm = () =>
      !dirty || window.confirm('Discard unsaved box edits?');
    setNavigationGuard(confirm);
    const before = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', before);
    return () => {
      setNavigationGuard(null);
      window.removeEventListener('beforeunload', before);
    };
  }, [dirty]);
  function change(next: Annotation[]) {
    setPast((h) => [...h, snapshot(rows)]);
    setFuture([]);
    setRows(next);
    setNote('');
  }
  function update(id: string, patch: Partial<Annotation>) {
    change(rows.map((a) => (a.id === id ? { ...a, ...patch } : a)));
  }
  function undo() {
    if (!past.length || busy) return;
    setFuture((h) => [snapshot(rows), ...h]);
    setRows(past[past.length - 1]);
    setPast((h) => h.slice(0, -1));
  }
  function redo() {
    if (!future.length || busy) return;
    setPast((h) => [...h, snapshot(rows)]);
    setRows(future[0]);
    setFuture((h) => h.slice(1));
  }
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (
        (e.target as HTMLElement).matches('input,select,textarea') ||
        busy ||
        loading
      )
        return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        e.shiftKey ? redo() : undo();
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
        e.preventDefault();
        redo();
      }
      if ((e.key === 'Delete' || e.key === 'Backspace') && selected) {
        e.preventDefault();
        change(rows.filter((a) => a.id !== selected));
        setSelected('');
      }
      if (/^[1-9]$/.test(e.key) && p.classes[+e.key - 1]) {
        setLabel(p.classes[+e.key - 1]);
        if (selected)
          update(selected, {
            label: p.classes[+e.key - 1],
            review_status: 'edited',
          });
      }
      if (e.key === 'Escape') {
        setSelected('');
        setTool('select');
      }
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  });
  function point(e: ReactPointerEvent): Point {
    const r = svg.current!.getBoundingClientRect();
    return {
      x: clamp(((e.clientX - r.left) / r.width) * 100),
      y: clamp(((e.clientY - r.top) / r.height) * 100),
    };
  }
  function down(e: ReactPointerEvent<SVGSVGElement>) {
    if (busy || loading || !loaded || !imageReady || e.button !== 0) return;
    const pos = point(e),
      target = e.target as SVGElement;
    const id = target.closest('[data-id]')?.getAttribute('data-id');
    const row = rows.find((a) => a.id === id);
    if (tool === 'draw') {
      if (!label) return;
      const ann: Annotation = {
        id: crypto.randomUUID(),
        asset_id: asset!.id,
        label,
        x: pos.x,
        y: pos.y,
        w: 0.01,
        h: 0.01,
        source: 'human',
        geometry_type: 'box',
        review_status: 'approved',
        provenance: {},
      };
      change([...rows, ann]);
      setSelected(ann.id);
      gesture.current = { start: pos, original: ann, kind: 'draw' };
    } else if (row) {
      setSelected(row.id);
      setPast((h) => [...h, snapshot(rows)]);
      setFuture([]);
      gesture.current = {
        start: pos,
        original: { ...row },
        kind: target.getAttribute('data-handle') || 'move',
      };
    } else {
      setSelected('');
      return;
    }
    e.currentTarget.setPointerCapture(e.pointerId);
    e.preventDefault();
  }
  function move(e: ReactPointerEvent<SVGSVGElement>) {
    const g = gesture.current;
    if (!g) return;
    const pos = point(e),
      a = g.original,
      dx = pos.x - g.start.x,
      dy = pos.y - g.start.y;
    let box = { x: a.x, y: a.y, w: a.w, h: a.h };
    if (g.kind === 'move')
      box = {
        ...box,
        x: clamp(a.x + dx, 0, 100 - a.w),
        y: clamp(a.y + dy, 0, 100 - a.h),
      };
    else if (g.kind === 'draw')
      box = {
        x: Math.min(g.start.x, pos.x),
        y: Math.min(g.start.y, pos.y),
        w: Math.max(0.01, Math.abs(dx)),
        h: Math.max(0.01, Math.abs(dy)),
      };
    else {
      let left = a.x,
        top = a.y,
        right = a.x + a.w,
        bottom = a.y + a.h;
      if (g.kind.includes('w')) left = clamp(a.x + dx, 0, right - 0.1);
      if (g.kind.includes('e')) right = clamp(a.x + a.w + dx, left + 0.1, 100);
      if (g.kind.includes('n')) top = clamp(a.y + dy, 0, bottom - 0.1);
      if (g.kind.includes('s')) bottom = clamp(a.y + a.h + dy, top + 0.1, 100);
      box = { x: left, y: top, w: right - left, h: bottom - top };
    }
    setRows((current) =>
      current.map((r) =>
        r.id === a.id ? { ...r, ...box, review_status: 'edited' } : r,
      ),
    );
  }
  function up(e: ReactPointerEvent<SVGSVGElement>) {
    const g = gesture.current;
    if (!g) return;
    if (g.kind === 'draw')
      setRows((current) =>
        current.filter(
          (a) => a.id !== g.original.id || (a.w >= 0.15 && a.h >= 0.15),
        ),
      );
    gesture.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId))
      e.currentTarget.releasePointerCapture(e.pointerId);
  }
  async function save() {
    if (!asset || busy) return;
    setActivity('save');
    setError('');
    setNote('');
    const submitted = snapshot(rows);
    try {
      await request(`/assets/${asset.id}/annotations/batch`, {
        method: 'PUT',
        body: JSON.stringify({ annotations: submitted }),
      });
      const persisted = await getAnnotations(asset.id);
      setRows(persisted);
      setSaved(JSON.stringify(persisted));
      setPast([]);
      setFuture([]);
      await refreshAssets(p.id);
      await refreshProjects();
      setNote('Saved. Approve this image when review is complete.');
    } catch (e) {
      setError(`Save failed. Your edits are still here. ${String(e)}`);
    } finally {
      setActivity(null);
    }
  }
  async function decide(action: 'approve' | 'reject') {
    if (!asset || dirty || busy) return;
    setActivity(action);
    setError('');
    try {
      await request(`/assets/${asset.id}/review`, {
        method: 'POST',
        body: JSON.stringify({ action, reviewer_id: 'demo_reviewer' }),
      });
      await refreshAssets(p.id);
      await refreshProjects();
      setNote(
        action === 'approve'
          ? 'Image approved. Accepted labels are ready to export.'
          : 'Image rejected. It will not be exported.',
      );
    } catch (e) {
      setError(`Review was not confirmed. ${String(e)}`);
    } finally {
      setActivity(null);
    }
  }
  function selectAsset(id: string) {
    if (dirty && !window.confirm('Discard unsaved box edits?')) return;
    setAssetId(id);
    setZoom(1);
  }
  async function download(format: 'coco' | 'yolo') {
    try {
      await exportLabels(p.id, format);
    } catch (e) {
      setError(String(e));
    }
  }
  if (p.modality !== 'image' || p.task !== 'Object detection')
    return (
      <div className="page">
        <PageHead
          title="Review"
          lede="Review for this task is outside the image detection demo."
        />
      </div>
    );
  return (
    <div className="page review-page">
      <PageHead
        eyebrow={projectEyebrow(p)}
        title="Review"
        lede="A closer look. Correct the boxes, decide on every label, then approve the image."
        actions={
          <div className="export-actions">
            <span>Export approved</span>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => download('coco')}
            >
              <Download size={14} /> COCO JSON
            </button>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => download('yolo')}
            >
              YOLO
            </button>
          </div>
        }
      />
      {error && (
        <p className="error-note" role="alert">
          {error}{' '}
          {!loaded && (
            <button
              className="btn"
              onClick={() => setLoadAttempt((a) => a + 1)}
            >
              Retry labels
            </button>
          )}
        </p>
      )}
      {note && (
        <p className="success-note" role="status">
          <Check size={16} />
          {note}
        </p>
      )}
      {!assets ? (
        <section className="card empty" role="status">
          Loading your images…
        </section>
      ) : !assets.length ? (
        <section className="card empty">
          <SquareDashed size={30} />
          <h2>No images to review yet</h2>
          <p>Upload images in AI results to begin.</p>
        </section>
      ) : (
        <>
          <section className="review-workspace" aria-busy={busy}>
            <div className="review-asset-bar">
              <div className="image-navigator">
                <button
                  className="studio-icon"
                  aria-label="Previous image"
                  disabled={busy || index === 0}
                  onClick={() => selectAsset(assets[index - 1].id)}
                >
                  <ArrowLeft size={16} />
                </button>
                <span className="image-position">
                  {String(index + 1).padStart(2, '0')}{' '}
                  <span>/ {String(assets.length).padStart(2, '0')}</span>
                </span>
                <button
                  className="studio-icon"
                  aria-label="Next image"
                  disabled={busy || index === assets.length - 1}
                  onClick={() => selectAsset(assets[index + 1].id)}
                >
                  <ArrowRight size={16} />
                </button>
              </div>
              <label className="image-chooser">
                <select
                  aria-label="Review image"
                  disabled={busy}
                  value={asset?.id}
                  onChange={(e) => selectAsset(e.target.value)}
                >
                  {assets.map((a, i) => (
                    <option value={a.id} key={a.id}>
                      {i + 1}. {a.filename}
                    </option>
                  ))}
                </select>
                <ChevronDown size={14} />
              </label>
              <span className="image-dimensions">
                {asset?.width} × {asset?.height}
              </span>
              <DecisionBadge status={asset?.review_status} />
              <span className="spacer" />
              <span
                className={`save-state${dirty ? ' is-dirty' : ''}`}
                role="status"
              >
                {dirty ? (
                  <>
                    <i />
                    Unsaved edits
                  </>
                ) : (
                  <>
                    <Check size={13} />
                    Saved
                  </>
                )}
              </span>
              <button
                className="btn btn-primary btn-sm"
                disabled={busy || loading || !loaded || !dirty}
                onClick={save}
              >
                {activity === 'save' ? 'Saving…' : 'Save edits'}
              </button>
            </div>
            <div className="review-bench">
              <div className="canvas-column">
                <fieldset
                  className="review-tools"
                  disabled={busy || loading || !loaded}
                >
                  <div className="tool-group">
                    <button
                      className="tool-button"
                      title="Select and move boxes"
                      aria-label="Select / move"
                      aria-pressed={tool === 'select'}
                      onClick={() => setTool('select')}
                    >
                      <MousePointer2 size={16} />
                      <span>Select</span>
                    </button>
                    <button
                      className="tool-button"
                      aria-label="Draw box"
                      aria-pressed={tool === 'draw'}
                      onClick={() => setTool('draw')}
                    >
                      <SquareDashed size={16} />
                      <span>Draw box</span>
                    </button>
                  </div>
                  {tool === 'draw' && (
                    <select
                      className="draw-class"
                      aria-label="New box class"
                      value={label}
                      onChange={(e) => setLabel(e.target.value)}
                    >
                      {p.classes.map((c) => (
                        <option key={c}>{c}</option>
                      ))}
                    </select>
                  )}
                  <div className="tool-group history-tools">
                    <button
                      className="studio-icon"
                      title="Undo · Ctrl Z"
                      aria-label="Undo"
                      disabled={!past.length}
                      onClick={undo}
                    >
                      <Undo2 size={16} />
                    </button>
                    <button
                      className="studio-icon"
                      title="Redo · Ctrl Shift Z"
                      aria-label="Redo"
                      disabled={!future.length}
                      onClick={redo}
                    >
                      <Redo2 size={16} />
                    </button>
                  </div>
                  <span className="spacer" />
                  <label
                    className="names-toggle"
                    title="Space names to avoid overlap. Hover any box to inspect it."
                  >
                    <input
                      type="checkbox"
                      checked={names}
                      onChange={(e) => setNames(e.target.checked)}
                    />
                    <span>Names</span>
                  </label>
                  <div className="zoom-controls">
                    <button
                      className="studio-icon"
                      aria-label="Zoom out"
                      disabled={zoom <= 0.5}
                      onClick={() =>
                        setZoom((z) =>
                          Math.max(0.5, Math.round((z - 0.25) * 100) / 100),
                        )
                      }
                    >
                      <ZoomOut size={16} />
                    </button>
                    <label className="zoom-value">
                      <span>{Math.round(zoom * 100)}%</span>
                      <input
                        aria-label="Zoom"
                        type="range"
                        min="0.5"
                        max="3"
                        step="0.05"
                        value={zoom}
                        onChange={(e) => setZoom(+e.target.value)}
                      />
                    </label>
                    <button
                      className="studio-icon"
                      aria-label="Zoom in"
                      disabled={zoom >= 3}
                      onClick={() =>
                        setZoom((z) =>
                          Math.min(3, Math.round((z + 0.25) * 100) / 100),
                        )
                      }
                    >
                      <ZoomIn size={16} />
                    </button>
                    <button
                      className="studio-icon"
                      aria-label="Fit"
                      title="Fit image"
                      onClick={() => setZoom(1)}
                    >
                      <Maximize size={16} />
                    </button>
                  </div>
                </fieldset>
                <div className="review-scroll">
                  <div
                    className="review-image"
                    style={{ width: `${zoom * 100}%` }}
                  >
                    <img
                      src={asset ? api.getAssetImageUrl(asset.id) : ''}
                      alt={asset?.filename}
                      draggable={false}
                      onLoad={() => setImageReady(true)}
                      onError={() => {
                        setImageReady(false);
                        setError(
                          'Image could not be loaded. Reload the image before reviewing.',
                        );
                      }}
                    />
                    <BoxOverlay
                      annotations={rows}
                      colours={colours}
                      selected={selected}
                      hovered={hovered}
                      names={names}
                      editable
                      svgRef={svg}
                      aria-label="Editable image boxes"
                      style={{
                        cursor: tool === 'draw' ? 'crosshair' : 'default',
                      }}
                      onHover={setHovered}
                      onPointerDown={down}
                      onPointerMove={move}
                      onPointerUp={up}
                      onPointerCancel={up}
                    />
                  </div>
                </div>
                <div className="canvas-status">
                  <span>
                    <MousePointer2 size={13} />
                    {tool === 'draw'
                      ? 'Drag to draw a box.'
                      : names
                        ? 'Names are spaced. Select a box to edit.'
                        : 'Hover to inspect. Select a box to edit.'}
                  </span>
                  <span className="canvas-shortcuts">
                    1–9 class <i />⌫ delete <i />⌘ Z undo
                  </span>
                </div>
                <div className="class-legend" aria-label="Project classes">
                  {p.classes.map((c) => (
                    <span key={c} style={colourStyle(colours[c])}>
                      <i />
                      {c}
                      <b>
                        {
                          rows.filter(
                            (a) =>
                              a.label === c && a.review_status !== 'rejected',
                          ).length
                        }
                      </b>
                    </span>
                  ))}
                </div>
              </div>
              <aside className="review-side">
                <div className="objects-head">
                  <h2>
                    Objects <span>{rows.length}</span>
                  </h2>
                  <button
                    className="accept-all"
                    title="Accept all remaining labels"
                    aria-label="Accept remaining labels"
                    disabled={busy || loading || !loaded || !remaining}
                    onClick={() =>
                      change(
                        rows.map((a) =>
                          ['approved', 'edited', 'rejected'].includes(
                            a.review_status || '',
                          )
                            ? a
                            : { ...a, review_status: 'approved' },
                        ),
                      )
                    }
                  >
                    <CheckCheck size={15} />
                    <span>Accept all</span>
                  </button>
                </div>
                <div className="objects-progress">
                  <div>
                    <span>
                      {remaining
                        ? `${remaining} to review`
                        : 'All labels decided'}
                    </span>
                    <b>
                      {rows.length - remaining} / {rows.length}
                    </b>
                  </div>
                  <span className="objects-progress-track">
                    <i
                      style={{
                        width: `${rows.length ? ((rows.length - remaining) / rows.length) * 100 : 0}%`,
                      }}
                    />
                  </span>
                </div>
                <fieldset
                  className="object-controls"
                  disabled={busy || loading || !loaded}
                >
                  <label className="object-search">
                    <Search size={14} />
                    <input
                      aria-label="Find objects"
                      placeholder="Find a class…"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                    />
                  </label>
                  <div className="object-filters" aria-label="Filter objects">
                    {[
                      ['all', 'All'],
                      ['pending', 'To review'],
                      ['low', 'Low confidence'],
                    ].map(([value, title]) => (
                      <button
                        key={value}
                        aria-pressed={objectFilter === value}
                        onClick={() => setObjectFilter(value)}
                      >
                        {title}
                      </button>
                    ))}
                  </div>
                </fieldset>
                <ul ref={objectList} className="review-labels">
                  {loading ? (
                    <li className="object-empty">Loading labels…</li>
                  ) : !rows.length ? (
                    <li className="object-empty">
                      <SquareDashed size={24} />
                      <b>No boxes yet</b>
                      <span>
                        Draw a missing object, or approve an empty image after
                        inspection.
                      </span>
                    </li>
                  ) : !visibleRows.length ? (
                    <li className="object-empty">No matching objects.</li>
                  ) : (
                    visibleRows.map((a) => {
                      const n = rows.indexOf(a) + 1,
                        low =
                          a.confidence != null &&
                          a.confidence < (p.raw.confidence_threshold ?? 0.7);
                      return (
                        <li
                          key={a.id}
                          data-object-id={a.id}
                          className={`${selected === a.id ? 'is-selected' : ''} ${a.review_status === 'rejected' ? 'is-rejected' : ''}`}
                          style={colourStyle(colours[a.label])}
                          onMouseEnter={() => setHovered(a.id)}
                          onMouseLeave={() => setHovered('')}
                        >
                          <button
                            className="label-select"
                            disabled={busy}
                            aria-pressed={selected === a.id}
                            onClick={() => {
                              setSelected(a.id);
                              setTool('select');
                            }}
                          >
                            <span className="object-number">
                              {String(n).padStart(2, '0')}
                            </span>
                            <span className="object-name">
                              <b title={a.label}>{a.label}</b>
                              <small>{modelName(a)}</small>
                            </span>
                            <span
                              className={`object-confidence${low ? ' is-low' : ''}`}
                            >
                              {a.confidence == null
                                ? 'Human'
                                : `${Math.round(a.confidence * 100)}%`}
                            </span>
                            <span
                              className={`object-decision is-${a.review_status || 'pending'}`}
                              title={a.review_status || 'Not reviewed'}
                            >
                              {a.review_status === 'rejected' ? (
                                <X size={13} />
                              ) : ['approved', 'edited'].includes(
                                  a.review_status || '',
                                ) ? (
                                <Check size={13} />
                              ) : (
                                <i />
                              )}
                            </span>
                          </button>
                        </li>
                      );
                    })
                  )}
                </ul>
                <fieldset
                  className="object-inspector"
                  disabled={busy || loading || !loaded}
                >
                  {selectedRow ? (
                    <>
                      <div className="inspector-heading">
                        <span>Selected object</span>
                        <b>
                          #
                          {String(rows.indexOf(selectedRow) + 1).padStart(
                            2,
                            '0',
                          )}
                        </b>
                      </div>
                      <label className="inspector-class">
                        Class
                        <select
                          aria-label="Selected box class"
                          value={selectedRow.label}
                          onChange={(e) =>
                            update(selected, {
                              label: e.target.value,
                              review_status: 'edited',
                            })
                          }
                        >
                          {p.classes.map((c) => (
                            <option key={c}>{c}</option>
                          ))}
                        </select>
                      </label>
                      <div className="object-actions">
                        <button
                          className={
                            selectedRow.review_status === 'approved'
                              ? 'is-active'
                              : ''
                          }
                          aria-label={`Accept ${selectedRow.label}`}
                          onClick={() =>
                            update(selected, { review_status: 'approved' })
                          }
                        >
                          <Check size={14} />
                          Accept
                        </button>
                        <button
                          className={
                            selectedRow.review_status === 'rejected'
                              ? 'is-active is-reject'
                              : ''
                          }
                          aria-label={`Reject ${selectedRow.label}`}
                          onClick={() =>
                            update(selected, { review_status: 'rejected' })
                          }
                        >
                          <X size={14} />
                          Reject
                        </button>
                        <button
                          className="delete-object"
                          aria-label={`Delete ${selectedRow.label}`}
                          title="Delete object"
                          onClick={() => {
                            change(rows.filter((r) => r.id !== selected));
                            setSelected('');
                          }}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                      <details className="box-details">
                        <summary>
                          Geometry & source <ChevronDown size={12} />
                        </summary>
                        <p className="mono">
                          x {selectedRow.x.toFixed(2)} · y{' '}
                          {selectedRow.y.toFixed(2)}
                          <br />w {selectedRow.w.toFixed(2)} · h{' '}
                          {selectedRow.h.toFixed(2)} (%)
                        </p>
                        <p>
                          {modelName(selectedRow)} ·{' '}
                          {selectedRow.confidence == null
                            ? 'Human-created'
                            : `${(selectedRow.confidence * 100).toFixed(1)}% model confidence`}
                        </p>
                      </details>
                    </>
                  ) : (
                    <div className="inspector-placeholder">
                      <MousePointer2 size={18} />
                      <p>
                        Select an object to change its class or review decision.
                      </p>
                    </div>
                  )}
                </fieldset>
              </aside>
            </div>
            <div className="review-footer">
              <div>
                <span className="review-footer-title">
                  {isApproved(asset?.review_status || '')
                    ? 'Image approved'
                    : remaining
                      ? `${remaining} labels need a decision`
                      : 'Ready for your final decision'}
                </span>
                <p>
                  {asset?.inference_error ||
                    (dirty
                      ? 'Save your changes to continue.'
                      : isApproved(asset?.review_status || '')
                        ? 'Accepted labels are ready to export.'
                        : 'Saving edits does not approve this image.')}
                </p>
              </div>
              <div className="page-actions">
                <button
                  className="btn btn-ghost btn-sm"
                  disabled={busy || dirty || loading || !loaded || !imageReady}
                  onClick={() => decide('reject')}
                >
                  {activity === 'reject' ? 'Rejecting…' : 'Reject image'}
                </button>
                <button
                  className="btn btn-primary"
                  aria-label="Approve image"
                  disabled={
                    busy ||
                    dirty ||
                    loading ||
                    !loaded ||
                    !imageReady ||
                    asset?.status === 'failed' ||
                    remaining > 0 ||
                    isApproved(asset?.review_status || '')
                  }
                  onClick={() => decide('approve')}
                >
                  {activity === 'approve' ? (
                    <Loader2 size={15} className="spin" />
                  ) : (
                    <Check size={15} />
                  )}
                  {activity === 'approve'
                    ? 'Approving…'
                    : isApproved(asset?.review_status || '')
                      ? 'Approved'
                      : 'Approve image'}
                </button>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
