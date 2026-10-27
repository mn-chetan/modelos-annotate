/*
 * Direction C — "Pipeline in motion". Motion and storytelling first.
 * A dark stage where one frame carries the story: a scan reveals the AI draft, a person
 * corrects it, QC approves it, and it leaves as data. Scroll drives the sequence.
 * Reduced motion gets the same steps as still frames.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  AnimatePresence,
  motion,
  MotionConfig,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
  useTransform,
} from 'motion/react';
import { ArrowRight } from 'lucide-react';
import { BrandLockup } from '../../../src/brand/BrandLockup';
import {
  WORKSPACE_HREF,
  capabilities,
  exportSample,
  images,
  streetBoxes,
  workflow,
  type Modality,
} from '../content';
import { DetectionFrame, EntityText, Filmstrip, PiiFrame, TrackFrame } from '../specimens';
import './c.css';

const ease = [0.22, 0.8, 0.26, 1] as const;

/* ---------- Hero frame: tilted stage with a scanning reveal ---------- */

function ScanFrame() {
  return (
    <div className="c-scan">
      <DetectionFrame stage="ai" tone="dark" showConfidence />
      <div className="c-beam" aria-hidden />
    </div>
  );
}

function Hero() {
  const ref = useRef<HTMLElement>(null);
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end start'] });
  const rotateX = useTransform(scrollYProgress, [0, 0.55], [22, 0]);
  const scale = useTransform(scrollYProgress, [0, 0.55], [0.88, 1]);
  const y = useTransform(scrollYProgress, [0, 0.55], [0, -40]);
  const glow = useTransform(scrollYProgress, [0, 0.55], [0.9, 0.35]);

  return (
    <section ref={ref} className="c-hero">
      <motion.div className="c-glow" style={{ opacity: glow }} aria-hidden />
      <div className="c-hero-copy">
        <motion.p
          className="c-eyebrow"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease }}
        >
          Annotation for image, text and video
        </motion.p>
        <h1 className="c-display">
          <motion.span
            initial={{ opacity: 0, y: 28 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, ease, delay: 0.05 }}
          >
            From raw data
          </motion.span>
          <motion.span
            initial={{ opacity: 0, y: 28 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, ease, delay: 0.18 }}
          >
            to <em>ground truth.</em>
          </motion.span>
        </h1>
        <motion.div
          className="c-hero-actions"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease, delay: 0.35 }}
        >
          <p>AI drafts every label. People correct it. Quality checks approve it.</p>
          <a className="c-btn c-btn-light" href={WORKSPACE_HREF}>
            Open workspace <ArrowRight size={16} aria-hidden />
          </a>
        </motion.div>
      </div>

      <div className="c-stage">
        <motion.div className="c-tilt" style={reduce ? undefined : { rotateX, scale, y }}>
          <ScanFrame />
          <motion.span
            className="c-float c-float-a"
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, ease, delay: 1.2 }}
          >
            <i className="is-ai" /> AI pre-annotation · {streetBoxes.length} objects
          </motion.span>
          <motion.span
            className="c-float c-float-b"
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, ease, delay: 1.6 }}
          >
            <i className="is-flag" /> 2 low-confidence calls sent to review
          </motion.span>
        </motion.div>
      </div>
    </section>
  );
}

/* ---------- Pinned pipeline ---------- */

function IntakeScene() {
  return (
    <div className="c-intake">
      <motion.div
        className="c-card c-card-img"
        initial={{ opacity: 0, rotate: -9, x: -40 }}
        animate={{ opacity: 1, rotate: -6, x: 0 }}
        transition={{ duration: 0.6, ease }}
      >
        <img src={images.street} alt="" />
        <span>street_0412.jpg</span>
      </motion.div>
      <motion.div
        className="c-card c-card-doc"
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease, delay: 0.08 }}
      >
        <div className="c-doc-lines" aria-hidden>
          {[92, 100, 84, 96, 70, 88, 60].map((w, i) => (
            <i key={i} style={{ width: `${w}%` }} />
          ))}
        </div>
        <span>ops-report-0217.txt</span>
      </motion.div>
      <motion.div
        className="c-card c-card-vid"
        initial={{ opacity: 0, rotate: 9, x: 40 }}
        animate={{ opacity: 1, rotate: 6, x: 0 }}
        transition={{ duration: 0.6, ease, delay: 0.16 }}
      >
        <Filmstrip frames={4} tone="dark" />
        <span>junction_cam_03.mp4</span>
      </motion.div>
      <motion.ul
        className="c-classes"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5, delay: 0.35 }}
      >
        {['car', 'bus', 'truck', 'motorcycle', 'cyclist', 'person'].map((c) => (
          <li key={c}>{c}</li>
        ))}
      </motion.ul>
    </div>
  );
}

