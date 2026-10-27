/*
 * Direction B — "Live specimen". Interaction-first.
 * The hero is a small working bench: pick a data type, step it through the workflow,
 * and watch the same sample move from draft to approved export.
 */
import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion, MotionConfig } from 'motion/react';
import {
  ArrowRight,
  Check,
  FileText,
  Film,
  Image as ImageIcon,
  Pause,
  Play,
  ScanEye,
  ShieldCheck,
  History,
} from 'lucide-react';
import { BrandLockup } from '../../../src/brand/BrandLockup';
import {
  workspaceHref,
  capabilities,
  exportSample,
  piiRegions,
  streetBoxes,
  textSample,
  textVerdicts,
  tracks,
  workflow,
  type Modality,
} from '../../../src/showcase/content';
import { DetectionFrame, EntityText, Filmstrip, PiiFrame, TrackFrame, type Stage } from '../../../src/showcase/specimens';
import './b.css';

const STEP_MS = 3200;
const stageForStep: Stage[] = ['raw', 'ai', 'review', 'qc', 'qc'];
const tabs: { key: Modality; icon: typeof ImageIcon }[] = [
  { key: 'image', icon: ImageIcon },
  { key: 'text', icon: FileText },
  { key: 'video', icon: Film },
];

type Status = 'draft' | 'review' | 'approved' | 'pending';

function statusFor(step: number, needsReview: boolean): Status {
  if (step === 0) return 'pending';
  if (step === 1) return 'draft';
  if (step === 2) return needsReview ? 'review' : 'draft';
  return 'approved';
}

const statusText: Record<Status, string> = {
  pending: 'Queued',
  draft: 'AI draft',
  review: 'In review',
  approved: 'Approved',
};

function StatusChip({ s }: { s: Status }) {
  return <span className={`b-chip is-${s}`}>{statusText[s]}</span>;
}

/* ---------- Side panel rows per modality ---------- */

function ImageRows({ step, pii }: { step: number; pii: boolean }) {
  if (pii) {
    const plates = piiRegions.filter((r) => r.label === 'plate').length;
    const faces = piiRegions.length - plates;
    return (
      <ul className="b-rows">
        <li>
          <span className="b-row-label">Number plates</span>
          <span className="b-row-val">{step === 0 ? '—' : plates}</span>
          <StatusChip s={step >= 3 ? 'approved' : statusFor(step, false)} />
        </li>
        <li>
          <span className="b-row-label">Faces</span>
          <span className="b-row-val">{step === 0 ? '—' : faces}</span>
          <StatusChip s={step >= 3 ? 'approved' : statusFor(step, false)} />
        </li>
        <li className="b-row-note">{step >= 3 ? 'Regions masked in the exported image.' : 'Regions are masked once approved.'}</li>
      </ul>
    );
  }
  const rows = [...streetBoxes].sort((a, b) => a.conf - b.conf).slice(0, 7);
  return (
    <ul className="b-rows">
      {rows.map((b) => {
        const fixed = step >= 2 && b.fix;
        return (
          <li key={b.id} className={step === 2 && b.fix ? 'is-flag' : ''}>
            <span className="b-row-label">
              {fixed ? (
                <>
                  <s>{b.label}</s> {b.fix}
                </>
              ) : (
                b.label
              )}
            </span>
            <span className="b-row-val">{step === 0 ? '—' : b.conf.toFixed(2)}</span>
            <StatusChip s={statusFor(step, Boolean(b.fix))} />
          </li>
        );
      })}
      <li className="b-row-note">+{streetBoxes.length - rows.length} more, sorted by confidence</li>
    </ul>
  );
}

function TextRows({ step }: { step: number }) {
  const ents = textSample.filter((s) => s.type);
  return (
    <ul className="b-rows">
      {ents.map((e) => {
        const fixed = step >= 2 && e.fix;
        return (
          <li key={e.text} className={step === 2 && e.fix ? 'is-flag' : ''}>
            <span className="b-row-label">
              {e.text}{' '}
              <small>
                {fixed ? (
                  <>
                    <s>{e.type}</s> {e.fix}
                  </>
                ) : (
                  e.type
                )}
              </small>
            </span>
            <span className="b-row-val">{step === 0 ? '—' : e.conf?.toFixed(2)}</span>
            <StatusChip s={statusFor(step, Boolean(e.fix))} />
          </li>
        );
      })}
      <li>
        <span className="b-row-label">
          Sentiment <small>{step === 0 ? '' : textVerdicts.sentiment.label}</small>
        </span>
        <span className="b-row-val">{step === 0 ? '—' : textVerdicts.sentiment.conf.toFixed(2)}</span>
        <StatusChip s={statusFor(step, false)} />
      </li>
      <li>
        <span className="b-row-label">
          Category <small>{step === 0 ? '' : textVerdicts.category.label}</small>
        </span>
        <span className="b-row-val">{step === 0 ? '—' : textVerdicts.category.conf.toFixed(2)}</span>
        <StatusChip s={statusFor(step, false)} />
      </li>
      <li className="b-row-note">
        Relation: {textVerdicts.relation.from} <code>{textVerdicts.relation.rel}</code> {textVerdicts.relation.to}
      </li>
    </ul>
  );
}

