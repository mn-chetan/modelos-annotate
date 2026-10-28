/*
 * The Overview's charts, built to the dataviz specs: bars ≤ 24px with 4px rounded data-ends
 * and square baselines, 2px surface gaps, solid hairline grids, a legend whenever two or
 * more series share a plot, text in ink tokens (never the series colour), tooltips on hover
 * and keyboard focus, and a table view wherever a value would otherwise hide behind hover.
 * Every colour here was run through the palette validator.
 */
import { useLayoutEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react';
import { ObjectCrop } from '../../../showcase/specimens';
import { fmt, pctText, routeAt, type Overview, type Sample } from './model';

/** Blue means the AI decided; yellow means it went to people; green, approved by people. */
export const AI_COLOR = '#2A57C0';
export const REVIEW_COLOR = '#D39B0A';
export const APPROVED_COLOR = '#1F8A5B';
/** Sequential blue, light to dark (monotone, light end 2.41:1 on white). */
const SEQ = ['#8EA6E2', '#5F7FD1', '#2F52B4', '#162E73'];
const SEQ_TEXT = ['var(--ink)', 'var(--ink)', '#fff', '#fff'];

/* ---------- Plumbing ---------- */

/** Draw at the container's real pixel width so type and marks keep their specified sizes. */
function useWidth(fallback = 640) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(240, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

type TipState = { x: number; y: number; value: ReactNode; label: ReactNode } | null;

/** Values lead, labels follow. */
function Tip({ tip, width }: { tip: TipState; width: number }) {
  if (!tip) return null;
  const edge = tip.x < 90 ? 'is-left' : tip.x > width - 90 ? 'is-right' : '';
  return (
    <div className={`ov-tip ${edge}`} style={{ left: tip.x, top: tip.y }} role="status">
      <b>{tip.value}</b>
      <span>{tip.label}</span>
    </div>
  );
}

/** Smallest clean ceiling at or above the peak. */
const niceMax = (v: number) => {
  if (v <= 0) return 1;
  const mag = Math.pow(10, Math.floor(Math.log10(v)));
  return [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find((m) => m * mag >= v)! * mag;
};
const compact = (n: number) => (n >= 10_000 ? `${Math.round(n / 1000)}K` : n >= 1000 ? `${(n / 1000).toFixed(1).replace(/\.0$/, '')}K` : fmt(n));

/** Rounded top, square baseline. */
const colPath = (x: number, y: number, w: number, h: number, r = 4) => {
  if (h <= 0) return '';
  const rr = Math.min(r, h, w / 2);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
};

/** Rounded right end, square at the left baseline. */
const barPath = (x: number, y: number, w: number, h: number, r = 4) => {
  if (w <= 0) return '';
  const rr = Math.min(r, w, h / 2);
  return `M${x},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h - rr}Q${x + w},${y + h} ${x + w - rr},${y + h}H${x}Z`;
};

/* ---------- Figure: title, legend, chart or table ---------- */

export type TableSpec = { cols: string[]; rows: (string | number)[][] };

export function Figure({ title, sub, legend, table, children }: { title: ReactNode; sub?: ReactNode; legend?: ReactNode; table?: TableSpec; children: ReactNode }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <figure className="ov-fig">
      <figcaption className="ov-fig-head">
        <div>
          <h2 className="ov-fig-title">{title}</h2>
          {sub ? <p className="ov-fig-sub">{sub}</p> : null}
        </div>
        {table ? (
          <div className="ov-seg" role="group" aria-label="Show as">
            <button aria-pressed={!asTable} onClick={() => setAsTable(false)}>
              Chart
            </button>
            <button aria-pressed={asTable} onClick={() => setAsTable(true)}>
              Table
            </button>
          </div>
        ) : null}
      </figcaption>
      {legend && !asTable ? <div className="ov-legend">{legend}</div> : null}
      {asTable && table ? <DataTable spec={table} /> : children}
    </figure>
  );
}

function DataTable({ spec }: { spec: TableSpec }) {
  return (
    <div className="ov-table-wrap">
      <table className="ov-table">
        <thead>
          <tr>
            {spec.cols.map((c, i) => (
              <th key={c} scope="col" className={i ? 'num' : undefined}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {spec.rows.map((r, ri) => (
            <tr key={ri}>
              {r.map((v, i) => (
                <td key={i} className={i ? 'num' : undefined}>
                  {typeof v === 'number' ? fmt(v) : v}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Key({ color, kind = 'rect', children }: { color: string; kind?: 'rect' | 'line'; children: ReactNode }) {
  return (
    <span className="ov-key">
      <i className={`is-${kind}`} style={{ background: color }} aria-hidden />
      {children}
    </span>
  );
}

export function SeqKey({ low, high }: { low: string; high: string }) {
  return (
    <span className="ov-seqkey">
      {low}
      {SEQ.map((c) => (
        <i key={c} style={{ background: c }} />
      ))}
      {high}
    </span>
  );
}

export function SampleView({ sample }: { sample: Sample }) {
  if (sample.kind === 'crop') return <ObjectCrop box={sample.box} src={sample.src} ratio={sample.ratio} pad={sample.box.w < 5 ? 2.5 : 1.2} className="ov-crop" />;
  return <span className="ov-snippet">“{sample.text}”</span>;
}

/* ---------- AI approval threshold: one draggable line over items by confidence ---------- */

export const PRESETS = [0.85, 0.9, 0.95];

/** The line being explored, starting from the project's own. */
export function useLine(initial: number) {
  const [line, setLine] = useState(initial);
  return { line, setLine, initial };
}

export function Routing({ o, t, height = 190 }: { o: Overview; t: ReturnType<typeof useLine>; height?: number }) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<TipState>(null);
  const dragging = useRef(false);
  const pad = { l: 36, r: 12, t: 46, b: 26 };
  const bins = o.bins;
  const band = (W - pad.l - pad.r) / bins.length;
  const bw = band - 2;
  // The approved bins can dwarf the review band, which is the point of the chart; when they
  // do, break the axis and print their true counts above the break.
  const peak = Math.max(...bins.map((b) => b.n));
  const body = Math.max(1, ...bins.filter((b) => b.hi <= t.initial + 1e-9).map((b) => b.n));
  const broken = peak > body * 3;
  // Counts are whole items: small ceilings stay even so the middle gridline is a whole number.
  const ceiling = broken ? niceMax(body * 2.2) : niceMax(peak);
  const max = ceiling < 4 ? Math.max(2, Math.ceil(ceiling / 2) * 2) : ceiling;
  const tall = bins.filter((b) => b.n > max);
  const roomy = band >= 34;
  const y = (v: number) => pad.t + (height - pad.t - pad.b) * (1 - v / max);
  const span = 1 - o.floor;
  const xAt = (v: number) => pad.l + ((v - o.floor) / span) * (W - pad.l - pad.r);
  const set = (v: number) => t.setLine(+Math.min(0.975, Math.max(o.floor + 0.05, Math.round(v / 0.025) * 0.025)).toFixed(3));
  const fromPointer = (e: PointerEvent<SVGElement>) => {
    const r = (e.currentTarget.ownerSVGElement ?? (e.currentTarget as SVGSVGElement)).getBoundingClientRect();
    return o.floor + ((e.clientX - r.left - pad.l) / (W - pad.l - pad.r)) * span;
  };
  const ticks = Array.from({ length: Math.round(span * 10) + 1 }, (_, i) => +(o.floor + i * 0.1).toFixed(1));
  const onKey = (e: KeyboardEvent) => {
    const step = e.key === 'ArrowRight' || e.key === 'ArrowUp' ? 0.025 : e.key === 'ArrowLeft' || e.key === 'ArrowDown' ? -0.025 : 0;
    if (step) {
      e.preventDefault();
      set(t.line + step);
    }
  };
  const label = t.line.toFixed(3).replace(/0$/, '');
  const r = routeAt(o, t.line);

  return (
    <div className="ov-routing">
      <div className="ov-chart" ref={ref} onPointerLeave={() => setTip(null)}>
        <svg width={W} height={height} role="group" aria-label={`Items by AI confidence, with the approval line${broken ? '; the tallest bars are cut, with their counts printed above' : ''}`}>
          <g className="ov-grid">
            {[0, max / 2, max].map((v) => (
              <line key={v} x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} />
            ))}
          </g>
          <g className="ov-axis">
            {[0, max / 2, max].map((v) => (
              <text key={v} x={pad.l - 8} y={y(v) + 4} textAnchor="end">
                {compact(v)}
              </text>
            ))}
            {ticks.map((v) => (
              <text key={v} x={xAt(v)} y={height - 6} textAnchor="middle">
                {v.toFixed(1)}
              </text>
            ))}
          </g>
          {bins.map((b, i) => {
            const auto = b.lo >= t.line - 1e-9;
            const x = pad.l + band * i + 1;
            const over = b.n > max;
            const top = y(Math.min(b.n, max));
            const brk = y(max * 0.78);
            const show = () =>
              setTip({
                x: x + bw / 2,
                y: top,
                value: `${fmt(b.n)} ${o.unit}`,
                label: `Confidence ${b.lo.toFixed(3)} to ${b.hi.toFixed(3)} · ${auto ? 'approved by AI' : 'sent to human review'}`,
              });
            return (
              <g key={i}>
                <path d={colPath(x, top, bw, y(0) - top, 3)} fill={auto ? AI_COLOR : REVIEW_COLOR} />
                {over ? (
                  <>
                    <path d={`M${x - 1},${brk + 3}L${x + bw + 1},${brk - 1}L${x + bw + 1},${brk + 2}L${x - 1},${brk + 6}Z`} fill="var(--surface)" />
                    {roomy ? (
                      <text className="ov-overflow" x={x + bw / 2} y={top - 6} textAnchor="middle">
                        {compact(b.n)}
                      </text>
                    ) : null}
                  </>
                ) : null}
                <rect className="ov-hit" x={x - 1} y={pad.t} width={band} height={height - pad.t - pad.b} onPointerMove={show} />
              </g>
            );
          })}
          {broken && !roomy ? (
            <text className="ov-overflow" x={Math.min(pad.l + band * bins.indexOf(tall[0]), xAt(t.line)) - 10} y={pad.t + 4} textAnchor="end">
              {tall.map((b) => compact(b.n)).join(' · ')} above the cut
            </text>
          ) : null}
          <g
            className="ov-handle"
            transform={`translate(${xAt(t.line)},0)`}
            tabIndex={0}
            role="slider"
            aria-label="AI approves at or above this confidence"
            aria-valuemin={+(o.floor + 0.05).toFixed(2)}
            aria-valuemax={0.975}
            aria-valuenow={t.line}
            aria-valuetext={label}
            onKeyDown={onKey}
            onPointerDown={(e) => {
              dragging.current = true;
              (e.currentTarget as SVGGElement).setPointerCapture(e.pointerId);
            }}
            onPointerMove={(e) => dragging.current && set(fromPointer(e))}
            onPointerUp={() => (dragging.current = false)}
          >
            <rect x={-12} y={0} width={24} height={height - pad.b} fill="transparent" />
            <line y1={20} y2={height - pad.b} stroke="var(--ink)" strokeWidth={2} />
            <rect className="ov-handle-knob" x={-19} y={1} width={38} height={20} rx={10} />
            <text y={15} textAnchor="middle">
              {label}
            </text>
          </g>
        </svg>
        <Tip tip={tip} width={W} />
      </div>
      <div className="ov-presets">
        <span>AI approves at</span>
        {PRESETS.map((v) => (
          <button key={v} aria-pressed={Math.abs(t.line - v) < 1e-6} onClick={() => t.setLine(v)}>
            {v.toFixed(2)}
          </button>
        ))}
        <button className="ov-reset" onClick={() => t.setLine(t.initial)} disabled={t.line === t.initial}>
          Back to the project’s {t.initial.toFixed(2)}
        </button>
        <span className="ov-presets-note">Drag the line, or focus it and use the arrow keys.</span>
      </div>
      <span className="sr-only" aria-live="polite">{`${pctText(r.share)} of ${o.unit} go to human review.`}</span>
    </div>
  );
}

export const routingTable = (o: Overview, line: number): TableSpec => {
  const r = routeAt(o, line);
  return {
    cols: ['Route', o.unit[0].toUpperCase() + o.unit.slice(1), 'Share'],
    rows: [
      [`Approved by AI (${line} and up)`, r.auto, pctText(r.auto / Math.max(1, r.auto + r.review))],
      [`Sent to human review (below ${line})`, r.review, pctText(r.share)],
    ],
  };
};

/* ---------- Can we trust the AI's confidence? A reliability diagram ---------- */

export function Calibration({ o, line }: { o: Overview; line: number }) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<TipState>(null);
  const H = 230;
  const pad = { l: 40, r: 12, t: 14, b: 26 };
  const f = o.floor;
  const x = (v: number) => pad.l + ((v - f) / (1 - f)) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v);
  const slope = (-Math.atan2(y(f) - y(1), x(1) - x(f)) * 180) / Math.PI;
  const xTicks = Array.from({ length: Math.round((1 - f) * 10) + 1 }, (_, i) => +(f + i * 0.1).toFixed(1));
  const mid = +(f + (1 - f) * 0.35).toFixed(2);
  return (
    <div className="ov-chart" ref={ref} onPointerLeave={() => setTip(null)}>
      <svg width={W} height={H} role="img" aria-label="How often the AI was right at each level of confidence it stated">
        <g className="ov-grid">
          {[0, 0.25, 0.5, 0.75, 1].map((v) => (
            <line key={v} x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} />
          ))}
        </g>
        <g className="ov-axis">
          {[0, 0.5, 1].map((v) => (
            <text key={v} x={pad.l - 8} y={y(v) + 4} textAnchor="end">
              {Math.round(v * 100)}%
            </text>
          ))}
          {xTicks.map((v) => (
            <text key={v} x={x(v)} y={H - 6} textAnchor="middle">
              {v.toFixed(1)}
            </text>
          ))}
        </g>
        {o.calibration.filter((b) => b.items > 0).map((b) => {
          const x0 = x(b.lo) + 2;
          const w = x(b.hi) - x(b.lo) - 4;
          const show = () => setTip({ x: x0 + w / 2, y: y(b.acc), value: `Right ${pctText(b.acc)}`, label: `Scored ${b.lo.toFixed(2)} to ${b.hi.toFixed(2)} · ${fmt(b.items)} reviewed ${o.labelNoun}` });
          return (
            <g key={b.lo}>
              <path d={colPath(x0, y(Math.max(b.acc, 0.01)), w, y(0) - y(Math.max(b.acc, 0.01)))} fill={b.lo >= line - 1e-9 ? AI_COLOR : REVIEW_COLOR} opacity={b.items < 5 ? 0.45 : 1} />
              <rect className="ov-hit" x={x0} y={pad.t} width={w} height={H - pad.t - pad.b} tabIndex={0} aria-label={`Scored ${b.lo} to ${b.hi}: right ${pctText(b.acc)}`} onPointerMove={show} onFocus={show} onBlur={() => setTip(null)} />
            </g>
          );
        })}
        {/* Perfectly calibrated: right exactly as often as it claims. */}
        <line x1={x(f)} y1={y(f)} x2={x(1)} y2={y(1)} stroke="var(--ink)" strokeWidth={1.5} pointerEvents="none" />
        {W > 420 ? (
          <text className="ov-anno" x={x(mid)} y={y(mid) - 8} transform={`rotate(${slope},${x(mid)},${y(mid) - 8})`}>
            Right exactly as often as it claims
          </text>
        ) : null}
      </svg>
      <Tip tip={tip} width={W} />
    </div>
  );
}

export const calibrationTable = (o: Overview): TableSpec => ({
  cols: ['AI confidence', 'Right', `Reviewed ${o.labelNoun}`],
  rows: o.calibration.filter((b) => b.items > 0).map((b) => [`${b.lo.toFixed(2)} to ${b.hi.toFixed(2)}`, pctText(b.acc), b.items]),
});

/* ---------- Ranked horizontal bars ---------- */

export function HBars({
  rows,
  labelW = 150,
}: {
  rows: { key: string; label: ReactNode; value: number; color: string; note: string }[];
  labelW?: number;
}) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<TipState>(null);
  const row = 34;
  const lw = W < 480 ? Math.min(labelW, 120) : labelW;
  const max = Math.max(...rows.map((r) => r.value), 1);
  const span = W - lw - 56;
  const H = rows.length * row + 4;
  return (
    <div className="ov-chart" ref={ref} onPointerLeave={() => setTip(null)}>
      <svg width={W} height={H} role="img" aria-label={rows.map((r) => `${r.key} ${fmt(r.value)}`).join(', ')}>
        <line x1={lw} x2={lw} y1={0} y2={H} stroke="var(--rule)" />
        {rows.map((r, i) => {
          const w = Math.max(2, (r.value / max) * span);
          const y = i * row + 8;
          const show = () => setTip({ x: lw + w / 2, y, value: fmt(r.value), label: r.note });
          return (
            <g key={r.key}>
              <foreignObject x={0} y={i * row} width={lw - 10} height={row}>
                <div className="ov-hlabel">{r.label}</div>
              </foreignObject>
              <path d={barPath(lw, y, w, 18)} fill={r.color} />
              <text className="ov-value" x={lw + w + 8} y={y + 13}>
                {fmt(r.value)}
              </text>
              <rect className="ov-hit" x={0} y={i * row} width={W} height={row} tabIndex={0} aria-label={`${r.key}: ${fmt(r.value)}`} onPointerMove={show} onFocus={show} onBlur={() => setTip(null)} />
            </g>
          );
        })}
      </svg>
      <Tip tip={tip} width={W} />
    </div>
  );
}

/* ---------- Heatmap: a grid of rates ---------- */

export function Heatmap({
  rows,
  cols,
  values,
  rowTitle,
  colTitle,
  describe,
}: {
  rows: string[];
  cols: string[];
  values: number[][];
  rowTitle: string;
  colTitle: string;
  describe: (r: number, c: number, v: number) => string;
}) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<TipState>(null);
  const labelW = Math.min(130, Math.max(...rows.map((r) => r.length)) * 7.2 + 16);
  const cw = Math.max(40, Math.min(96, (W - labelW) / cols.length));
  const ch = 38;
  const headH = Math.max(...cols.map((c) => c.length)) * 6.4 > cw - 6 ? 64 : 30;
  const max = Math.max(1e-9, ...values.flat());
  const step = (v: number) => Math.min(SEQ.length - 1, Math.floor((v / max) * SEQ.length * 0.999));
  const H = headH + rows.length * ch;
  const format = (v: number) => `${Math.round(v * 100)}%`;
  return (
    <div className="ov-chart" ref={ref} onPointerLeave={() => setTip(null)}>
      <svg width={W} height={H + 18} role="img" aria-label={`${rowTitle} by ${colTitle}`}>
        <text className="ov-axis-title" x={4} y={14}>
          {rowTitle}
        </text>
        <text className="ov-axis-title" x={labelW + (cols.length * cw) / 2} y={H + 14} textAnchor="middle">
          {colTitle}
        </text>
        {cols.map((c, j) =>
          headH > 30 ? (
            <text key={c} className="ov-colhead" transform={`translate(${labelW + j * cw + cw / 2 + 4},${headH - 6}) rotate(-35)`}>
              {c}
            </text>
          ) : (
            <text key={c} className="ov-colhead" x={labelW + j * cw + cw / 2} y={headH - 10} textAnchor="middle">
              {c}
            </text>
          ),
        )}
        {rows.map((r, i) => (
          <g key={r}>
            <text className="ov-rowlabel" x={labelW - 10} y={headH + i * ch + ch / 2 + 4} textAnchor="end">
              {r}
            </text>
            {cols.map((c, j) => {
              const v = values[i][j];
              const k = step(v);
              const x = labelW + j * cw;
              const y = headH + i * ch;
              const show = () => setTip({ x: x + cw / 2, y, value: format(v), label: describe(i, j, v) });
              return (
                <g key={c}>
                  <rect x={x + 1} y={y + 1} width={cw - 2} height={ch - 2} rx={4} fill={SEQ[k]} />
                  <text className="ov-cell" x={x + cw / 2} y={y + ch / 2 + 4} textAnchor="middle" fill={SEQ_TEXT[k]}>
                    {format(v)}
                  </text>
                  <rect className="ov-hit" x={x} y={y} width={cw} height={ch} tabIndex={0} aria-label={`${r}, ${c}: ${format(v)}`} onPointerMove={show} onFocus={show} onBlur={() => setTip(null)} />
                </g>
              );
            })}
          </g>
        ))}
      </svg>
      <Tip tip={tip} width={W} />
    </div>
  );
}
