import {
  useLayoutEffect,
  useRef,
  useState,
  type RefObject,
  type SVGProps,
} from 'react';
import type { Annotation } from '../store';
import { colourStyle } from './annotation-ui';
import './review.css';

type Props = {
  annotations: Annotation[];
  colours: Record<string, string>;
  selected?: string;
  hovered?: string;
  names?: boolean;
  showRejected?: boolean;
  visible?: boolean;
  svgRef?: RefObject<SVGSVGElement | null>;
  editable?: boolean;
  onHover?: (id: string) => void;
  onSelect?: (id: string) => void;
} & Omit<SVGProps<SVGSVGElement>, 'onSelect'>;

type Caption = {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  index: number;
  annotation: Annotation;
};
const within = (n: number, max: number) => Math.max(4, Math.min(n, max));
/** Geometry stays in image percentages. Typography and handles stay in screen pixels. */
export function BoxOverlay({
  annotations,
  colours,
  selected = '',
  hovered = '',
  names = false,
  showRejected = false,
  visible = true,
  svgRef,
  editable = false,
  onHover,
  onSelect,
  ...svgProps
}: Props) {
  const localRef = useRef<SVGSVGElement>(null);
  const ref = svgRef || localRef;
  const [size, setSize] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const bounds = el.getBoundingClientRect();
      setSize((s) =>
        s.width === bounds.width && s.height === bounds.height
          ? s
          : { width: bounds.width, height: bounds.height },
      );
    };
    measure();
    const observer =
      typeof ResizeObserver === 'undefined'
        ? undefined
        : new ResizeObserver(measure);
    observer?.observe(el);
    window.addEventListener('resize', measure);
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [ref]);
  const focus = hovered || selected;
  const boxes = annotations
    .filter(
      (a) =>
        (!a.geometry_type || a.geometry_type === 'box') &&
        (showRejected || a.review_status !== 'rejected' || a.id === focus),
    )
    .sort((a, b) => Number(a.id === selected) - Number(b.id === selected));
  const captions: Caption[] = [];
  if (visible && size.width && size.height) {
    // Reserve the focused label first; keep other labels from overlapping it or each other.
    const ordered = [...boxes].sort(
      (a, b) => Number(b.id === focus) - Number(a.id === focus),
    );
    for (const a of ordered) {
      if (!names && a.id !== focus) continue;
      const index = annotations.findIndex((row) => row.id === a.id);
      const w = Math.min(
        size.width - 8,
        Math.max(110, Math.min(220, a.label.length * 7 + 92)),
      );
      const h = 27;
      const x = (a.x / 100) * size.width,
        y = (a.y / 100) * size.height;
      const right = ((a.x + a.w) / 100) * size.width,
        bottom = ((a.y + a.h) / 100) * size.height;
      const candidates = [
        [x, y - h - 3],
        [x, y + 4],
        [right - w, y - h - 3],
        [x, bottom + 3],
      ];
      for (const [left, top] of candidates) {
        const candidate = {
          id: a.id,
          x: within(left, size.width - w - 4),
          y: within(top, size.height - h - 4),
          w,
          h,
          index,
          annotation: a,
        };
        if (
          a.id !== focus &&
          captions.some(
            (c) =>
              candidate.x < c.x + c.w + 6 &&
              candidate.x + w + 6 > c.x &&
              candidate.y < c.y + c.h + 5 &&
              candidate.y + h + 5 > c.y,
          )
        )
          continue;
        captions.push(candidate);
        break;
      }
    }
  }
  return (
    <div className={`annotation-overlay${focus ? ' has-focus' : ''}`}>
      <svg
        {...svgProps}
        ref={ref}
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        className="box-geometry"
        onClick={(e) => {
          svgProps.onClick?.(e);
          if (e.target === e.currentTarget) onSelect?.('');
        }}
        style={{
          ...svgProps.style,
          opacity: visible ? 1 : 0,
          pointerEvents: visible ? 'auto' : 'none',
        }}
      >
        {boxes.map((a) => {
          const active = a.id === focus;
          const colour =
            a.review_status === 'rejected'
              ? '#F58282'
              : colours[a.label] || '#47B8E0';
          const hw = 800 / (size.width || 1000),
            hh = 800 / (size.height || 600);
          return (
            <g
              key={a.id}
              data-id={a.id}
              className={`annotation-box${active ? ' is-focused' : ''}${a.id === selected ? ' is-selected' : ''}`}
              style={{
                ...colourStyle(colour),
                opacity: focus && !active ? 0.3 : 1,
              }}
              onPointerEnter={() => onHover?.(a.id)}
              onPointerLeave={() => onHover?.('')}
              onClick={() => onSelect?.(a.id)}
            >
              <rect
                x={a.x}
                y={a.y}
                width={a.w}
                height={a.h}
                stroke={colour}
                strokeWidth={active ? 2.5 : 1.5}
                vectorEffect="non-scaling-stroke"
                fill={active ? '#ffffff0d' : 'transparent'}
                strokeDasharray={
                  a.review_status === 'rejected' ? '5 4' : undefined
                }
              />
              {editable &&
                a.id === selected &&
                ['nw', 'ne', 'sw', 'se'].map((corner) => (
                  <rect
                    key={corner}
                    data-handle={corner}
                    x={(corner.includes('w') ? a.x : a.x + a.w) - hw / 2}
                    y={(corner.includes('n') ? a.y : a.y + a.h) - hh / 2}
                    width={hw}
                    height={hh}
                    fill="white"
                    stroke={colour}
                    strokeWidth="1.5"
                    vectorEffect="non-scaling-stroke"
                    style={{ cursor: `${corner}-resize` }}
                  />
                ))}
            </g>
          );
        })}
      </svg>
      <div className="box-captions" aria-hidden="true">
        {captions.map((c) => (
          <div
            key={c.id}
            className={`box-caption${c.id === focus ? ' is-focused' : ''}`}
            style={{
              ...colourStyle(
                c.annotation.review_status === 'rejected'
                  ? '#F58282'
                  : colours[c.annotation.label] || '#47B8E0',
              ),
              left: c.x,
              top: c.y,
              width: c.w,
            }}
          >
            <span className="box-caption-index">
              {String(c.index + 1).padStart(2, '0')}
            </span>
            <b>{c.annotation.label}</b>
            {c.annotation.confidence != null && (
              <span>{Math.round(c.annotation.confidence * 100)}%</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