function VideoRows({ step }: { step: number }) {
  return (
    <ul className="b-rows">
      {tracks.map((t) => {
        const box = streetBoxes.find((b) => b.id === t.boxId)!;
        const needs = Boolean(box.fix);
        return (
          <li key={t.id} className={step === 2 && needs ? 'is-flag' : ''}>
            <span className="b-row-label">
              <b>#{t.id}</b>{' '}
              {step >= 2 && box.fix ? (
                <>
                  <s>{box.label}</s> {t.label}
                </>
              ) : needs ? (
                box.label
              ) : (
                t.label
              )}
            </span>
            <span className="b-row-val">{step === 0 ? '—' : '84 fr'}</span>
            <StatusChip s={statusFor(step, needs)} />
          </li>
        );
      })}
      <li className="b-row-note">Tracks keep one ID for the whole clip.</li>
    </ul>
  );
}

function IntakePanel({ modality }: { modality: Modality }) {
  const classes =
    modality === 'text'
      ? 'Person, Organisation, Location, Date'
      : 'car, bus, truck, motorcycle, cyclist, person';
  return (
    <dl className="b-intake">
      <div>
        <dt>Data</dt>
        <dd>{modality === 'image' ? 'Street imagery' : modality === 'text' ? 'Operations reports' : 'Traffic clips'}</dd>
      </div>
      <div>
        <dt>Classes</dt>
        <dd>{classes}</dd>
      </div>
      <div>
        <dt>Review</dt>
        <dd>Confidence below 0.70 goes to a person first</dd>
      </div>
      <div>
        <dt>Quality</dt>
        <dd>Independent sample audit before export</dd>
      </div>
    </dl>
  );
}

/* ---------- The bench ---------- */

function Bench({ modality, setModality }: { modality: Modality; setModality: (m: Modality) => void }) {
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [pii, setPii] = useState(false);
  const stage = stageForStep[step];

  useEffect(() => {
    if (!playing) return;
    const t = setTimeout(() => setStep((s) => (s + 1) % workflow.length), STEP_MS);
    return () => clearTimeout(t);
  }, [playing, step]);

  const choose = (i: number) => {
    setPlaying(false);
    setStep(i);
  };

  const pickModality = (m: Modality) => {
    setModality(m);
    setStep(0);
    setPii(false);
  };

  const canvas =
    modality === 'image' ? (
      pii ? (
        <PiiFrame masked={step >= 3} className={step === 0 ? 'b-hide-pii' : ''} />
      ) : (
        <DetectionFrame stage={stage} />
      )
    ) : modality === 'text' ? (
      <div className="b-doc">
        <p className="b-doc-meta">ops-report-0217.txt</p>
        <EntityText stage={stage} />
        {step >= 1 ? (
          <p className="b-doc-verdicts">
            <span>Sentiment · {textVerdicts.sentiment.label}</span>
            <span>Category · {textVerdicts.category.label}</span>
          </p>
        ) : null}
      </div>
    ) : (
      <div className="b-video">
        <TrackFrame showTracks={step >= 1} playing={playing || step > 0} />
        <Filmstrip frames={10} playing={playing || step > 0} />
      </div>
    );

  return (
    <div className="b-bench" id="bench">
      <div className="b-bench-bar">
        <div className="b-tabs" role="tablist" aria-label="Data type">
          {tabs.map(({ key, icon: Icon }) => (
            <button
              key={key}
              role="tab"
              aria-selected={modality === key}
              className="b-tab"
              onClick={() => pickModality(key)}
            >
              {modality === key ? <motion.span layoutId="b-tab-pill" className="b-tab-pill" /> : null}
              <Icon size={15} aria-hidden />
              <span>{capabilities[key].title}</span>
            </button>
          ))}
        </div>
        {modality === 'image' ? (
          <div className="b-sub" role="group" aria-label="Image task">
            <button aria-pressed={!pii} onClick={() => { setPii(false); setStep(0); }}>
              Detection
            </button>
            <button aria-pressed={pii} onClick={() => { setPii(true); setStep(0); }}>
              PII masking
            </button>
          </div>
        ) : null}
        <span className="b-sample">Sample data</span>
      </div>

      <div className="b-bench-body">
        <div className="b-canvas">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={modality + String(pii)}
              initial={{ opacity: 0, scale: 0.985 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.985 }}
              transition={{ duration: 0.28, ease: [0.22, 0.8, 0.26, 1] }}
              className="b-canvas-inner"
            >
              {canvas}
            </motion.div>
          </AnimatePresence>
        </div>
        <aside className="b-panel" aria-live="polite">
          <header className="b-panel-head">
            <h3>{step === 4 ? 'Export' : step === 0 ? 'Project setup' : 'Labels'}</h3>
            <span>{workflow[step].actor === 'AI' ? 'AI' : workflow[step].actor}</span>
          </header>
          {step === 0 ? (
            <IntakePanel modality={modality} />
          ) : step === 4 ? (
            <pre className="b-code">
              <code>{exportSample}</code>
            </pre>
          ) : modality === 'image' ? (
            <ImageRows step={step} pii={pii} />
          ) : modality === 'text' ? (
            <TextRows step={step} />
          ) : (
            <VideoRows step={step} />
          )}
        </aside>
      </div>

      <div className="b-steps">
        <button
          className="b-play"
          onClick={() => setPlaying((p) => !p)}
          aria-label={playing ? 'Pause walkthrough' : 'Play walkthrough'}
        >
          {playing ? <Pause size={15} /> : <Play size={15} />}
        </button>
        <ol>
          {workflow.map((s, i) => (
            <li key={s.key}>
              <button
                className={`b-step ${i === step ? 'is-on' : ''} ${i < step ? 'is-done' : ''}`}
                onClick={() => choose(i)}
                aria-current={i === step ? 'step' : undefined}
              >
                <span className="b-step-num">{i < step ? <Check size={12} aria-hidden /> : i + 1}</span>
                <span className="b-step-name">{s.name}</span>
                {i === step && playing ? (
                  <motion.span
                    key={`p${step}`}
                    className="b-step-progress"
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: 1 }}
                    transition={{ duration: STEP_MS / 1000, ease: 'linear' }}
                  />
                ) : null}
              </button>
            </li>
          ))}
        </ol>
      </div>
      <p className="b-step-line">{workflow[step].line}</p>
    </div>
  );
}