function ReviewScene() {
  const [fixed, setFixed] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setFixed(true), 1100);
    return () => clearTimeout(t);
  }, []);
  return (
    <div className="c-review">
      <DetectionFrame stage={fixed ? 'review' : 'ai'} tone="dark" showConfidence={!fixed} />
      <motion.svg
        className="c-cursor"
        viewBox="0 0 24 24"
        initial={{ left: '78%', top: '92%' }}
        animate={{ left: '55.5%', top: '74%' }}
        transition={{ duration: 0.9, ease: [0.6, 0, 0.3, 1], delay: 0.15 }}
        aria-hidden
      >
        <path d="M3 2l7.5 19 2.6-7.7L21 10.8z" />
      </motion.svg>
    </div>
  );
}

function QcScene() {
  return (
    <div className="c-qc">
      <DetectionFrame stage="qc" tone="dark" showConfidence={false} />
      <motion.div
        className="c-stamp"
        initial={{ opacity: 0, scale: 1.4, rotate: -14 }}
        animate={{ opacity: 1, scale: 1, rotate: -8 }}
        transition={{ duration: 0.45, ease: [0.3, 1.4, 0.5, 1], delay: 0.25 }}
      >
        <b>Approved</b>
        <span>Quality check</span>
      </motion.div>
    </div>
  );
}

function ExportScene() {
  const lines = exportSample.split('\n');
  return (
    <div className="c-code" role="img" aria-label="Exported label as JSON">
      <div className="c-code-bar" aria-hidden>
        <i />
        <i />
        <i />
        <span>labels.json</span>
      </div>
      <pre>
        {lines.map((l, i) => (
          <motion.span
            key={i}
            className="c-code-line"
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3, delay: 0.05 * i }}
          >
            <em>{String(i + 1).padStart(2, ' ')}</em>
            {l}
          </motion.span>
        ))}
      </pre>
    </div>
  );
}

const scenes: (() => ReactNode)[] = [
  () => <IntakeScene />,
  () => <DetectionFrame stage="ai" tone="dark" />,
  () => <ReviewScene />,
  () => <QcScene />,
  () => <ExportScene />,
];

function Pipeline() {
  const ref = useRef<HTMLElement>(null);
  const [step, setStep] = useState(0);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end end'] });
  const bar = useTransform(scrollYProgress, [0, 1], [0, 1]);
  useMotionValueEvent(scrollYProgress, 'change', (p) => {
    setStep(Math.min(workflow.length - 1, Math.max(0, Math.floor(p * workflow.length))));
  });
  const s = workflow[step];

  return (
    <section ref={ref} id="workflow" className="c-pipe" style={{ height: `${workflow.length * 80 + 20}vh` }}>
      <div className="c-pipe-pin">
        <div className="c-pipe-copy">
          <p className="c-eyebrow">The pipeline</p>
          <div className="c-pipe-count" aria-hidden>
            <span>{String(step + 1).padStart(2, '0')}</span> / {String(workflow.length).padStart(2, '0')}
          </div>
          <AnimatePresence mode="wait">
            <motion.div
              key={s.key}
              className="c-pipe-text"
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -18 }}
              transition={{ duration: 0.35, ease }}
            >
              <h2 className="c-h2">{s.name}</h2>
              <p className="c-pipe-line">{s.line}</p>
              <span className={`c-actor is-${s.actor.toLowerCase()}`}>{s.actor}</span>
            </motion.div>
          </AnimatePresence>
          <ol className="c-ticks" aria-label="Pipeline steps">
            {workflow.map((w, i) => (
              <li key={w.key} className={i === step ? 'is-on' : i < step ? 'is-done' : ''}>
                {w.name}
              </li>
            ))}
          </ol>
        </div>
        <div className="c-pipe-stage">
          <AnimatePresence mode="wait">
            <motion.div
              key={step}
              className="c-scene"
              initial={{ opacity: 0, scale: 0.97, filter: 'blur(6px)' }}
              animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
              exit={{ opacity: 0, scale: 1.02, filter: 'blur(6px)' }}
              transition={{ duration: 0.4, ease }}
            >
              {scenes[step]()}
            </motion.div>
          </AnimatePresence>
          <motion.div className="c-pipe-bar" style={{ scaleX: bar }} aria-hidden />
        </div>
      </div>
    </section>
  );
}

