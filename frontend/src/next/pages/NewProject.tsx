import { useState } from 'react';
import { FileText, Film, Image as ImageIcon, X } from 'lucide-react';
import { projects, type Modality } from '../../showcase/content';
import { navigate } from '../router';
import { PageHead } from './shared';

const types: { key: Modality; icon: typeof ImageIcon; title: string; line: string }[] = [
  { key: 'image', icon: ImageIcon, title: 'Image', line: 'Photos and frames: boxes, classes and masks.' },
  { key: 'text', icon: FileText, title: 'Text', line: 'Documents and messages: entities, sentiment, categories.' },
  { key: 'video', icon: Film, title: 'Video', line: 'Clips: objects detected and tracked across frames.' },
];

const tasks: Record<Modality, string[]> = {
  image: ['Object detection', 'PII masking'],
  text: ['Named entities', 'Sentiment', 'Classification', 'Relation extraction'],
  video: ['Object tracking', 'Detection'],
};

const defaultClasses: Record<string, string[]> = {
  'Object detection': ['car', 'bus', 'truck', 'person'],
  'PII masking': ['number plate', 'face'],
  'Named entities': ['Person', 'Organisation', 'Location', 'Date'],
  Sentiment: ['Positive', 'Neutral', 'Negative'],
  Classification: ['Billing', 'Delivery', 'Product'],
  'Relation extraction': ['works_at', 'located_in'],
  'Object tracking': ['car', 'bus', 'cyclist'],
  Detection: ['car', 'person'],
};

export function NewProjectPage() {
  const [modality, setModality] = useState<Modality>('image');
  const [task, setTask] = useState(tasks.image[0]);
  const [classes, setClasses] = useState(defaultClasses[task]);
  const [threshold, setThreshold] = useState(0.7);
  const [sample, setSample] = useState(10);

  const pickModality = (m: Modality) => {
    setModality(m);
    setTask(tasks[m][0]);
    setClasses(defaultClasses[tasks[m][0]]);
  };
  const pickTask = (t: string) => {
    setTask(t);
    setClasses(defaultClasses[t]);
  };
  const create = () => {
    // Static showcase: open the sample project that matches what was chosen.
    const match = projects.find((p) => p.modality === modality && p.task === task) ?? projects.find((p) => p.modality === modality)!;
    navigate({ id: 'project', projectId: match.id, tab: 'overview' });
  };

  return (
    <div className="page">
      <PageHead
        eyebrow="Workspace"
        title="New project"
        lede="Say what the data is and what to label. AI drafts the first pass; your rules decide what people check."
      />
      <div className="split">
        <section className="card card-pad">
          <div className="form-step">
            <h2>
              <span>01</span>Data type
            </h2>
            <div className="choice-grid">
              {types.map(({ key, icon: Icon, title, line }) => (
                <button key={key} className="choice" aria-pressed={modality === key} onClick={() => pickModality(key)}>
                  <Icon size={20} aria-hidden />
                  <b>{title}</b>
                  <small>{line}</small>
                </button>
              ))}
            </div>
          </div>
          <div className="form-step">
            <h2>
              <span>02</span>Task
            </h2>
            <div className="pills">
              {tasks[modality].map((t) => (
                <button key={t} className="pill-btn" aria-pressed={task === t} onClick={() => pickTask(t)}>
                  {t}
                </button>
              ))}
            </div>
          </div>
          <div className="form-step">
            <h2>
              <span>03</span>Classes
            </h2>
            <div>
              <p>The labels annotators and the model can use.</p>
              <div className="pills">
                {classes.map((c) => (
                  <span key={c} className="tag">
                    {c}
                    <button
                      className="icon-btn"
                      style={{ width: 18, height: 18, border: 0, background: 'none' }}
                      aria-label={`Remove ${c}`}
                      onClick={() => setClasses(classes.filter((x) => x !== c))}
                    >
                      <X size={12} />
                    </button>
                  </span>
                ))}
                <span className="tag muted">+ Add class</span>
              </div>
            </div>
          </div>
          <div className="form-step">
            <h2>
              <span>04</span>Review rules
            </h2>
            <div>
              <div className="field-row">
                <label htmlFor="thr">
                  Send to review below
                  <small>Labels under this confidence go to a person first.</small>
                </label>
                <span style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                  <input id="thr" type="range" min={0.5} max={0.95} step={0.05} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} />
                  <span className="field-val">{threshold.toFixed(2)}</span>
                </span>
              </div>
              <div className="field-row">
                <label htmlFor="smp">
                  Quality check sample
                  <small>Share of reviewed work audited before export.</small>
                </label>
                <span style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                  <input id="smp" type="range" min={5} max={50} step={5} value={sample} onChange={(e) => setSample(Number(e.target.value))} />
                  <span className="field-val">{sample}%</span>
                </span>
              </div>
            </div>
          </div>
        </section>

        <aside className="card card-pad summary">
          <h2 className="h-section" style={{ margin: 0 }}>
            What happens next
          </h2>
          <ol>
            <li>You upload {modality === 'image' ? 'images' : modality === 'text' ? 'documents' : 'clips'}.</li>
            <li>AI drafts {task.toLowerCase()} labels for every item.</li>
            <li>Anything below {threshold.toFixed(2)} confidence goes to review.</li>
            <li>{sample}% of reviewed work is audited by QC.</li>
            <li>Approved labels are ready to export.</li>
          </ol>
          <button className="btn btn-primary" onClick={create}>
            Create project
          </button>
          <p className="muted" style={{ margin: 0, fontSize: 12.5 }}>
            Showcase only: this opens a sample project of the same kind.
          </p>
        </aside>
      </div>
    </div>
  );
}
