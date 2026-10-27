/*
 * Two small single-series charts for Reports. Following the dataviz rules: bars capped at
 * 24px with a 4px rounded data-end and a square baseline, recessive hairline grid, no
 * legend for one series (the title names it), hover and focus tooltips on every bar, and a
 * table view so no value is gated behind the hover.
 */
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { fmt } from './shared';

type Tip = { x: number; y: number; label: string; value: number } | null;

/** Draw at the container's real pixel width so type and marks keep their specified sizes. */
function useWidth(fallback = 640) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

function TableView({ rows, valueName }: { rows: [string, number][]; valueName: string }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Item</th>
            <th scope="col" className="num">
              {valueName}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}>
              <td>{k}</td>
              <td className="num">{fmt(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ChartCard({
  title,
  sub,
  rows,
  valueName,
  children,
}: {
  title: string;
  sub: string;
  rows: [string, number][];
  valueName: string;
  children: ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <section className="card card-pad">
      <div className="chart-head">
        <div>
          <h2>{title}</h2>
          <p>{sub}</p>
        </div>
        <div className="seg" role="group" aria-label={`${title} view`}>
          <button aria-pressed={!asTable} onClick={() => setAsTable(false)}>
            Chart
          </button>
          <button aria-pressed={asTable} onClick={() => setAsTable(true)}>
            Table
          </button>
        </div>
      </div>
      {asTable ? <TableView rows={rows} valueName={valueName} /> : children}
    </section>
  );
}

/** Rounded top, square baseline. */
function columnPath(x: number, y: number, w: number, h: number, r = 4) {
  const rr = Math.min(r, h, w / 2);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
}

/** Rounded right end, square at the left baseline. */
function barPath(x: number, y: number, w: number, h: number, r = 4) {
  const rr = Math.min(r, w, h / 2);
  return `M${x},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h - rr}Q${x + w},${y + h} ${x + w - rr},${y + h}H${x}Z`;
}

/** Smallest clean ceiling (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8 × 10ⁿ) at or above the peak. */
const niceMax = (v: number) => {
  const mag = Math.pow(10, Math.floor(Math.log10(v)));
  const step = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find((m) => m * mag >= v)!;
  return step * mag;
};

export function ColumnChart({ rows, valueName }: { rows: [string, number][]; valueName: string }) {
  const [tip, setTip] = useState<Tip>(null);
  const [ref, W] = useWidth();
  const H = 240;
  const pad = { l: 36, r: 8, t: 12, b: 26 };
  const max = niceMax(Math.max(...rows.map((r) => r[1])));
  const band = (W - pad.l - pad.r) / rows.length;
  const bw = Math.min(24, band - 6);
  const y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const ticks = [0, max / 2, max];

  return (
    <div className="chart" ref={ref} onPointerLeave={() => setTip(null)}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${valueName} by day, last ${rows.length} days`}>
        <g className="grid">
          {ticks.map((t) => (
            <line key={t} x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} />
          ))}
        </g>
        <g className="axis">
          {ticks.map((t) => (
            <text key={t} x={pad.l - 8} y={y(t) + 4} textAnchor="end">
              {fmt(t)}
            </text>
          ))}
          {rows.map(([k], i) =>
            i % 2 === 0 || rows.length < 9 ? (
              <text key={k} x={pad.l + band * i + band / 2} y={H - 6} textAnchor="middle">
                {k}
              </text>
            ) : null,
          )}
        </g>
        {rows.map(([k, v], i) => {
          const x = pad.l + band * i + (band - bw) / 2;
          const show = () => setTip({ x: ((x + bw / 2) / W) * 100, y: (y(v) / H) * 100, label: k, value: v });
          return (
            <g key={k}>
              <rect
                className="hit"
                x={pad.l + band * i}
                y={pad.t}
                width={band}
                height={H - pad.t - pad.b}
                tabIndex={0}
                aria-label={`${k}: ${fmt(v)} ${valueName.toLowerCase()}`}
                onPointerMove={show}
                onFocus={show}
                onBlur={() => setTip(null)}
              />
              <path className="mark" d={columnPath(x, y(v), bw, y(0) - y(v))} pointerEvents="none" />
            </g>
          );
        })}
      </svg>
      {tip ? (
        <div className="tip" style={{ left: `${tip.x}%`, top: `${tip.y}%` }}>
          <b>{fmt(tip.value)}</b>
          {tip.label}
        </div>
      ) : null}
    </div>
  );
}

export function BarChart({ rows, valueName }: { rows: [string, number][]; valueName: string }) {
  const [tip, setTip] = useState<Tip>(null);
  const [ref, W] = useWidth();
  const row = 34;
  const labelW = 128;
  const H = rows.length * row + 8;
  const max = Math.max(...rows.map((r) => r[1]));
  const span = Math.min(W - labelW - 48, 560);

  return (
    <div className="chart" ref={ref} onPointerLeave={() => setTip(null)}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${valueName} by class`}>
        <line x1={labelW} x2={labelW} y1={0} y2={H} stroke="var(--rule)" />
        {rows.map(([k, v], i) => {
          const w = (v / max) * span;
          const yy = i * row + (row - 18) / 2 + 4;
          const show = () => setTip({ x: ((labelW + w / 2) / W) * 100, y: (yy / H) * 100, label: k, value: v });
          return (
            <g key={k}>
              <text className="axis" x={labelW - 10} y={yy + 13} textAnchor="end" style={{ font: '500 12px var(--sans)', fill: 'var(--ink2)' }}>
                {k}
              </text>
              <rect
                className="hit"
                x={0}
                y={i * row + 2}
                width={W}
                height={row}
                tabIndex={0}
                aria-label={`${k}: ${v} ${valueName.toLowerCase()}`}
                onPointerMove={show}
                onFocus={show}
                onBlur={() => setTip(null)}
              />
              <path className="mark" d={barPath(labelW, yy, Math.max(w, 2), 18)} pointerEvents="none" />
              <g className="value">
                <text x={labelW + w + 8} y={yy + 13}>
                  {v}
                </text>
              </g>
            </g>
          );
        })}
      </svg>
      {tip ? (
        <div className="tip" style={{ left: `${tip.x}%`, top: `${tip.y}%` }}>
          <b>{fmt(tip.value)}</b>
          {tip.label}
        </div>
      ) : null}
    </div>
  );
}