/** Reduced motion: the same steps as still frames, no pinning. */
function PipelineStill() {
  return (
    <section id="workflow" className="c-still">
      <p className="c-eyebrow">The pipeline</p>
      {workflow.map((w, i) => (
        <article key={w.key} className="c-still-row">
          <div>
            <div className="c-pipe-count">
              <span>{String(i + 1).padStart(2, '0')}</span> / 05
            </div>
            <h2 className="c-h2">{w.name}</h2>
            <p className="c-pipe-line">{w.line}</p>
          </div>
          <div className="c-scene">{scenes[i]()}</div>
        </article>
      ))}
    </section>
  );
}

/* ---------- Horizontal modality gallery ---------- */

const modalitySpec: Record<Modality, ReactNode> = {
  image: (
    <div className="c-panel-spec">
      <PiiFrame masked tone="dark" />
    </div>
  ),
  text: (
    <div className="c-panel-spec c-panel-doc">
      <EntityText stage="ai" tone="dark" />
    </div>
  ),
  video: (
    <div className="c-panel-spec">
      <TrackFrame tone="dark" />
      <Filmstrip frames={8} tone="dark" />
    </div>
  ),
};

function Panels() {
  return (
    <>
      {(Object.keys(capabilities) as Modality[]).map((m, i) => {
        const c = capabilities[m];
        return (
          <article key={m} className="c-panel">
            <div className="c-panel-head">
              <span className="c-panel-num">0{i + 1}</span>
              <h3>{c.title}</h3>
            </div>
            {modalitySpec[m]}
            <p>{c.line}</p>
            <ul>
              {c.tasks.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </article>
        );
      })}
    </>
  );
}

function Modalities({ still }: { still: boolean }) {
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end end'] });
  const x = useTransform(scrollYProgress, [0.05, 0.95], ['0%', '-66.6667%']);

  if (still) {
    return (
      <section id="capabilities" className="c-mods-still">
        <h2 className="c-h2 c-mods-title">One pipeline. Three kinds of data.</h2>
        <div className="c-mods-grid">
          <Panels />
        </div>
      </section>
    );
  }

  return (
    <section ref={ref} id="capabilities" className="c-mods">
      <div className="c-mods-pin">
        <h2 className="c-h2 c-mods-title">One pipeline. Three kinds of data.</h2>
        <motion.div className="c-mods-track" style={{ x }}>
          <Panels />
        </motion.div>
      </div>
    </section>
  );
}

/* ---------- Page ---------- */

function useNarrow() {
  const [narrow, setNarrow] = useState(() => matchMedia('(max-width: 820px)').matches);
  useEffect(() => {
    const mq = matchMedia('(max-width: 820px)');
    const on = () => setNarrow(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return narrow;
}

export default function PipelineInMotion() {
  const reduce = useReducedMotion();
  const narrow = useNarrow();

  return (
    <MotionConfig reducedMotion="user">
      <div className="c-root">
        <header className="c-nav">
          <a href="#top" className="c-brand-chip" aria-label="ModelOS Annotate home">
            <BrandLockup size="sm" />
          </a>
          <nav aria-label="Sections">
            <a href="#workflow">Workflow</a>
            <a href="#capabilities">Capabilities</a>
            <a className="c-btn c-btn-light c-btn-sm" href={WORKSPACE_HREF}>
              Open workspace
            </a>
          </nav>
        </header>

        <main id="top">
          <Hero />
          {reduce ? <PipelineStill /> : <Pipeline />}
          <Modalities still={Boolean(reduce) || narrow} />

          <section className="c-close">
            <motion.h2
              className="c-display c-display-sm"
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '0px 0px -15% 0px' }}
              transition={{ duration: 0.8, ease }}
            >
              Ground truth, <em>reviewed.</em>
            </motion.h2>
            <a className="c-btn c-btn-light" href={WORKSPACE_HREF}>
              Open workspace <ArrowRight size={16} aria-hidden />
            </a>
          </section>
        </main>

        <footer className="c-foot">
          <BrandLockup size="md" />
          <span>Image · Text · Video</span>
        </footer>
      </div>
    </MotionConfig>
  );
}
