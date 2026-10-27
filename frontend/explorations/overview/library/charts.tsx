/*
 * Chart primitives for the library, to the same dataviz specs as the Overview: thin marks,
 * 4px rounded data-ends, 2px surface gaps, solid hairline grids, text in ink tokens,
 * tooltips on hover and focus, and colour validated before use.
 */
import { useState, type ReactNode } from 'react';
import { useWidth } from '../viz';
import { fmt, pctText } from '../model';

/** Sequential blue, light to dark (validated: monotone, light end 2.41:1 on white). */
export const SEQ = ['#8EA6E2', '#5F7FD1', '#2F52B4', '#162E73'];
const SEQ_TEXT = ['var(--ink)', 'var(--ink)', '#fff', '#fff'];
const step = (v: number, max: number) => (max <= 0 ? 0 : Math.min(SEQ.length - 1, Math.floor((v / max) * SEQ.length * 0.999)));

type Tip = { x: number; y: number; value: ReactNode; label: ReactNode } | null;

function TipBox({ tip, width }: { tip: Tip; width: number }) {
  if (!tip) return null;
  const edge = tip.x < 90 ? 'is-left' : tip.x > width - 90 ? 'is-right' : '';
  return (
    <div className={`ov-tip ${edge}`} style={{ left: tip.x, top: tip.y }} role="status">
      <b>{tip.value}</b>
      <span>{tip.label}</span>
    </div>
  );
}

const rounded = (x: number, y: number, w: number, h: number, r = 4) => {
  if (w <= 0) return '';
  const rr = Math.min(r, w, h / 2);
  return `M${x},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h - rr}Q${x + w},${y + h} ${x + w - rr},${y + h}H${x}Z`;
};
const colPath = (x: number, y: number, w: number, h: number, r = 4) => {
  if (h <= 0) return '';
  const rr = Math.min(r, h, w / 2);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
};

/* ---------- Heatmap: a grid of counts or rates ---------- */

export function Heatmap({
  rows,
  cols,
  values,
  format = (v) => fmt(v),
  neutral,
  rowTitle,
  colTitle,
  describe,
  cell = 44,
}: {
  rows: string[];
  cols: string[];
  values: (number | null)[][];
  format?: (v: number) => string;
  /** Cells drawn quiet (e.g. the correct diagonal) and left out of the colour scale. */
  neutral?: (r: number, c: number) => boolean;
  rowTitle: string;
  colTitle: string;
  describe: (r: number, c: number, v: number) => string;
  cell?: number;
}) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<Tip>(null);
  const labelW = Math.min(150, Math.max(...rows.map((r) => r.length)) * 7.2 + 16);
  const cw = Math.max(34, Math.min(cell * 2, (W - labelW) / cols.length));
  const ch = Math.min(cell, 40);
  const headH = Math.max(...cols.map((c) => c.length)) * 6.2 > cw - 6 ? 64 : 28;
  const max = Math.max(1e-9, ...values.flatMap((r, i) => r.map((v, j) => (v == null || neutral?.(i, j) ? 0 : v))));
  const H = headH + rows.length * ch;
  return (
    <div className="ov-chart" ref={ref} onPointerLeave={() => setTip(null)}>
      <svg width={W} height={H + 18} role="img" aria-label={`${rowTitle} by ${colTitle}`}>
        <text className="lib-axis-title" x={labelW + (cols.length * cw) / 2} y={H + 14} textAnchor="middle">
          {colTitle}
        </text>
        {cols.map((c, j) =>
          headH > 28 ? (
            <text key={c} className="lib-head" transform={`translate(${labelW + j * cw + cw / 2 + 4},${headH - 6}) rotate(-35)`}>
              {c}
            </text>
          ) : (
            <text key={c} className="lib-head" x={labelW + j * cw + cw / 2} y={headH - 10} textAnchor="middle">
              {c}
            </text>
          ),
        )}
        {rows.map((r, i) => (
          <g key={r}>
            <text className="lib-rowlabel" x={labelW - 10} y={headH + i * ch + ch / 2 + 4} textAnchor="end">
              {r}
            </text>
            {cols.map((c, j) => {
              const v = values[i][j];
              const x = labelW + j * cw;
              const y = headH + i * ch;
              if (v == null) return <rect key={c} x={x + 1} y={y + 1} width={cw - 2} height={ch - 2} rx={4} fill="var(--rule2)" opacity={0.5} />;
              const quiet = neutral?.(i, j);
              const k = step(v, max);
              const fill = quiet ? 'var(--surface)' : v === 0 ? 'var(--surface)' : SEQ[k];
              const show = () => setTip({ x: x + cw / 2, y, value: format(v), label: describe(i, j, v) });
              return (
                <g key={c}>
                  <rect x={x + 1} y={y + 1} width={cw - 2} height={ch - 2} rx={4} fill={fill} stroke={quiet || v === 0 ? 'var(--rule)' : 'none'} />
                  <text className="lib-cell" x={x + cw / 2} y={y + ch / 2 + 4} textAnchor="middle" fill={quiet || v === 0 ? 'var(--muted)' : SEQ_TEXT[k]}>
                    {v === 0 && !quiet ? '·' : format(v)}
                  </text>
                  <rect className="ov-hit" x={x} y={y} width={cw} height={ch} tabIndex={0} aria-label={`${r}, ${c}: ${format(v)}`} onPointerMove={show} onFocus={show} onBlur={() => setTip(null)} />
                </g>
              );
            })}
          </g>
        ))}
        <text className="lib-axis-title" x={4} y={14}>
          {rowTitle}
        </text>
      </svg>
      <TipBox tip={tip} width={W} />
    </div>
  );
}

