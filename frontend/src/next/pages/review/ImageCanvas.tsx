/*
 * The image half of the review bench: select, move and resize boxes, draw missing ones,
 * zoom, and show names. Geometry is in image percentages, so it survives any zoom.
 */
import { useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { Maximize, MousePointer2, SquareDashed, ZoomIn, ZoomOut } from 'lucide-react';
import { api } from '../../../services/api';
import type { Annotation, LiveAsset, LiveProject } from '../../store';
import { BoxOverlay } from '../BoxOverlay';
import { colourStyle } from '../annotation-ui';
import type { Edits } from './useEdits';

type Point = { x: number; y: number };
type Gesture = { start: Point; original: Annotation; kind: string };

const clamp = (v: number, min = 0, max = 100) => Math.max(min, Math.min(max, v));
/** At 100% the whole image fits the stage, whichever of its width or height runs out first. */
function fitWidth(a: LiveAsset, zoom: number) {
  const ratio = a.width && a.height ? a.width / a.height : 4 / 3;
  return `min(${zoom * 100}%, calc(${zoom} * (min(72vh, 820px) - 28px) * ${ratio.toFixed(4)}))`;
}

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 3;

export function ImageCanvas({
  project: p,
  asset,
  edits,
  colours,
  selected,
  onSelect,
  drawClass,
  onDrawClass,
}: {
  project: LiveProject;
  asset: LiveAsset;
  edits: Edits;
  colours: Record<string, string>;
  selected: string;
  onSelect: (id: string) => void;
  drawClass: string;
  onDrawClass: (name: string) => void;
}) {
  const [tool, setTool] = useState<'select' | 'draw'>('select');
  const [names, setNames] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [hovered, setHovered] = useState('');
  const [ready, setReady] = useState(false);
  const [broken, setBroken] = useState(false);
  const gesture = useRef<Gesture | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const locked = !!edits.busy || edits.loading || !ready;
  const step = (d: number) => setZoom((z) => clamp(Math.round((z + d) * 100) / 100, ZOOM_MIN, ZOOM_MAX));

  function point(e: ReactPointerEvent): Point {
    const r = svg.current!.getBoundingClientRect();
    return { x: clamp(((e.clientX - r.left) / r.width) * 100), y: clamp(((e.clientY - r.top) / r.height) * 100) };
  }

  function down(e: ReactPointerEvent<SVGSVGElement>) {
    if (locked || e.button !== 0) return;
    const pos = point(e);
    const target = e.target as SVGElement;
    const id = target.closest('[data-id]')?.getAttribute('data-id');
    const row = edits.rows.find((a) => a.id === id);
    if (tool === 'draw') {
      if (!drawClass) return;
      const box: Annotation = {
        id: crypto.randomUUID(),
        asset_id: asset.id,
        label: drawClass,
        x: pos.x,
        y: pos.y,
        w: 0.01,
        h: 0.01,
        source: 'human',
        geometry_type: 'box',
        review_status: 'approved',
        provenance: {},
      };
      edits.change([...edits.rows, box]);
      onSelect(box.id);
      gesture.current = { start: pos, original: box, kind: 'draw' };
    } else if (row) {
      onSelect(row.id);
      edits.begin();
      gesture.current = { start: pos, original: { ...row }, kind: target.getAttribute('data-handle') || 'move' };
    } else {
      onSelect('');
      return;
    }
    e.currentTarget.setPointerCapture(e.pointerId);
    e.preventDefault();
  }

  function move(e: ReactPointerEvent<SVGSVGElement>) {
    const g = gesture.current;
    if (!g) return;
    const pos = point(e);
    const a = g.original;
    const dx = pos.x - g.start.x;
    const dy = pos.y - g.start.y;
    let box = { x: a.x, y: a.y, w: a.w, h: a.h };
    if (g.kind === 'move') {
      box = { ...box, x: clamp(a.x + dx, 0, 100 - a.w), y: clamp(a.y + dy, 0, 100 - a.h) };
    } else if (g.kind === 'draw') {
      box = { x: Math.min(g.start.x, pos.x), y: Math.min(g.start.y, pos.y), w: Math.max(0.01, Math.abs(dx)), h: Math.max(0.01, Math.abs(dy)) };
    } else {
      let left = a.x;
      let top = a.y;
      let right = a.x + a.w;
      let bottom = a.y + a.h;
      if (g.kind.includes('w')) left = clamp(a.x + dx, 0, right - 0.1);
      if (g.kind.includes('e')) right = clamp(a.x + a.w + dx, left + 0.1, 100);
      if (g.kind.includes('n')) top = clamp(a.y + dy, 0, bottom - 0.1);
      if (g.kind.includes('s')) bottom = clamp(a.y + a.h + dy, top + 0.1, 100);
      box = { x: left, y: top, w: right - left, h: bottom - top };
    }
    // A moved AI box counts as corrected; a box a person just drew stays accepted.
    const status = g.kind === 'draw' ? 'approved' : 'edited';
    edits.live((rows) => rows.map((r) => (r.id === a.id ? { ...r, ...box, review_status: status } : r)));
  }

  function up(e: ReactPointerEvent<SVGSVGElement>) {
    const g = gesture.current;
    if (!g) return;
    // A click in draw mode, rather than a drag, leaves no sliver behind.
    if (g.kind === 'draw') edits.live((rows) => rows.filter((a) => a.id !== g.original.id || (a.w >= 0.15 && a.h >= 0.15)));
    gesture.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
  }

  return (
    <div className="rv-canvas">
      <div className="rv-tools" role="toolbar" aria-label="Image tools">
        <div className="seg">
          <button aria-pressed={tool === 'select'} onClick={() => setTool('select')} title="Select, move and resize boxes">
            <MousePointer2 size={14} aria-hidden /> Select
          </button>
          <button aria-pressed={tool === 'draw'} onClick={() => setTool('draw')} title="Drag on the image to draw a box">
            <SquareDashed size={14} aria-hidden /> Draw
          </button>
        </div>
        {tool === 'draw' ? (
          <select className="rv-select" aria-label="Class for new boxes" value={drawClass} onChange={(e) => onDrawClass(e.target.value)}>
            {p.classes.map((c, i) => (
              <option key={c} value={c}>
                {i < 9 ? `${i + 1}  ` : ''}
                {c}
              </option>
            ))}
          </select>
        ) : null}
        <span className="spacer" />
        <label className="rv-toggle" title="Show every box's name, spaced so they don't overlap">
          <input type="checkbox" checked={names} onChange={(e) => setNames(e.target.checked)} /> Names
        </label>
        <span className="rv-zoom">
          <button className="rv-icon" aria-label="Zoom out" disabled={zoom <= ZOOM_MIN} onClick={() => step(-0.25)}>
            <ZoomOut size={16} />
          </button>
          <span className="mono">{Math.round(zoom * 100)}%</span>
          <button className="rv-icon" aria-label="Zoom in" disabled={zoom >= ZOOM_MAX} onClick={() => step(0.25)}>
            <ZoomIn size={16} />
          </button>
          <button className="rv-icon" aria-label="Fit image" title="Fit" disabled={zoom === 1} onClick={() => setZoom(1)}>
            <Maximize size={15} />
          </button>
        </span>
      </div>

      <div className="rv-stage">
        <div className="rv-scroll">
          <div className="image-boxes rv-image" style={{ width: fitWidth(asset, zoom) }}>
            {broken ? (
              <p className="rv-broken">The image couldn’t be loaded.</p>
            ) : (
              <img
                src={api.getAssetImageUrl(asset.id)}
                alt={asset.filename}
                draggable={false}
                onLoad={() => setReady(true)}
                onError={() => setBroken(true)}
              />
            )}
            {!broken ? (
              <BoxOverlay
                annotations={edits.rows}
                colours={colours}
                selected={selected}
                hovered={hovered}
                names={names}
                editable
                svgRef={svg}
                aria-label="Boxes on this image"
                style={{ cursor: tool === 'draw' ? 'crosshair' : 'default' }}
                onHover={setHovered}
                onPointerDown={down}
                onPointerMove={move}
                onPointerUp={up}
                onPointerCancel={up}
              />
            ) : null}
          </div>
        </div>
      </div>

      <ul className="rv-legend" aria-label="Classes">
        {p.classes.map((c, i) => {
          const n = edits.rows.filter((a) => a.label === c && a.review_status !== 'rejected').length;
          return (
            <li key={c} style={colourStyle(colours[c])} className={n ? '' : 'is-none'}>
              <i aria-hidden />
              {i < 9 ? <kbd>{i + 1}</kbd> : null}
              {c}
              <b className="mono">{n}</b>
            </li>
          );
        })}
      </ul>
      {asset.caption ? (
        <p className="rv-caption">
          <span>AI scene note</span> {asset.caption}
        </p>
      ) : null}
    </div>
  );
}