const principles = [
  {
    icon: ScanEye,
    title: 'Review where it matters',
    line: 'Confidence decides what a person sees first, so reviewers spend time on the calls that need them.',
  },
  {
    icon: History,
    title: 'Every decision kept',
    line: 'Accepts, corrections and rejections stay attached to the label they changed.',
  },
  {
    icon: ShieldCheck,
    title: 'Quality you can report on',
    line: 'Independent audits and per-project production and quality reports, before anything ships.',
  },
];

export default function LiveSpecimen() {
  const [modality, setModality] = useState<Modality>('image');
  const benchRef = useRef<HTMLDivElement>(null);

  const jump = (m: Modality) => {
    setModality(m);
    benchRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  return (
    <MotionConfig reducedMotion="user">
      <div className="b-root">
        <header className="b-top">
          <BrandLockup size="md" />
          <a className="b-btn b-btn-accent b-btn-sm" href={workspaceHref('b')}>
            Open workspace
          </a>
        </header>

        <main>
          <section className="b-hero">
            <motion.div
              className="b-hero-copy"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease: [0.22, 0.8, 0.26, 1] }}
            >
              <p className="b-kicker">Annotation for image, text and video</p>
              <h1>
                AI drafts the labels.
                <br />
                <span>People make the call.</span>
              </h1>
              <p className="b-sub-lede">
                One workspace to annotate, review and quality-check training data, with a person in
                the loop wherever the model is unsure.
              </p>
            </motion.div>
            <motion.div
              ref={benchRef}
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.1, ease: [0.22, 0.8, 0.26, 1] }}
            >
              <Bench modality={modality} setModality={setModality} />
            </motion.div>
          </section>

          <section className="b-caps" aria-label="Capabilities">
            {(Object.keys(capabilities) as Modality[]).map((m) => {
              const c = capabilities[m];
              const Icon = tabs.find((t) => t.key === m)!.icon;
              return (
                <article key={m} className="b-cap">
                  <Icon size={20} aria-hidden />
                  <h2>{c.title}</h2>
                  <p>{c.line}</p>
                  <ul>
                    {c.tasks.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                  <button className="b-cap-try" onClick={() => jump(m)}>
                    Try it above <ArrowRight size={14} aria-hidden />
                  </button>
                </article>
              );
            })}
          </section>

          <section className="b-principles">
            <h2>Built for the people who sign off on the data.</h2>
            <div className="b-principles-grid">
              {principles.map(({ icon: Icon, title, line }) => (
                <div key={title} className="b-principle">
                  <Icon size={20} aria-hidden />
                  <h3>{title}</h3>
                  <p>{line}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="b-cta">
            <h2>Run your first project.</h2>
            <p>Bring a dataset, name the classes, and let the first pass run.</p>
            <a className="b-btn b-btn-accent" href={workspaceHref('b')}>
              Open workspace <ArrowRight size={16} aria-hidden />
            </a>
          </section>
        </main>

        <footer className="b-foot">
          <BrandLockup size="sm" />
          <span>Image · Text · Video</span>
        </footer>
      </div>
    </MotionConfig>
  );
}
