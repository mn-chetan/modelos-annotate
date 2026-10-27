/*
 * The landing page — "The Review Desk". Editorial, reading-first, low motion.
 * Concept-07 paper and ink; a serif headline over one large annotated figure;
 * capabilities as an index, the workflow as a ledger.
 */
import { useEffect, useState, type ReactNode } from 'react';
import { motion, MotionConfig } from 'motion/react';
import { ArrowRight, ArrowUpRight } from 'lucide-react';
import { BrandLockup } from '../brand/BrandLockup';
import { WORKSPACE_HREF, capabilities, streetBoxes, workflow, type Modality } from '../showcase/content';
import {
  DetectionFrame,
  EntityText,
  Filmstrip,
  ObjectCrop,
  PiiFrame,
  TrackFrame,
  type Stage,
} from '../showcase/specimens';
import './landing.css';

const reveal = {
  initial: { opacity: 0, y: 14 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: '0px 0px -12% 0px' },
  transition: { duration: 0.6, ease: [0.22, 0.8, 0.26, 1] as const },
};

function useHeroStage(): Stage {
  const [stage, setStage] = useState<Stage>('raw');
  useEffect(() => {
    const t1 = setTimeout(() => setStage('ai'), 500);
    const t2 = setTimeout(() => setStage('review'), 2600);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, []);
  return stage;
}

const specimenFor: Record<Modality, ReactNode> = {
  image: (
    <figure className="a-spec">
      <PiiFrame masked className="spec-compact" />
      <figcaption>Plates and faces found and masked before review.</figcaption>
    </figure>
  ),
  text: (
    <figure className="a-spec">
      <div className="a-sheet">
        <EntityText stage="ai" />
      </div>
      <figcaption>Entities drafted in context, each with its type.</figcaption>
    </figure>
  ),
  video: (
    <figure className="a-spec">
      <TrackFrame />
      <Filmstrip frames={8} />
      <figcaption>Track IDs held from frame to frame.</figcaption>
    </figure>
  ),
};

const actorClass: Record<string, string> = { AI: 'is-ai', Reviewer: 'is-rev', QC: 'is-qc', Team: 'is-team' };

export default function Landing() {
  const stage = useHeroStage();
  const moto = streetBoxes.find((b) => b.id === 'b3')!;

  return (
    <MotionConfig reducedMotion="user">
      <div className="a-root">
        <header className="a-top">
          <a href="#top" className="a-brand" aria-label="ModelOS Annotate home">
            <BrandLockup size="md" />
          </a>
          <nav className="a-nav" aria-label="Sections">
            <a href="#capabilities">Capabilities</a>
            <a href="#workflow">Workflow</a>
            <a href="#quality">Quality</a>
          </nav>
          <a className="a-btn a-btn-ink a-btn-sm" href={WORKSPACE_HREF}>
            Open workspace
          </a>
        </header>

        <main id="top">
          <section className="a-hero">
            <div className="a-hero-copy">
              <p className="a-eyebrow">Data annotation for image, text and video</p>
              <h1 className="a-display">
                Labels your reviewers <em>can stand behind.</em>
              </h1>
            </div>
            <div className="a-hero-side">
              <p className="a-lede">
                ModelOS Annotate drafts every label with AI, puts each uncertain call in front of a
                person, and audits the result before it leaves.
              </p>
              <div className="a-actions">
                <a className="a-btn a-btn-ink" href={WORKSPACE_HREF}>
                  Open workspace <ArrowRight size={16} aria-hidden />
                </a>
                <a className="a-link" href="#workflow">
                  See the workflow
                </a>
              </div>
            </div>
            <motion.figure className="a-figure" {...reveal}>
              <DetectionFrame stage={stage} />
              <figcaption>
                <span className="a-fig">Fig. 1</span>
                AI drafted twelve objects. The two it was unsure of went to a reviewer, who corrected
                both.
                <span className="a-legend" aria-hidden>
                  <i className="is-ai" /> AI draft <i className="is-flag" /> Sent to review
                </span>
              </figcaption>
            </motion.figure>
          </section>

          <section id="capabilities" className="a-section">
            <motion.header className="a-section-head" {...reveal}>
              <p className="a-eyebrow">
                <span>01</span> Capabilities
              </p>
              <h2 className="a-h2">One desk for three kinds of data.</h2>
            </motion.header>
            <ol className="a-index">
              {(Object.keys(capabilities) as Modality[]).map((m, i) => {
                const c = capabilities[m];
                return (
                  <motion.li key={m} className="a-index-row" {...reveal}>
                    <span className="a-index-num">0{i + 1}</span>
                    <div className="a-index-copy">
                      <h3 className="a-h3">{c.title}</h3>
                      <p>{c.line}</p>
                      <ul className="a-tasks">
                        {c.tasks.map((t) => (
                          <li key={t}>{t}</li>
                        ))}
                      </ul>
                    </div>
                    {specimenFor[m]}
                  </motion.li>
                );
              })}
            </ol>
          </section>

          <section id="workflow" className="a-section">
            <motion.header className="a-section-head" {...reveal}>
              <p className="a-eyebrow">
                <span>02</span> Workflow
              </p>
              <h2 className="a-h2">From intake to export, every label has an owner.</h2>
            </motion.header>
            <motion.div className="a-ledger-wrap" {...reveal}>
              <table className="a-ledger">
                <thead>
                  <tr>
                    <th scope="col">No.</th>
                    <th scope="col">Step</th>
                    <th scope="col">Owner</th>
                    <th scope="col">What happens</th>
                  </tr>
                </thead>
                <tbody>
                  {workflow.map((s, i) => (
                    <tr key={s.key}>
                      <td className="a-ledger-num">{String(i + 1).padStart(2, '0')}</td>
                      <th scope="row">{s.name}</th>
                      <td>
                        <span className={`a-actor ${actorClass[s.actor]}`}>{s.actor}</span>
                      </td>
                      <td>{s.line}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </motion.div>
          </section>

          <section id="quality" className="a-section a-quality">
            <motion.div className="a-quality-copy" {...reveal}>
              <p className="a-eyebrow">
                <span>03</span> Quality
              </p>
              <h2 className="a-h2">Quality is a step, not a hope.</h2>
              <p className="a-body">
                Confidence decides what a person sees first. Every correction is kept, and an
                independent check approves the work, or sends it back, before anything is exported.
              </p>
              <ul className="a-points">
                <li>Low-confidence labels routed to review first</li>
                <li>A trail of every accept, correction and rejection</li>
                <li>Sampled quality audits with rework and reject</li>
                <li>Production and quality reports per project</li>
              </ul>
            </motion.div>
            <motion.article className="a-trail" {...reveal} aria-label="Decision trail for one label">
              <ObjectCrop box={moto} pad={2.5} className="a-trail-crop" />
              <ol className="a-trail-steps">
                <li>
                  <span className="a-actor is-ai">AI</span>
                  <p>
                    Labelled <code>person</code>
                  </p>
                  <span className="a-trail-meta">confidence 0.58</span>
                </li>
                <li>
                  <span className="a-actor is-rev">Reviewer</span>
                  <p>
                    Corrected to <code>motorcycle</code>
                  </p>
                  <span className="a-trail-meta">box kept</span>
                </li>
                <li>
                  <span className="a-actor is-qc">QC</span>
                  <p>Approved</p>
                  <span className="a-trail-meta">ready to export</span>
                </li>
              </ol>
            </motion.article>
          </section>

          <section className="a-close">
            <motion.div {...reveal}>
              <h2 className="a-display a-display-sm">Start with a project.</h2>
              <p className="a-lede">Bring a dataset, name the classes, and let the first pass run.</p>
              <a className="a-btn a-btn-ink" href={WORKSPACE_HREF}>
                Open workspace <ArrowUpRight size={16} aria-hidden />
              </a>
            </motion.div>
          </section>
        </main>

        <footer className="a-foot">
          <BrandLockup size="sm" />
          <span>Image · Text · Video</span>
        </footer>
      </div>
    </MotionConfig>
  );
}