export function SeqKey({ low, high }: { low: string; high: string }) {
  return (
    <span className="lib-seqkey">
      {low}
      {SEQ.map((c) => (
        <i key={c} style={{ background: c }} />
      ))}
      {high}
    </span>
  );
}

/* ---------- Ranked horizontal bars ---------- */

export function HBars({
  rows,
  format = (v) => fmt(v),
  max,
  color = 'var(--blue)',
  labelW = 150,
  extra,
}: {
  rows: { label: ReactNode; key: string; value: number; color?: string; note?: string; mark?: number }[];
  format?: (v: number) => string;
  max?: number;
  color?: string;
  labelW?: number;
  /** Optional reference mark per row (e.g. the project average), drawn as a tick. */
  extra?: { name: string; value: number };
}) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<Tip>(null);
  const row = 34;
  const lw = W < 480 ? Math.min(labelW, 110) : labelW;
  const m = max ?? Math.max(...rows.map((r) => r.value), 1e-9);
  const span = W - lw - 64;
  const H = rows.length * row + 4;
  return (
    <div className="ov-chart" ref={ref} onPointerLeave={() => setTip(null)}>
      <svg width={W} height={H} role="img" aria-label="Ranked bars">
        <line x1={lw} x2={lw} y1={0} y2={H} stroke="var(--rule)" />
        {extra ? (
          <g>
            <line x1={lw + (extra.value / m) * span} x2={lw + (extra.value / m) * span} y1={0} y2={H} stroke="var(--ink)" strokeWidth={1.5} />
          </g>
        ) : null}
        {rows.map((r, i) => {
          const w = Math.max(2, (r.value / m) * span);
          const y = i * row + 8;
          const show = () => setTip({ x: lw + w / 2, y, value: format(r.value), label: r.note ?? r.key });
          return (
            <g key={r.key}>
              <foreignObject x={0} y={i * row} width={lw - 10} height={row}>
                <div className="lib-hlabel">{r.label}</div>
              </foreignObject>
              <path d={rounded(lw, y, w, 18)} fill={r.color ?? color} />
              <text className="lib-value" x={lw + w + 8} y={y + 13}>
                {format(r.value)}
              </text>
              <rect className="ov-hit" x={0} y={i * row} width={W} height={row} tabIndex={0} aria-label={`${r.key}: ${format(r.value)}`} onPointerMove={show} onFocus={show} onBlur={() => setTip(null)} />
            </g>
          );
        })}
      </svg>
      <TipBox tip={tip} width={W} />
    </div>
  );
}

/* ---------- 100% stacked rows: parts of each whole ---------- */

