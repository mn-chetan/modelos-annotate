/*
 * The Overview's charts, shared by all three directions so they compare on composition,
 * not on content. Built to the dataviz specs: bars ≤ 24px with 4px rounded data-ends and
 * square baselines, 2px surface gaps, hairline solid grids, a legend whenever two or more
 * series share a plot, text in ink tokens (never the series colour), hover and focus
 * tooltips on every mark, and a table twin for every figure.
 */
import { useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react';
import { ObjectCrop } from '../../src/showcase/specimens';
import {
  BAND_RAMP,
  SENT_BACK,
  STATE_COLOR,
  STATE_NAME,
  STATE_ORDER,
  ahtText,
  fmt,
  hoursText,
  itemId,
  longDate,
  pctText,
  routeAt,
  type ItemState,
  type Overview,
  type Sample,
} from './model';

/* ---------- Plumbing ---------- */

export function useWidth(fallback = 640) {
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

type TipState = { x: number; y: number; value: ReactNode; label: ReactNode; rows?: [string, string, string?][] } | null;

/** Values lead, labels follow; rows are keyed with a short stroke of the series colour. */
function Tip({ tip, width }: { tip: TipState; width: number }) {
  if (!tip) return null;
  const edge = tip.x < 90 ? 'is-left' : tip.x > width - 90 ? 'is-right' : '';
  return (
    <div className={`ov-tip ${edge}`} style={{ left: tip.x, top: tip.y }} role="status">
      <b>{tip.value}</b>
      <span>{tip.label}</span>
      {tip.rows?.map(([k, v, c]) => (
        <span key={k} className="ov-tip-row">
          {c ? <i style={{ background: c }} /> : null}
          {k}
          <em>{v}</em>
        </span>
      ))}
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

/* ---------- Figure: title, optional legend, chart or table ---------- */

export type TableSpec = { cols: string[]; rows: (string | number)[][]; numeric?: number[] };

export function Figure({
  title,
  sub,
  legend,
  table,
  children,
  className = '',
  headExtra,
}: {
  title: ReactNode;
  sub?: ReactNode;
  legend?: ReactNode;
  table?: TableSpec;
  children: ReactNode;
  className?: string;
  headExtra?: ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <figure className={`ov-fig ${className}`}>
      <figcaption className="ov-fig-head">
        <div>
          <h3 className="ov-fig-title">{title}</h3>
          {sub ? <p className="ov-fig-sub">{sub}</p> : null}
        </div>
        <div className="ov-fig-tools">
          {headExtra}
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
        </div>
      </figcaption>
      {legend && !asTable ? <div className="ov-legend">{legend}</div> : null}
      {asTable && table ? <DataTable spec={table} /> : children}
    </figure>
  );
}

export function DataTable({ spec }: { spec: TableSpec }) {
  const num = new Set(spec.numeric ?? spec.cols.map((_, i) => i).slice(1));
  return (
    <div className="ov-table-wrap">
      <table className="ov-table">
        <thead>
          <tr>
            {spec.cols.map((c, i) => (
              <th key={c} scope="col" className={num.has(i) ? 'num' : undefined}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {spec.rows.map((r, ri) => (
            <tr key={ri}>
              {r.map((v, i) => (
                <td key={i} className={num.has(i) ? 'num' : undefined}>
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

export function Key({ color, kind = 'rect', children }: { color: string; kind?: 'rect' | 'line' | 'hollow'; children: ReactNode }) {
  return (
    <span className="ov-key">
      <i className={`is-${kind}`} style={kind === 'hollow' ? undefined : { background: color }} aria-hidden />
      {children}
    </span>
  );
}

type Names = Partial<Record<ItemState, string>>;
const nameOf = (s: ItemState, names?: Names) => names?.[s] ?? STATE_NAME[s];

export function StateKeys({ o, counts = true, names }: { o: Overview; counts?: boolean; names?: Names }) {
  return (
    <>
      {STATE_ORDER.filter((s) => o.states[s] > 0).map((s) => (
        <Key key={s} color={STATE_COLOR[s]} kind={s === 'queued' ? 'hollow' : 'rect'}>
          {nameOf(s, names)}
          {counts ? <b>{fmt(o.states[s])}</b> : null}
        </Key>
      ))}
      {o.sentBack ? (
        <Key color={SENT_BACK}>
          Sent back by QC<b>{fmt(o.sentBack)}</b>
        </Key>
      ) : null}
    </>
  );
}

export const stateTable = (o: Overview, names?: Names): TableSpec => ({
  cols: ['State', o.unit[0].toUpperCase() + o.unit.slice(1), 'Share'],
  rows: [
    ...STATE_ORDER.filter((s) => !names || o.states[s] > 0).map((s) => [nameOf(s, names), o.states[s], pctText(o.states[s] / o.assets, 1)]),
    ...(o.sentBack ? [['of which sent back by QC', o.sentBack, pctText(o.sentBack / o.assets, 1)]] : []),
  ],
});

/* ---------- State bar: where every item is right now ---------- */

export function StateBar({
  o,
  height = 14,
  selected,
  onSelect,
  names,
}: {
  o: Overview;
  height?: number;
  selected?: ItemState | null;
  onSelect?: (s: ItemState | null) => void;
  names?: Names;
}) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<TipState>(null);
  const gap = 2;
  const segs = STATE_ORDER.filter((s) => o.states[s] > 0);
  const usable = W - gap * (segs.length - 1);
  let x = 0;
  return (
    <div className="ov-chart" ref={ref} onPointerLeave={() => setTip(null)}>
      <svg width={W} height={height} role="img" aria-label={segs.map((s) => `${nameOf(s, names)} ${fmt(o.states[s])}`).join(', ')}>
        {segs.map((s, i) => {
          const w = Math.max(3, (o.states[s] / o.assets) * usable);
          const x0 = x;
          x += w + gap;
          const first = i === 0;
          const last = i === segs.length - 1;
          const r = Math.min(4, w / 2);
          const d = `M${x0 + (first ? r : 0)},0H${x0 + w - (last ? r : 0)}${last ? `Q${x0 + w},0 ${x0 + w},${r}V${height - r}Q${x0 + w},${height} ${x0 + w - r},${height}` : `V${height}`}H${x0 + (first ? r : 0)}${first ? `Q${x0},${height} ${x0},${height - r}V${r}Q${x0},0 ${x0 + r},0` : `V0`}Z`;
          const dim = selected && selected !== s;
          const show = () =>
            setTip({ x: x0 + w / 2, y: 0, value: fmt(o.states[s]), label: `${nameOf(s, names)} · ${pctText(o.states[s] / o.assets, 1)}` });
          return (
            <g key={s} opacity={dim ? 0.25 : 1}>
              <path
                d={d}
                fill={s === 'queued' ? 'var(--surface)' : STATE_COLOR[s]}
                stroke={s === 'queued' ? 'var(--rule-strong)' : 'none'}
                strokeWidth={s === 'queued' ? 1 : 0}
              />
              <rect
                className="ov-hit"
                x={x0}
                y={-6}
                width={w}
                height={height + 12}
                tabIndex={0}
                role={onSelect ? 'button' : undefined}
                aria-label={`${nameOf(s, names)}: ${fmt(o.states[s])}`}
                onPointerMove={show}
                onFocus={show}
                onBlur={() => setTip(null)}
                onClick={() => onSelect?.(selected === s ? null : s)}
                style={{ cursor: onSelect ? 'pointer' : undefined }}
              />
            </g>
          );
        })}
      </svg>
      <Tip tip={tip} width={W} />
    </div>
  );
}

/* ---------- Throughput: approved per day against the plan ---------- */

export function Throughput({ o, span = 28, height = 220 }: { o: Overview; span?: number; height?: number }) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<TipState>(null);
  const [hover, setHover] = useState<number | null>(null);
  const days = o.days.slice(-span);
  const pad = { l: 36, r: 64, t: 14, b: 26 };
  const max = niceMax(Math.max(o.planned * 1.15, ...days.map((d) => d.approved)));
  const band = (W - pad.l - pad.r) / days.length;
  const bw = Math.max(3, Math.min(24, band - 2));
  const y = (v: number) => pad.t + (height - pad.t - pad.b) * (1 - v / max);
  const ticks = [0, max / 2, max];
  const every = [1, 2, 7].find((k) => band * k >= 46) ?? 7;

  return (
    <div className="ov-chart" ref={ref} onPointerLeave={() => (setTip(null), setHover(null))}>
      <svg width={W} height={height} role="img" aria-label={`${o.unit} approved per day over the last ${days.length} days, against a plan of ${o.planned} per working day`}>
        <defs>
          <pattern id="ov-today" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="5" height="5" fill="#C9D4F2" />
            <line x1="0" y1="0" x2="0" y2="5" stroke="var(--blue)" strokeWidth="2" />
          </pattern>
        </defs>
        <g className="ov-grid">
          {ticks.map((t) => (
            <line key={t} x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} />
          ))}
        </g>
        <g className="ov-axis">
          {ticks.map((t) => (
            <text key={t} x={pad.l - 8} y={y(t) + 4} textAnchor="end">
              {compact(t)}
            </text>
          ))}
          {days.map((d, i) =>
            (days.length - 1 - i) % every === 0 ? (
              <text key={i} x={pad.l + band * i + band / 2} y={height - 6} textAnchor="middle">
                {d.today ? 'Today' : d.label}
              </text>
            ) : null,
          )}
        </g>
        {days.map((d, i) => {
          const x = pad.l + band * i + (band - bw) / 2;
          const show = () => {
            setHover(i);
            setTip({
              x: x + bw / 2,
              y: y(Math.max(d.approved, o.planned)),
              value: fmt(d.approved),
              label: `${longDate(d.date)}${d.today ? ', so far' : d.weekend ? ', weekend' : ''}`,
              rows: d.weekend ? undefined : [['Plan', fmt(o.planned), 'var(--ink)']],
            });
          };
          return (
            <g key={i}>
              <path
                d={colPath(x, y(d.approved), bw, y(0) - y(d.approved))}
                fill={d.today ? 'url(#ov-today)' : d.weekend ? '#9AB0E6' : 'var(--blue)'}
                opacity={hover !== null && hover !== i ? 0.55 : 1}
              />
              <rect
                className="ov-hit"
                x={pad.l + band * i}
                y={pad.t}
                width={band}
                height={height - pad.t - pad.b}
                tabIndex={0}
                aria-label={`${longDate(d.date)}: ${fmt(d.approved)} approved`}
                onPointerMove={show}
                onFocus={show}
                onBlur={() => (setTip(null), setHover(null))}
              />
            </g>
          );
        })}
        {/* The plan: a solid ink rule, labelled at its end rather than in a legend box alone. */}
        <line x1={pad.l} x2={W - pad.r + 4} y1={y(o.planned)} y2={y(o.planned)} stroke="var(--ink)" strokeWidth={2} strokeLinecap="round" pointerEvents="none" />
        <g className="ov-endlabel" pointerEvents="none">
          <text x={W - pad.r + 10} y={y(o.planned) - 2}>
            Plan
          </text>
          <text x={W - pad.r + 10} y={y(o.planned) + 12} className="is-muted">
            {fmt(o.planned)}/day
          </text>
        </g>
      </svg>
      <Tip tip={tip} width={W} />
    </div>
  );
}

export const throughputTable = (o: Overview, span = 28): TableSpec => ({
  cols: ['Day', 'Approved', 'Plan'],
  rows: o.days.slice(-span).map((d) => [`${longDate(d.date)}${d.today ? ' (so far)' : ''}`, d.approved, d.weekend ? '—' : o.planned]),
});

export function ThroughputKeys() {
  return (
    <>
      <Key color="var(--blue)">Approved, working day</Key>
      <Key color="#9AB0E6">Weekend</Key>
      <Key color="var(--ink)" kind="line">
        Plan per working day
      </Key>
    </>
  );
}

/* ---------- Burn-up: cumulative approvals toward the whole project ---------- */

export function BurnUp({ o, height = 220 }: { o: Overview; height?: number }) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<TipState>(null);
  const days = o.days.slice(-28);
  const before = o.states.approved - days.reduce((s, d) => s + d.approved, 0);
  const cum = days.reduce<number[]>((acc, d) => (acc.push((acc.at(-1) ?? before) + d.approved), acc), []);
  // Projection at the recent working-day pace until the ETA (or the due date).
  const proj: { t: number; v: number }[] = [];
  const end = o.eta ?? o.due;
  const DAY = 86_400_000;
  const extra = Math.max(0, Math.round((Math.max(end.getTime(), o.due.getTime()) - days.at(-1)!.date.getTime()) / DAY));
  let v = cum.at(-1)!;
  for (let k = 1; k <= extra; k++) {
    const dow = new Date(days.at(-1)!.date.getTime() + k * DAY).getDay();
    if (dow !== 0 && dow !== 6) v = Math.min(o.assets, v + o.perWorkingDay);
    proj.push({ t: days.length - 1 + k, v });
  }
  const n = days.length + extra;
  const pad = { l: 44, r: 16, t: 18, b: 26 };
  const x = (i: number) => pad.l + ((W - pad.l - pad.r) * i) / Math.max(1, n - 1);
  const max = o.assets * 1.1;
  const y = (val: number) => pad.t + (height - pad.t - pad.b) * (1 - val / max);
  const dueIdx = days.length - 1 + Math.round((o.due.getTime() - days.at(-1)!.date.getTime()) / DAY);
  const line = cum.map((c, i) => `${i ? 'L' : 'M'}${x(i)},${y(c)}`).join('');
  const pline = proj.length ? `M${x(days.length - 1)},${y(cum.at(-1)!)}` + proj.map((p) => `L${x(p.t)},${y(p.v)}`).join('') : '';

  const onMove = (e: PointerEvent<SVGRectElement>) => {
    const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
    const i = Math.round(((e.clientX - r.left - pad.l) / (W - pad.l - pad.r)) * (n - 1));
    if (i < 0 || i >= n) return;
    if (i < days.length) setTip({ x: x(i), y: y(cum[i]), value: fmt(cum[i]), label: `approved by ${longDate(days[i].date)}` });
    else {
      const p = proj[i - days.length];
      setTip({ x: x(i), y: y(p.v), value: fmt(p.v), label: `projected by ${longDate(new Date(days.at(-1)!.date.getTime() + (i - days.length + 1) * DAY))}` });
    }
  };

  return (
    <div className="ov-chart" ref={ref} onPointerLeave={() => setTip(null)}>
      <svg width={W} height={height} role="img" aria-label={`Approved so far, ${fmt(cum.at(-1)!)} of ${fmt(o.assets)}, with a projection at the recent pace`}>
        <g className="ov-grid">
          {[0, Math.round(o.assets / 2)].map((t) => (
            <line key={t} x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} />
          ))}
        </g>
        <g className="ov-axis">
          {[0, Math.round(o.assets / 2), o.assets].map((t) => (
            <text key={t} x={pad.l - 8} y={y(t) + 4} textAnchor="end">
              {compact(t)}
            </text>
          ))}
          <text x={x(0)} y={height - 6}>
            {days[0].label}
          </text>
          <text x={x(days.length - 1)} y={height - 6} textAnchor="middle">
            Today
          </text>
        </g>
        {/* The whole project: the ceiling every line is climbing toward. */}
        <line x1={pad.l} x2={W - pad.r} y1={y(o.assets)} y2={y(o.assets)} stroke="var(--ink)" strokeWidth={1} />
        <text className="ov-anno" x={pad.l + 2} y={y(o.assets) - 6}>
          All {fmt(o.assets)} {o.unit}
        </text>
        {dueIdx < n ? (
          <g>
            <line x1={x(dueIdx)} x2={x(dueIdx)} y1={pad.t} y2={height - pad.b} stroke="var(--rule-strong)" />
            <text className="ov-anno" x={x(dueIdx) - 4} y={height - pad.b - 6} textAnchor="end">
              Due {o.due.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
            </text>
          </g>
        ) : null}
        <path d={`${line}L${x(cum.length - 1)},${y(0)}L${x(0)},${y(0)}Z`} fill="var(--blue)" opacity={0.1} />
        <path d={line} fill="none" stroke="var(--blue)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {pline ? <path d={pline} fill="none" stroke="var(--blue)" strokeWidth={2} strokeDasharray="2 5" strokeLinecap="round" /> : null}
        <circle cx={x(days.length - 1)} cy={y(cum.at(-1)!)} r={5} fill="var(--blue)" stroke="var(--surface)" strokeWidth={2} />
        {o.eta ? <circle cx={x(n - 1 - Math.max(0, Math.round((Math.max(o.eta.getTime(), o.due.getTime()) - o.eta.getTime()) / DAY)))} cy={y(o.assets)} r={4} fill="var(--surface)" stroke="var(--blue)" strokeWidth={2} /> : null}
        <rect className="ov-hit" x={pad.l} y={pad.t} width={W - pad.l - pad.r} height={height - pad.t - pad.b} onPointerMove={onMove} />
      </svg>
      <Tip tip={tip} width={W} />
    </div>
  );
}

/* ---------- Routing: the confidence threshold governor ---------- */

const ROUTE_COLOR = { audit: SENT_BACK, review: STATE_COLOR.review, auto: '#2A57C0' } as const;
export const PRESETS = [0.85, 0.9, 0.95];

/** Two lines by default; pass lo = 0.4 for a single auto-accept line with no audit band. */
export function useThresholds(lo0 = 0.7, hi0 = 0.95) {
  const [lo, setLo] = useState(lo0);
  const [hi, setHi] = useState(hi0);
  return { lo, hi, setLo, setHi, lo0, hi0 };
}

export function RoutingKeys({ single = false }: { single?: boolean }) {
  return (
    <>
      <Key color={ROUTE_COLOR.auto}>Approved by AI</Key>
      <Key color={ROUTE_COLOR.review}>Sent to human review</Key>
      {single ? null : <Key color={ROUTE_COLOR.audit}>Reviewed, then audited</Key>}
    </>
  );
}

export function Routing({
  o,
  t,
  height = 190,
  presets = true,
}: {
  o: Overview;
  t: ReturnType<typeof useThresholds>;
  height?: number;
  presets?: boolean;
}) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<TipState>(null);
  const drag = useRef<'lo' | 'hi' | null>(null);
  const pad = { l: 36, r: 12, t: 46, b: 26 };
  const bins = o.bins;
  const band = (W - pad.l - pad.r) / bins.length;
  const bw = band - 2;
  // Auto-accepted bins can dwarf the review band, which is the point of the chart; when
  // they do, break the axis and print their true counts above the break.
  const peak = Math.max(...bins.map((b) => b.n));
  const body = Math.max(1, ...bins.filter((b) => b.hi <= 0.95 + 1e-9).map((b) => b.n));
  const broken = peak > body * 3;
  const max = broken ? niceMax(body * 2.2) : niceMax(peak);
  const tall = bins.filter((b) => b.n > max);
  const roomy = band >= 34;
  const y = (v: number) => pad.t + (height - pad.t - pad.b) * (1 - v / max);
  const xAt = (v: number) => pad.l + ((v - 0.4) / 0.6) * (W - pad.l - pad.r);
  const snap = (v: number) => Math.round(Math.min(1, Math.max(0.4, v)) / 0.025) * 0.025;

  const set = (which: 'lo' | 'hi', v: number) => {
    const s = +snap(v).toFixed(3);
    if (which === 'lo') t.setLo(Math.min(Math.max(0.5, s), +(t.hi - 0.05).toFixed(3)));
    else t.setHi(Math.max(Math.min(0.975, s), +(t.lo + 0.05).toFixed(3)));
  };
  const fromPointer = (e: PointerEvent<SVGElement>) => {
    const r = (e.currentTarget.ownerSVGElement ?? (e.currentTarget as SVGSVGElement)).getBoundingClientRect();
    return 0.4 + ((e.clientX - r.left - pad.l) / (W - pad.l - pad.r)) * 0.6;
  };
  const onKey = (which: 'lo' | 'hi') => (e: KeyboardEvent) => {
    const cur = which === 'lo' ? t.lo : t.hi;
    const step = e.key === 'ArrowRight' || e.key === 'ArrowUp' ? 0.025 : e.key === 'ArrowLeft' || e.key === 'ArrowDown' ? -0.025 : 0;
    if (step) {
      e.preventDefault();
      set(which, cur + step);
    }
  };

  const handle = (which: 'lo' | 'hi') => {
    const v = which === 'lo' ? t.lo : t.hi;
    const hx = xAt(v);
    return (
      <g
        className="ov-handle"
        transform={`translate(${hx},0)`}
        tabIndex={0}
        role="slider"
        aria-label={which === 'lo' ? 'Audit below this confidence' : 'AI approves at or above this confidence'}
        aria-valuemin={which === 'lo' ? 0.5 : t.lo + 0.05}
        aria-valuemax={which === 'lo' ? t.hi - 0.05 : 0.975}
        aria-valuenow={v}
        aria-valuetext={v.toFixed(3).replace(/0$/, '')}
        onKeyDown={onKey(which)}
        onPointerDown={(e) => {
          drag.current = which;
          (e.currentTarget as SVGGElement).setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => drag.current === which && set(which, fromPointer(e))}
        onPointerUp={() => (drag.current = null)}
      >
        <rect x={-12} y={0} width={24} height={height - pad.b} fill="transparent" />
        <line y1={20} y2={height - pad.b} stroke="var(--ink)" strokeWidth={2} />
        <rect className="ov-handle-knob" x={-19} y={1} width={38} height={20} rx={10} />
        <text y={15} textAnchor="middle">
          {v.toFixed(3).replace(/0$/, '')}
        </text>
      </g>
    );
  };

  const r = routeAt(o, t.lo, t.hi);
  return (
    <div className="ov-routing">
      <div className="ov-chart" ref={ref} onPointerLeave={() => setTip(null)}>
        <svg width={W} height={height} role="group" aria-label={`Items by AI confidence, with the two routing thresholds${broken ? '; the tallest bars are cut, with their counts printed above' : ''}`}>
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
            {[0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1].map((v) => (
              <text key={v} x={xAt(v)} y={height - 6} textAnchor="middle">
                {v.toFixed(1)}
              </text>
            ))}
          </g>
          {bins.map((b, i) => {
            const route = b.lo >= t.hi - 1e-9 ? 'auto' : b.hi <= t.lo + 1e-9 ? 'audit' : 'review';
            const x = pad.l + band * i + 1;
            const show = () =>
              setTip({
                x: x + bw / 2,
                y: y(b.n),
                value: `${fmt(b.n)} ${o.unit}`,
                label: `Confidence ${b.lo.toFixed(3)} to ${b.hi.toFixed(3)} · ${route === 'auto' ? 'approved by AI' : route === 'audit' ? 'reviewed, then audited' : 'sent to human review'}`,
              });
            const over = b.n > max;
            const top = y(Math.min(b.n, max));
            const brk = y(max * 0.78);
            return (
              <g key={i}>
                <path d={colPath(x, top, bw, y(0) - top, 3)} fill={ROUTE_COLOR[route]} />
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
            <text className="ov-overflow" x={Math.min(pad.l + band * bins.indexOf(tall[0]), xAt(t.hi)) - 10} y={pad.t + 4} textAnchor="end">
              {tall.map((b) => compact(b.n)).join(' · ')} above the cut
            </text>
          ) : null}
          {t.lo0 <= 0.4 ? null : handle('lo')}
          {handle('hi')}
        </svg>
        <Tip tip={tip} width={W} />
      </div>
      {presets ? (
        <div className="ov-presets">
          <span>AI approves at</span>
          {PRESETS.map((v) => (
            <button key={v} aria-pressed={Math.abs(t.hi - v) < 1e-6} onClick={() => t.setHi(v)}>
              {v.toFixed(2)}
            </button>
          ))}
          <button className="ov-reset" onClick={() => (t.setLo(t.lo0), t.setHi(t.hi0))} disabled={t.lo === t.lo0 && t.hi === t.hi0}>
            Reset
          </button>
          <span className="ov-presets-note">{t.lo0 <= 0.4 ? 'Drag the line' : 'Drag either line'}, or focus it and use the arrow keys.</span>
        </div>
      ) : null}
      <span className="sr-only" aria-live="polite">
        {`${pctText(r.share)} of ${o.unit} go to people.`}
      </span>
    </div>
  );
}

export const routingTable = (o: Overview, lo: number, hi: number): TableSpec => {
  const r = routeAt(o, lo, hi);
  const single = lo <= 0.4;
  return {
    cols: ['Route', o.unit[0].toUpperCase() + o.unit.slice(1), 'Share'],
    rows: [
      [`Approved by AI (≥ ${hi})`, r.auto, pctText(r.auto / o.drafted)],
      [single ? `Sent to human review (< ${hi})` : `Sent to human review (${lo} to ${hi})`, r.review, pctText(r.review / o.drafted)],
      ...(single ? [] : [[`Reviewed, then audited (< ${lo})`, r.audit, pctText(r.audit / o.drafted)]]),
    ],
  };
};

/* ---------- Field: every item, one square each ---------- */

export function Field({
  o,
  cell = 10,
  highlight,
  onPick,
  maxHeight,
}: {
  o: Overview;
  cell?: number;
  highlight?: ItemState | 'back' | null;
  onPick?: (i: number) => void;
  maxHeight?: number;
}) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<TipState>(null);
  const [hover, setHover] = useState<number | null>(null);
  const n = o.field.length;
  // Grow the cell for small projects so 48 clips still read as a field, not a speck.
  let s = n < 120 ? Math.min(34, Math.floor(Math.sqrt((W * 140) / n)) - 2) : cell;
  const g = s >= 18 ? 4 : 2;
  let cols = Math.max(8, Math.floor((W + g) / (s + g)));
  if (maxHeight) {
    while (Math.ceil(n / cols) * (s + g) > maxHeight && s > 5) {
      s -= 1;
      cols = Math.max(8, Math.floor((W + g) / (s + g)));
    }
  }
  const rows = Math.ceil(n / cols);
  const H = rows * (s + g) - g;

  const at = (e: { currentTarget: SVGSVGElement; clientX: number; clientY: number }) => {
    const r = e.currentTarget.getBoundingClientRect();
    const c = Math.floor((e.clientX - r.left) / (s + g));
    const rr = Math.floor((e.clientY - r.top) / (s + g));
    const i = rr * cols + c;
    return c >= 0 && c < cols && i >= 0 && i < n ? i : -1;
  };
  const describe = (i: number) => {
    const f = o.field[i];
    const state = f.back ? 'Sent back by QC' : STATE_NAME[f.state];
    return {
      x: (i % cols) * (s + g) + s / 2,
      y: Math.floor(i / cols) * (s + g),
      value: itemId(o, i),
      label: f.state === 'queued' ? state : `${state} · AI confidence ${f.conf.toFixed(2)}`,
    };
  };

  return (
    <div className="ov-chart ov-field" ref={ref} onPointerLeave={() => (setTip(null), setHover(null))}>
      <svg
        width={W}
        height={H}
        role="img"
        aria-label={`Every ${o.unitOne}${o.unitPerSquare > 1 ? ` (one square per ${o.unitPerSquare})` : ''} by state: ${STATE_ORDER.map((st) => `${STATE_NAME[st]} ${fmt(o.states[st])}`).join(', ')}`}
        onPointerMove={(e) => {
          const i = at(e);
          setHover(i >= 0 ? i : null);
          setTip(i >= 0 ? describe(i) : null);
        }}
        onClick={(e) => {
          const i = at(e);
          if (i >= 0) onPick?.(i);
        }}
        style={{ cursor: onPick ? 'pointer' : undefined }}
      >
        {o.field.map((f, i) => {
          const x = (i % cols) * (s + g);
          const yy = Math.floor(i / cols) * (s + g);
          const match = !highlight || (highlight === 'back' ? f.back : f.state === highlight);
          const fill = f.back ? SENT_BACK : STATE_COLOR[f.state];
          const r = Math.min(3, s / 4);
          return f.state === 'queued' ? (
            <rect key={i} x={x + 0.5} y={yy + 0.5} width={s - 1} height={s - 1} rx={r} fill="none" stroke="var(--rule-strong)" opacity={match ? 1 : 0.3} />
          ) : (
            <rect key={i} x={x} y={yy} width={s} height={s} rx={r} fill={fill} opacity={match ? (hover === i ? 0.7 : 1) : 0.14} />
          );
        })}
        {hover !== null ? (
          <rect
            x={(hover % cols) * (s + g) - 2}
            y={Math.floor(hover / cols) * (s + g) - 2}
            width={s + 4}
            height={s + 4}
            rx={4}
            fill="none"
            stroke="var(--ink)"
            strokeWidth={1.5}
            pointerEvents="none"
          />
        ) : null}
      </svg>
      <Tip tip={tip} width={W} />
    </div>
  );
}

/* ---------- Flow: how items move from intake to approval ---------- */

type FlowNode = { id: string; col: number; label: string; n: number; color?: string; hollow?: boolean; state?: ItemState };
type FlowLink = { from: string; to: string; n: number; color?: string };

/** AI's own path is blue, people's is review yellow; approvals stay green. Validated together. */
export const AI_COLOR = ROUTE_COLOR.auto;

/**
 * `split` divides the approvals by who decided: the AI alone (blue) or a person (green),
 * and names the steps for an AI-versus-people reading.
 */
export function flowModel(o: Overview, split = false) {
  if (split) {
    const nodes: FlowNode[] = [
      { id: 'in', col: 0, label: `Total ${o.unit}`, n: o.assets },
      { id: 'drafted', col: 1, label: 'Annotated by AI', n: o.drafted, color: AI_COLOR },
      { id: 'q1', col: 1, label: 'Not annotated yet', n: o.states.queued, hollow: true, state: 'queued' as const },
      { id: 'auto', col: 2, label: 'No review needed', n: o.autoAccepted, color: AI_COLOR },
      { id: 'people', col: 2, label: 'Sent to human review', n: o.toPeople, color: STATE_COLOR.review },
      { id: 'q2', col: 2, label: 'Not annotated yet', n: o.states.queued, hollow: true, state: 'queued' as const },
      { id: 'aiOk', col: 3, label: 'Approved by AI', n: o.approvedAuto, color: AI_COLOR },
      { id: 'humanOk', col: 3, label: 'Approved by reviewers', n: o.approvedHuman, color: STATE_COLOR.approved, state: 'approved' as const },
      { id: 'review', col: 3, label: 'In human review', n: o.states.review + o.states.qc, color: STATE_COLOR.review, state: 'review' as const },
      { id: 'q3', col: 3, label: 'Not annotated yet', n: o.states.queued, hollow: true, state: 'queued' as const },
    ].filter((nd) => nd.n > 0);
    const links: FlowLink[] = [
      { from: 'in', to: 'drafted', n: o.drafted },
      { from: 'in', to: 'q1', n: o.states.queued },
      { from: 'drafted', to: 'auto', n: o.autoAccepted, color: AI_COLOR },
      { from: 'drafted', to: 'people', n: o.toPeople, color: STATE_COLOR.review },
      { from: 'q1', to: 'q2', n: o.states.queued },
      { from: 'auto', to: 'aiOk', n: o.approvedAuto, color: AI_COLOR },
      { from: 'people', to: 'humanOk', n: o.approvedHuman, color: STATE_COLOR.approved },
      { from: 'people', to: 'review', n: o.states.review + o.states.qc, color: STATE_COLOR.review },
      { from: 'q2', to: 'q3', n: o.states.queued },
    ].filter((l) => l.n > 0);
    return { nodes, links };
  }
  const nodes = (
    [
    { id: 'in', col: 0, label: 'In the project', n: o.assets },
    { id: 'drafted', col: 1, label: 'Drafted by AI', n: o.drafted },
    { id: 'q1', col: 1, label: 'Waiting for AI', n: o.states.queued, hollow: true, state: 'queued' },
    { id: 'auto', col: 2, label: 'Accepted automatically', n: o.autoAccepted },
    { id: 'people', col: 2, label: 'Sent to people', n: o.toPeople },
    { id: 'q2', col: 2, label: 'Waiting for AI', n: o.states.queued, hollow: true, state: 'queued' },
    { id: 'approved', col: 3, label: 'Approved', n: o.states.approved, color: STATE_COLOR.approved, state: 'approved' },
    { id: 'qc', col: 3, label: 'In quality check', n: o.states.qc, color: STATE_COLOR.qc, state: 'qc' },
    { id: 'review', col: 3, label: 'Waiting for review', n: o.states.review, color: STATE_COLOR.review, state: 'review' },
    { id: 'q3', col: 3, label: 'Waiting for AI', n: o.states.queued, hollow: true, state: 'queued' },
    ] satisfies FlowNode[]
  ).filter((nd) => nd.n > 0) as FlowNode[];
  const links: FlowLink[] = [
    { from: 'in', to: 'drafted', n: o.drafted },
    { from: 'in', to: 'q1', n: o.states.queued },
    { from: 'drafted', to: 'auto', n: o.autoAccepted },
    { from: 'drafted', to: 'people', n: o.toPeople },
    { from: 'q1', to: 'q2', n: o.states.queued },
    { from: 'auto', to: 'approved', n: o.approvedAuto, color: STATE_COLOR.approved },
    { from: 'people', to: 'approved', n: o.approvedHuman, color: STATE_COLOR.approved },
    { from: 'people', to: 'qc', n: o.states.qc, color: STATE_COLOR.qc },
    { from: 'people', to: 'review', n: o.states.review, color: STATE_COLOR.review },
    { from: 'q2', to: 'q3', n: o.states.queued },
  ].filter((l) => l.n > 0);
  return { nodes, links };
}

export function Flow({
  o,
  height = 300,
  selected,
  onSelect,
  split = false,
}: {
  o: Overview;
  height?: number;
  selected?: string | null;
  onSelect?: (id: string | null) => void;
  split?: boolean;
}) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<TipState>(null);
  const { nodes, links } = useMemo(() => flowModel(o, split), [o, split]);
  const narrow = W < 600;
  const labelW = narrow ? 0 : split ? 210 : 168;
  const nodeW = 10;
  const gap = 18;
  const cols = 4;
  const colX = (c: number) => (c * (W - labelW - nodeW)) / (cols - 1);
  const maxNodes = Math.max(...[0, 1, 2, 3].map((c) => nodes.filter((nd) => nd.col === c).length));
  const k = (height - gap * (maxNodes - 1)) / o.assets;

  // Lay out each column top-down, centred on the tallest column.
  const pos = new Map<string, { x: number; y: number; h: number }>();
  for (let c = 0; c < cols; c++) {
    const col = nodes.filter((nd) => nd.col === c);
    const total = col.reduce((s, nd) => s + Math.max(2, nd.n * k), 0) + gap * (col.length - 1);
    let yy = (height - total) / 2;
    for (const nd of col) {
      const h = Math.max(2, nd.n * k);
      pos.set(nd.id, { x: colX(c), y: yy, h });
      yy += h + gap;
    }
  }
  // Ribbon offsets inside each node, in link order.
  const outOff = new Map<string, number>();
  const inOff = new Map<string, number>();
  const ribbons = links.map((l) => {
    const a = pos.get(l.from)!;
    const b = pos.get(l.to)!;
    const h = Math.max(1, l.n * k);
    const y0 = a.y + (outOff.get(l.from) ?? 0);
    const y1 = b.y + (inOff.get(l.to) ?? 0);
    outOff.set(l.from, (outOff.get(l.from) ?? 0) + h);
    inOff.set(l.to, (inOff.get(l.to) ?? 0) + h);
    const x0 = a.x + nodeW;
    const x1 = b.x;
    const mx = (x0 + x1) / 2;
    const d = `M${x0},${y0}C${mx},${y0} ${mx},${y1} ${x1},${y1}L${x1},${y1 + h}C${mx},${y1 + h} ${mx},${y0 + h} ${x0},${y0 + h}Z`;
    return { ...l, d, mid: { x: mx, y: (y0 + y1) / 2 + h / 2 } };
  });
  const lit = (l: FlowLink) => !selected || l.from === selected || l.to === selected;
  const isQueued = (id: string) => id.startsWith('q');

  if (narrow) {
    // Phones: the same flow as a ledger, so nothing is squeezed into hairlines.
    return (
      <div className="ov-flow-list" ref={ref}>
        {nodes
          .filter((nd) => nd.id !== 'q1' && nd.id !== 'q2')
          .map((nd) => (
            <button key={nd.id} className="ov-flow-row" aria-pressed={selected === nd.id} onClick={() => onSelect?.(selected === nd.id ? null : nd.id)} style={{ paddingLeft: 8 + nd.col * 14 }}>
              <i style={{ background: nd.hollow ? 'transparent' : nd.color ?? 'var(--ink)' }} className={nd.hollow ? 'is-hollow' : ''} />
              <span>{nd.label}</span>
              <b>{fmt(nd.n)}</b>
            </button>
          ))}
      </div>
    );
  }

  return (
    <div className="ov-chart" ref={ref} onPointerLeave={() => setTip(null)}>
      <svg width={W} height={height} role="group" aria-label="How items move from intake to approval">
        {ribbons.map((l, i) => (
          <path
            key={i}
            d={l.d}
            fill={l.color ?? (isQueued(l.to) ? 'var(--rule-strong)' : 'var(--ink)')}
            opacity={lit(l) ? (l.color ? 0.26 : isQueued(l.to) ? 0.3 : 0.055) : 0.03}
            onPointerMove={() =>
              setTip({ x: l.mid.x, y: l.mid.y, value: fmt(l.n), label: `${nodes.find((n) => n.id === l.from)!.label} → ${nodes.find((n) => n.id === l.to)!.label}` })
            }
          />
        ))}
        {nodes.map((nd) => {
          const p = pos.get(nd.id)!;
          const on = selected === nd.id;
          const last = nd.col === cols - 1;
          return (
            <g
              key={nd.id}
              className="ov-flow-node"
              tabIndex={0}
              role="button"
              aria-pressed={on}
              aria-label={`${nd.label}: ${fmt(nd.n)}`}
              onClick={() => onSelect?.(on ? null : nd.id)}
              onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onSelect?.(on ? null : nd.id))}
            >
              <rect x={p.x - 4} y={p.y - 4} width={nodeW + 8} height={p.h + 8} fill="transparent" />
              {/* The label is part of the target, not just the bar. */}
              <rect x={p.x + nodeW} y={p.y + Math.min(p.h / 2, 18) - 11} width={(fmt(nd.n).length + nd.label.length) * 7.4 + 24} height={22} fill="transparent" />
              <rect
                x={p.x}
                y={p.y}
                width={nodeW}
                height={p.h}
                rx={3}
                fill={nd.hollow ? 'var(--surface)' : nd.color ?? 'var(--ink)'}
                stroke={nd.hollow ? 'var(--rule-strong)' : on ? 'var(--ink)' : 'none'}
                strokeWidth={on ? 2 : 1}
              />
              <text className="ov-flow-label" x={last ? p.x + nodeW + 10 : p.x + nodeW + 8} y={p.y + Math.min(p.h / 2, 18) + 4} paintOrder="stroke">
                <tspan className="ov-flow-n">{fmt(nd.n)}</tspan>
                <tspan dx={6}>{nd.label}</tspan>
              </text>
            </g>
          );
        })}
      </svg>
      <Tip tip={tip} width={W} />
    </div>
  );
}

export const flowTable = (o: Overview, split = false): TableSpec => {
  const m = flowModel(o, split);
  const nm = (id: string) => m.nodes.find((n) => n.id === id)!.label;
  return {
    cols: ['From', 'To', o.unit[0].toUpperCase() + o.unit.slice(1)],
    numeric: [2],
    rows: m.links.map((l) => [nm(l.from), nm(l.to), l.n]),
  };
};

/* ---------- Quality bands against QC ---------- */

export function Bands({ o, height = 12 }: { o: Overview; height?: number }) {
  const [ref, W] = useWidth();
  const [tip, setTip] = useState<TipState>(null);
  const gap = 2;
  const usable = W - gap * (o.bands.length - 1);
  let x = 0;
  return (
    <div>
      <div className="ov-chart" ref={ref} onPointerLeave={() => setTip(null)}>
        <svg width={W} height={height} role="img" aria-label={o.bands.map(([nm, v]) => `${nm} ${pctText(v)}`).join(', ')}>
          {o.bands.map(([nm, v], i) => {
            const w = v * usable;
            const x0 = x;
            x += w + gap;
            const r = Math.min(4, w / 2);
            const first = i === 0;
            const last = i === o.bands.length - 1;
            const d = `M${x0 + (first ? r : 0)},0H${x0 + w - (last ? r : 0)}${last ? `Q${x0 + w},0 ${x0 + w},${r}V${height - r}Q${x0 + w},${height} ${x0 + w - r},${height}` : `V${height}`}H${x0 + (first ? r : 0)}${first ? `Q${x0},${height} ${x0},${height - r}V${r}Q${x0},0 ${x0 + r},0` : 'V0'}Z`;
            const show = () => setTip({ x: x0 + w / 2, y: 0, value: pctText(v), label: nm });
            return (
              <g key={nm}>
                <path d={d} fill={BAND_RAMP[i]} />
                <rect className="ov-hit" x={x0} y={-6} width={w} height={height + 12} tabIndex={0} aria-label={`${nm}: ${pctText(v)}`} onPointerMove={show} onFocus={show} onBlur={() => setTip(null)} />
              </g>
            );
          })}
        </svg>
        <Tip tip={tip} width={W} />
      </div>
      <ul className="ov-bands">
        {o.bands.map(([nm, v], i) => (
          <li key={nm}>
            <i style={{ background: BAND_RAMP[i] }} aria-hidden />
            <span>{nm}</span>
            <b>{pctText(v)}</b>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ---------- Small pieces ---------- */

export function Spark({ values, width = 96, height = 28, better = 'up' }: { values: number[]; width?: number; height?: number; better?: 'up' | 'down' }) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (i: number) => 3 + (i * (width - 6)) / (values.length - 1);
  const y = (v: number) => 3 + (height - 6) * (1 - (v - min) / span);
  const d = values.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join('');
  const last = values.at(-1)!;
  const up = last >= values.at(-2)!;
  const good = better === 'up' ? up : !up;
  return (
    <svg className="ov-spark" width={width} height={height} aria-hidden>
      <path d={d} fill="none" stroke="#B9B2A3" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <path d={`M${x(values.length - 2)},${y(values.at(-2)!)}L${x(values.length - 1)},${y(last)}`} stroke={good ? 'var(--pass)' : 'var(--fail)'} strokeWidth={2} strokeLinecap="round" />
      <circle cx={x(values.length - 1)} cy={y(last)} r={3.5} fill={good ? 'var(--pass)' : 'var(--fail)'} stroke="var(--surface)" strokeWidth={1.5} />
    </svg>
  );
}

/** A signed change, coloured by whether the direction is good, never by sign alone. */
export function Delta({ value, unit = 'pts', better = 'up', digits = 1 }: { value: number; unit?: string; better?: 'up' | 'down'; digits?: number }) {
  const flat = Math.abs(value) < 0.05;
  const good = flat ? null : better === 'up' ? value > 0 : value < 0;
  return (
    <span className={`ov-delta ${good === null ? 'is-flat' : good ? 'is-good' : 'is-bad'}`}>
      {flat ? '±0' : `${value > 0 ? '+' : '−'}${Math.abs(value).toFixed(digits)}`}
      {unit ? ` ${unit}` : ''}
    </span>
  );
}

export function SampleView({ sample, size = 'sm' }: { sample: Sample; size?: 'sm' | 'md' }) {
  if (sample.kind === 'crop') return <ObjectCrop box={sample.box} src={sample.src} pad={sample.box.w < 5 ? 2.5 : 1.2} className={`ov-crop is-${size}`} masked={sample.masked} />;
  return <span className={`ov-snippet is-${size}`}>“{sample.text}”</span>;
}

export const metaLine = (o: Overview) =>
  `${fmt(o.assets)} ${o.unit} · ${fmt(o.labels)} ${o.labelNoun} · ${o.team} reviewer${o.team === 1 ? '' : 's'} · ${ahtText(o.ahtSec)} per ${o.unitOne}`;
