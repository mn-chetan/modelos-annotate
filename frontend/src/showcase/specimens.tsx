/*
 * Product-shaped specimens shared by the landing explorations. Each one renders a
 * stage of the annotation workflow on real sample material; pages decide layout and
 * choreography around them.
 */
import { CSSProperties } from 'react';
import {
  Box,
  Span,
  entityColor,
  images,
  piiRegions,
  streetBoxes,
  textSample,
  tracks,
} from './content';
import './specimens.css';

export type Stage = 'raw' | 'ai' | 'review' | 'qc';

const pct = (b: Box): CSSProperties => ({
  left: `${b.x}%`,
  top: `${b.y}%`,
  width: `${b.w}%`,
  height: `${b.h}%`,
});

function boxState(b: Box, stage: Stage) {
  if (stage === 'review' && b.fix) return 'flag';
  if (stage === 'qc') return 'pass';
  return 'ai';
}

/** Detection specimen: the street frame with drafted, reviewed or approved boxes. */
export function DetectionFrame({
  stage,
  showConfidence = true,
  className = '',
  boxes = streetBoxes,
}: {
  stage: Stage;
  showConfidence?: boolean;
  className?: string;
  boxes?: Box[];
}) {
  return (
    <div className={`spec-frame ${className}`} data-stage={stage}>
      <img src={images.street} alt="City street with buses, a truck, cars, a motorcyclist and a cyclist" />
      <div className="spec-layer" aria-hidden>
        {boxes.map((b, i) => {
          const state = boxState(b, stage);
          const label = stage === 'raw' ? b.label : (stage === 'review' || stage === 'qc') && b.fix ? b.fix : b.label;
          return (
            <div
              key={b.id}
              className={`spec-box is-${state}${b.x + b.w > 88 ? ' is-right' : ''}`}
              style={{ ...pct(b), transitionDelay: stage === 'ai' ? `${i * 55}ms` : '0ms' }}
            >
              <span className="spec-tag">
                {stage === 'review' && b.fix ? (
                  <>
                    <s>{b.label}</s> {b.fix}
                  </>
                ) : (
                  label
                )}
                {showConfidence && stage === 'ai' ? <em>{b.conf.toFixed(2)}</em> : null}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** PII specimen: plates and faces found, then masked. */
export function PiiFrame({
  masked,
  className = '',
}: {
  masked: boolean;
  className?: string;
}) {
  return (
    <div className={`spec-frame ${className}`} data-masked={masked}>
      {/* Zoomed to street level so plates and faces read at specimen size. */}
      <div className="spec-zoom">
        <img src={images.buses} alt="Busy shopping street with buses, taxis and pedestrians" />
        <div className="spec-layer" aria-hidden>
          {piiRegions.map((r) => (
            <div key={r.id} className={`spec-pii ${masked ? 'is-masked' : ''}`} style={pct(r)} />
          ))}
        </div>
      </div>
    </div>
  );
}

/** Text specimen: entities drafted, one corrected in review, all approved in QC. */
export function EntityText({
  stage,
  spans = textSample,
  className = '',
}: {
  stage: Stage;
  spans?: Span[];
  className?: string;
}) {
  return (
    <p className={`spec-text ${className}`} data-stage={stage}>
      {spans.map((s, i) => {
        if (!s.type || stage === 'raw') return <span key={i}>{s.text}</span>;
        const flagged = stage === 'review' && s.fix;
        const type = (stage === 'review' || stage === 'qc') && s.fix ? s.fix : s.type;
        return (
          <mark
            key={i}
            className={`spec-ent ${flagged ? 'is-flag' : ''} ${stage === 'qc' ? 'is-pass' : ''}`}
            style={{ '--ent': entityColor[type] } as CSSProperties}
          >
            {s.text}
            <sup>
              {flagged ? (
                <>
                  <s>{s.type}</s> {s.fix}
                </>
              ) : (
                type
              )}
            </sup>
          </mark>
        );
      })}
    </p>
  );
}

const trackBoxes = tracks.map((t) => ({ ...t, box: streetBoxes.find((b) => b.id === t.boxId)! }));

/**
 * Video specimen: the street frame drifts like a camera move; boxes ride in the same
 * layer so each track keeps its identity as the frame changes.
 */
export function TrackFrame({
  playing = true,
  showTracks = true,
  className = '',
}: {
  playing?: boolean;
  showTracks?: boolean;
  className?: string;
}) {
  return (
    <div className={`spec-frame spec-video ${className}`} data-playing={playing}>
      <div className="spec-pan">
        <img src={images.street} alt="Video frame of a city street" />
        <div className="spec-layer" aria-hidden>
          {showTracks &&
            trackBoxes.map(({ id, label, box }) => (
              <div key={id} className={`spec-box is-track${box.x + box.w > 88 ? ' is-right' : ''}`} style={pct(box)}>
                <span className="spec-tag">
                  <b>#{id}</b> {label}
                </span>
              </div>
            ))}
        </div>
      </div>
      <div className="spec-rec" aria-hidden>
        <i /> REC
      </div>
    </div>
  );
}

/** A strip of frames under a video specimen with a moving playhead. */
export function Filmstrip({
  frames = 8,
  playing = true,
  className = '',
}: {
  frames?: number;
  playing?: boolean;
  className?: string;
}) {
  return (
    <div className={`spec-strip ${className}`} data-playing={playing} aria-hidden>
      {Array.from({ length: frames }, (_, i) => (
        <div key={i} className="spec-strip-cell" style={{ '--i': i, '--n': frames } as CSSProperties}>
          <img src={images.street} alt="" />
          <span>{String(i * 12).padStart(4, '0')}</span>
        </div>
      ))}
      <div className="spec-playhead" />
    </div>
  );
}

/** Zooms the street frame onto one object, with padding around its box (in % of frame). */
export function ObjectCrop({
  box,
  pad = 3,
  className = '',
  src = images.street,
  masked = false,
  ratio = 1376 / 768,
}: {
  box: Box;
  pad?: number;
  className?: string;
  src?: string;
  masked?: boolean;
  /** The source image's width over height; the showcase photos are 1376 × 768. */
  ratio?: number;
}) {
  const x = Math.max(0, box.x - pad);
  const y = Math.max(0, box.y - pad * 1.5);
  const w = Math.min(100 - x, box.w + pad * 2);
  const h = Math.min(100 - y, box.h + pad * 3);
  return (
    <div className={`spec-crop ${className}`} style={{ aspectRatio: `${w * ratio} / ${h}` }}>
      <img
        src={src}
        alt=""
        style={{
          width: `${(100 / w) * 100}%`,
          height: `${(100 / h) * 100}%`,
          left: `${-(x / w) * 100}%`,
          top: `${-(y / h) * 100}%`,
        }}
      />
      <div
        className={`spec-crop-box${masked ? ' is-masked' : ''}`}
        style={{
          left: `${((box.x - x) / w) * 100}%`,
          top: `${((box.y - y) / h) * 100}%`,
          width: `${(box.w / w) * 100}%`,
          height: `${(box.h / h) * 100}%`,
        }}
      />
    </div>
  );
}