export function StackRows({ rows, parts, colors, labelW = 130 }: { rows: { name: string; values: number[] }[]; parts: string[]; colors: string[]; labelW?: number }) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<Tip>(null);
  const row = 32;
  const lw = W < 480 ? 96 : labelW;
  const span = W - lw;
  return (
    <div className="ov-chart" ref={ref} onPointerLeave={() => setTip(null)}>
      <svg width={W} height={rows.length * row} role="img" aria-label="Share of each part, per row">
        {rows.map((r, i) => {
          const total = r.values.reduce((a, b) => a + b, 0) || 1;
          const live = r.values.map((v, k) => [v, k] as const).filter(([v]) => v > 0);
          const gaps = (live.length - 1) * 2;
          let x = lw;
          return (
            <g key={r.name}>
              <text className="lib-rowlabel" x={lw - 10} y={i * row + 20} textAnchor="end">
                {r.name}
              </text>
              {live.map(([v, k], idx) => {
                const w = (v / total) * (span - gaps);
                const x0 = x;
                x += w + 2;
                const first = idx === 0;
                const last = idx === live.length - 1;
                const h = 16;
                const y = i * row + 8;
                const rr = Math.min(4, w / 2);
                const d = `M${x0 + (first ? rr : 0)},${y}H${x0 + w - (last ? rr : 0)}${last ? `Q${x0 + w},${y} ${x0 + w},${y + rr}V${y + h - rr}Q${x0 + w},${y + h} ${x0 + w - rr},${y + h}` : `V${y + h}`}H${x0 + (first ? rr : 0)}${first ? `Q${x0},${y + h} ${x0},${y + h - rr}V${y + rr}Q${x0},${y} ${x0 + rr},${y}` : `V${y}`}Z`;
                const show = () => setTip({ x: x0 + w / 2, y, value: `${fmt(v)} · ${pctText(v / total)}`, label: `${r.name}: ${parts[k]}` });
                return (
                  <g key={k}>
                    <path d={d} fill={colors[k]} />
                    <rect className="ov-hit" x={x0} y={y - 6} width={w} height={h + 12} tabIndex={0} aria-label={`${r.name}, ${parts[k]}: ${fmt(v)}`} onPointerMove={show} onFocus={show} onBlur={() => setTip(null)} />
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
      <TipBox tip={tip} width={W} />
    </div>
  );
}

/* ---------- Reliability diagram: stated confidence against how often it was right ---------- */

export function Reliability({ bins, line }: { bins: { lo: number; hi: number; acc: number; items: number }[]; line: number }) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<Tip>(null);
  const H = 240;
  const pad = { l: 40, r: 12, t: 12, b: 30 };
  const x = (v: number) => pad.l + ((v - 0.4) / 0.6) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - (v - 0.3) / 0.7);
  return (
    <div className="ov-chart" ref={ref} onPointerLeave={() => setTip(null)}>
      <svg width={W} height={H} role="img" aria-label="AI confidence against how often the AI was right">
        <g className="ov-grid">
          {[0.4, 0.6, 0.8, 1].map((v) => (
            <line key={v} x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} />
          ))}
        </g>
        <g className="ov-axis">
          {[0.4, 0.6, 0.8, 1].map((v) => (
            <text key={v} x={pad.l - 8} y={y(v) + 4} textAnchor="end">
              {Math.round(v * 100)}%
            </text>
          ))}
          {[0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1].map((v) => (
            <text key={v} x={x(v)} y={H - 10} textAnchor="middle">
              {v.toFixed(1)}
            </text>
          ))}
        </g>
        {bins.map((b) => {
          const x0 = x(b.lo) + 2;
          const w = x(b.hi) - x(b.lo) - 4;
          const show = () => setTip({ x: x0 + w / 2, y: y(b.acc), value: `Right ${pctText(b.acc)}`, label: `Scored ${b.lo.toFixed(2)} to ${b.hi.toFixed(2)} · ${fmt(b.items)} items` });
          return (
            <g key={b.lo}>
              <path d={colPath(x0, y(b.acc), w, y(0.3) - y(b.acc))} fill={b.lo >= line - 1e-9 ? '#2A57C0' : '#D39B0A'} />
              <rect className="ov-hit" x={x0} y={pad.t} width={w} height={H - pad.t - pad.b} tabIndex={0} aria-label={`Scored ${b.lo} to ${b.hi}: right ${pctText(b.acc)}`} onPointerMove={show} onFocus={show} onBlur={() => setTip(null)} />
            </g>
          );
        })}
        {/* Perfectly calibrated: right exactly as often as it claims. */}
        <line x1={x(0.4)} y1={y(0.4)} x2={x(1)} y2={y(1)} stroke="var(--ink)" strokeWidth={1.5} pointerEvents="none" />
        <text className="lib-anno" x={x(0.62)} y={y(0.62) - 8} transform={`rotate(${(-Math.atan2(y(0.4) - y(1), x(1) - x(0.4)) * 180) / Math.PI},${x(0.62)},${y(0.62) - 8})`}>
          If the AI were right exactly as often as it claims
        </text>
        <line x1={x(line)} x2={x(line)} y1={pad.t} y2={H - pad.b} stroke="var(--ink)" strokeDasharray="3 3" />
        <text className="lib-anno" x={x(line) - 6} y={pad.t + 10} textAnchor="end">
          AI approves above {line}
        </text>
      </svg>
      <TipBox tip={tip} width={W} />
    </div>
  );
}

/* ---------- Dot strip: one value per person against the team median ---------- */

export function DotStrip({ rows, median, format, lowNote }: { rows: { name: string; v: number; flag?: boolean }[]; median: number; format: (v: number) => string; lowNote: string }) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<Tip>(null);
  const lw = W < 480 ? 96 : 130;
  const row = 32;
  const max = Math.max(...rows.map((r) => r.v), median) * 1.15;
  const x = (v: number) => lw + (v / max) * (W - lw - 20);
  const H = rows.length * row + 26;
  return (
    <div className="ov-chart" ref={ref} onPointerLeave={() => setTip(null)}>
      <svg width={W} height={H} role="img" aria-label="Each reviewer against the team median">
        <line x1={x(median)} x2={x(median)} y1={16} y2={H} stroke="var(--ink)" strokeWidth={1.5} />
        <text className="lib-anno" x={x(median)} y={10} textAnchor="middle">
          Team median {format(median)}
        </text>
        {rows.map((r, i) => {
          const y = 26 + i * row + row / 2;
          const show = () => setTip({ x: x(r.v), y: y - 8, value: format(r.v), label: r.flag ? `${r.name} · ${lowNote}` : r.name });
          return (
            <g key={r.name}>
              <line x1={lw} x2={W - 20} y1={y} y2={y} stroke="var(--rule2)" />
              <text className="lib-rowlabel" x={lw - 12} y={y + 4} textAnchor="end">
                {r.name}
              </text>
              <circle cx={x(r.v)} cy={y} r={6} fill={r.flag ? '#D39B0A' : '#2A57C0'} stroke="var(--surface)" strokeWidth={2} />
              <text className="lib-value" x={x(r.v) + 12} y={y + 4}>
                {format(r.v)}
              </text>
              <rect className="ov-hit" x={0} y={y - row / 2} width={W} height={row} tabIndex={0} aria-label={`${r.name}: ${format(r.v)}`} onPointerMove={show} onFocus={show} onBlur={() => setTip(null)} />
            </g>
          );
        })}
      </svg>
      <TipBox tip={tip} width={W} />
    </div>
  );
}

/* ---------- Columns: a simple histogram ---------- */

export function Columns({ rows, color = 'var(--blue)', xLabel, unit }: { rows: { label: string; n: number; color?: string }[]; color?: string; xLabel: string; unit: string }) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<Tip>(null);
  const H = 200;
  const pad = { l: 36, r: 8, t: 12, b: 40 };
  const max = Math.max(...rows.map((r) => r.n), 1);
  const band = (W - pad.l - pad.r) / rows.length;
  const bw = Math.min(24, band - 2);
  const y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const every = Math.max(1, Math.ceil(36 / band));
  return (
    <div className="ov-chart" ref={ref} onPointerLeave={() => setTip(null)}>
      <svg width={W} height={H} role="img" aria-label={xLabel}>
        <g className="ov-grid">
          {[0, max / 2, max].map((v) => (
            <line key={v} x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} />
          ))}
        </g>
        <g className="ov-axis">
          {[0, Math.round(max / 2), max].map((v) => (
            <text key={v} x={pad.l - 8} y={y(v) + 4} textAnchor="end">
              {fmt(v)}
            </text>
          ))}
          {rows.map((r, i) =>
            i % every === 0 ? (
              <text key={r.label} x={pad.l + band * i + band / 2} y={H - 24} textAnchor="middle">
                {r.label}
              </text>
            ) : null,
          )}
        </g>
        <text className="lib-axis-title" x={pad.l + (W - pad.l - pad.r) / 2} y={H - 4} textAnchor="middle">
          {xLabel}
        </text>
        {rows.map((r, i) => {
          const x = pad.l + band * i + (band - bw) / 2;
          const show = () => setTip({ x: x + bw / 2, y: y(r.n), value: `${fmt(r.n)} ${unit}`, label: r.label });
          return (
            <g key={r.label}>
              <path d={colPath(x, y(r.n), bw, y(0) - y(r.n))} fill={r.color ?? color} />
              <rect className="ov-hit" x={pad.l + band * i} y={pad.t} width={band} height={H - pad.t - pad.b} tabIndex={0} aria-label={`${r.label}: ${fmt(r.n)}`} onPointerMove={show} onFocus={show} onBlur={() => setTip(null)} />
            </g>
          );
        })}
      </svg>
      <TipBox tip={tip} width={W} />
    </div>
  );
}

/* ---------- Frame heatmap: where in the picture reviewers corrected the AI ---------- */

export function FrameHeat({ src, heat, grid }: { src: string; heat: number[]; grid: { cols: number; rows: number } }) {
  const [tip, setTip] = useState<Tip>(null);
  const [ref, W] = useWidth();
  const max = Math.max(...heat, 1);
  const H = W * (768 / 1376);
  const cw = W / grid.cols;
  const ch = H / grid.rows;
  return (
    <div className="ov-chart lib-frame" ref={ref} onPointerLeave={() => setTip(null)}>
      <img src={src} alt="" width={W} height={H} />
      <svg width={W} height={H} role="img" aria-label="Corrections by position in the frame">
        {heat.map((v, i) => {
          const x = (i % grid.cols) * cw;
          const y = Math.floor(i / grid.cols) * ch;
          const k = step(v, max);
          const show = () => setTip({ x: x + cw / 2, y, value: `${fmt(v)} corrections`, label: `${Math.floor(i / grid.cols) < grid.rows / 2 ? 'Upper' : 'Lower'} ${(i % grid.cols) < grid.cols / 3 ? 'left' : (i % grid.cols) < (2 * grid.cols) / 3 ? 'middle' : 'right'} of the frame` });
          return (
            <g key={i}>
              <rect x={x + 1} y={y + 1} width={cw - 2} height={ch - 2} rx={3} fill={SEQ[k]} opacity={0.12 + (v / max) * 0.7} />
              <rect className="ov-hit" x={x} y={y} width={cw} height={ch} tabIndex={0} aria-label={`Cell ${i + 1}: ${v} corrections`} onPointerMove={show} onFocus={show} onBlur={() => setTip(null)} />
            </g>
          );
        })}
      </svg>
      <TipBox tip={tip} width={W} />
    </div>
  );
}

/* ---------- Diverging bars: above or below zero per row, around a neutral centre ---------- */

export function Diverge({
  rows,
  posName,
  negName,
  posColor = '#2A57C0',
  negColor = '#D39B0A',
  format,
}: {
  rows: { name: string; v: number; note: string }[];
  posName: string;
  negName: string;
  posColor?: string;
  negColor?: string;
  format: (v: number) => string;
}) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<Tip>(null);
  const lw = W < 480 ? 92 : 120;
  const row = 32;
  // Headroom so the value label at the end of the longest bar never meets the row labels.
  const max = Math.max(...rows.map((r) => Math.abs(r.v)), 1e-9) * 1.7;
  const mid = lw + (W - lw) / 2;
  const half = (W - lw) / 2 - 8;
  const H = rows.length * row + 22;
  return (
    <div className="ov-chart" ref={ref} onPointerLeave={() => setTip(null)}>
      <svg width={W} height={H} role="img" aria-label={`${negName} and ${posName} by class`}>
        <text className="lib-anno" x={mid - 8} y={10} textAnchor="end">
          ← {negName}
        </text>
        <text className="lib-anno" x={mid + 8} y={10}>
          {posName} →
        </text>
        <line x1={mid} x2={mid} y1={16} y2={H} stroke="var(--ink)" strokeWidth={1.5} />
        {rows.map((r, i) => {
          const y = 22 + i * row + 8;
          const w = Math.max(2, (Math.abs(r.v) / max) * half);
          const pos = r.v >= 0;
          const x = pos ? mid + 1 : mid - 1 - w;
          const show = () => setTip({ x: pos ? x + w : x, y, value: format(r.v), label: r.note });
          return (
            <g key={r.name}>
              <text className="lib-rowlabel" x={lw - 12} y={y + 13} textAnchor="end">
                {r.name}
              </text>
              <path d={pos ? rounded(x, y, w, 16) : rounded(-(x + w), y, w, 16)} transform={pos ? undefined : 'scale(-1,1)'} fill={pos ? posColor : negColor} />
              <text className="lib-value" x={pos ? x + w + 8 : x - 8} y={y + 13} textAnchor={pos ? 'start' : 'end'}>
                {format(r.v)}
              </text>
              <rect className="ov-hit" x={0} y={22 + i * row} width={W} height={row} tabIndex={0} aria-label={`${r.name}: ${format(r.v)}`} onPointerMove={show} onFocus={show} onBlur={() => setTip(null)} />
            </g>
          );
        })}
      </svg>
      <TipBox tip={tip} width={W} />
    </div>
  );
}
