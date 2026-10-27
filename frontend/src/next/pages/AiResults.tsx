import { useEffect, useState } from 'react';
import {
  ArrowRight,
  Check,
  CircleAlert,
  Image as ImageIcon,
  Loader2,
  Play,
  Plus,
  Search,
  Sparkles,
} from 'lucide-react';
import { api } from '../../services/api';
import {
  getAnnotations,
  isApproved,
  isDrafted,
  refreshAssets,
  refreshProjects,
  request,
  useAssets,
  type Annotation,
  type LiveProject,
} from '../store';
import { projectHref } from '../router';
import { PageHead, projectEyebrow } from './shared';
import { ImageBoxes } from './ImageBoxes';
import {
  classColours,
  colourStyle,
  DecisionBadge,
  modelName,
} from './annotation-ui';

type Batch = {
  id: string;
  status: string;
  total: number;
  completed: number;
  failed: number;
  error_summary?: string;
  items?: { asset_id: string; status: string; error_message?: string }[];
};
export function AiResultsPage({ project: p }: { project: LiveProject }) {
  const assets = useAssets(p.id);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [selected, setSelected] = useState('');
  const [focused, setFocused] = useState('');
  const [hovered, setHovered] = useState('');
  const [query, setQuery] = useState('');
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [loadingLabels, setLoadingLabels] = useState(true);
  const [activity, setActivity] = useState<'run' | 'upload' | null>(null);
  const busy = activity !== null;
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const active = batches.some((b) => ['queued', 'running'].includes(b.status));
  const asset = assets?.find((a) => a.id === selected) || assets?.[0];
  const colours = classColours(p.classes, p.raw.label_ontology);
  const object = annotations.find((a) => a.id === focused);
  const latest = batches[0];
  const predictions = annotations.filter((a) =>
    a.label.toLowerCase().includes(query.toLowerCase()),
  );
  async function poll() {
    const rows = await request<Batch[]>(`/projects/${p.id}/batches`);
    setBatches(rows);
    return rows;
  }
  useEffect(() => {
    let alive = true,
      timer: ReturnType<typeof setTimeout>;
    async function tick() {
      try {
        const rows = await request<Batch[]>(`/projects/${p.id}/batches`);
        if (!alive) return;
        setBatches(rows);
        await refreshAssets(p.id);
        if (alive)
          timer = setTimeout(
            tick,
            rows.some((b) => ['queued', 'running'].includes(b.status))
              ? 2500
              : 10000,
          );
      } catch (e) {
        if (alive) {
          setError(String(e));
          timer = setTimeout(tick, 5000);
        }
      }
    }
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [p.id]);
  useEffect(() => {
    if (!asset) return;
    let alive = true;
    setLoadingLabels(true);
    getAnnotations(asset.id)
      .then((a) => {
        if (alive) {
          setAnnotations(a);
          setFocused((id) => (a.some((row) => row.id === id) ? id : ''));
          setLoadingLabels(false);
        }
      })
      .catch((e) => {
        if (alive) {
          setError(String(e));
          setLoadingLabels(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [asset?.id, asset?.updated_at]);
  useEffect(() => {
    const clear = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setFocused('');
        setHovered('');
      }
    };
    window.addEventListener('keydown', clear);
    return () => window.removeEventListener('keydown', clear);
  }, []);
  async function run() {
    setActivity('run');
    setError('');
    try {
      await api.triggerAiAnnotation(p.id);
      await poll();
      await refreshAssets(p.id);
    } catch (e) {
      setError(String(e));
    } finally {
      setActivity(null);
    }
  }
  async function upload(files: File[]) {
    setActivity('upload');
    setError('');
    try {
      for (let i = 0; i < files.length; i++) {
        await api.uploadAssets(p.id, [files[i]]);
        setNote(`${i + 1} of ${files.length} files uploaded`);
      }
    } catch (e) {
      setError(
        `Upload stopped. Successfully uploaded files are saved. ${String(e)}`,
      );
    } finally {
      await refreshAssets(p.id);
      await refreshProjects();
      setActivity(null);
    }
  }
  function selectAsset(id: string) {
    setSelected(id);
    setFocused('');
    setHovered('');
    setAnnotations([]);
    setQuery('');
  }
  if (p.modality !== 'image' || p.task !== 'Object detection')
    return (
      <div className="page">
        <PageHead
          title="AI results"
          lede="Processing this task is outside the image detection demo."
        />
      </div>
    );
  return (
    <div className="page ai-results-page">
      <PageHead
        eyebrow={projectEyebrow(p)}
        title="AI results"
        lede={
          active
            ? 'AI is drafting your labels. Results appear here as each image finishes.'
            : assets?.some(isDrafted)
              ? 'The first pass is ready for a closer look. Inspect a prediction, then make it yours in review.'
              : 'Start with your images. Let AI draft boxes, then review every label.'
        }
        actions={
          <>
            <label
              className={`btn btn-ghost${busy || active ? ' is-disabled' : ''}`}
            >
              {activity === 'upload' ? (
                <Loader2 size={15} className="spin" />
              ) : (
                <Plus size={15} />
              )}
              {activity === 'upload' ? 'Uploading…' : 'Upload images'}
              <input
                disabled={busy || active}
                style={{ display: 'none' }}
                type="file"
                accept="image/*"
                multiple
                onChange={(e) => {
                  const fs = Array.from(e.target.files || []);
                  e.target.value = '';
                  upload(fs);
                }}
              />
            </label>
            <button
              className="btn btn-ghost"
              disabled={
                busy ||
                active ||
                !assets?.some((a) => ['uploaded', 'failed'].includes(a.status))
              }
              onClick={run}
            >
              {active || activity === 'run' ? (
                <Loader2 size={15} className="spin" />
              ) : (
                <Play size={14} />
              )}{' '}
              {active
                ? 'AI running…'
                : activity === 'run'
                  ? 'Starting…'
                  : 'Run AI'}
            </button>
            <a className="btn btn-primary" href={projectHref(p.id, 'review')}>
              Open review
              <ArrowRight size={15} />
            </a>
          </>
        }
      />
      {error && (
        <p role="alert" className="error-note">
          <CircleAlert size={16} />
          {error}
        </p>
      )}
      {note && (
        <p role="status" className="success-note">
          <Check size={15} />
          {note}
        </p>
      )}
      <div className="results-summary" aria-live="polite">
        <div className="results-counts">
          {!assets ? (
            <span>Loading images…</span>
          ) : (
            <>
              <span>
                <b>{assets.length}</b>{' '}
                {assets.length === 1 ? 'image' : 'images'}
              </span>
              <span>
                <b>{assets.filter(isDrafted).length}</b> drafted
              </span>
              <span>
                <b>
                  {assets.filter((a) => isApproved(a.review_status)).length}
                </b>{' '}
                approved
              </span>
            </>
          )}
        </div>
        <span className="results-human-note">
          <Check size={13} />
          Human approval required
        </span>
      </div>
      {active && latest && (
        <div className="batch-progress" role="status">
          <Loader2 size={17} className="spin" />
          <div>
            <b>Drafting your annotations</b>
            <span>
              {latest.completed + latest.failed} of {latest.total} images
              finished
            </span>
          </div>
          <progress
            value={latest.completed + latest.failed}
            max={Math.max(1, latest.total)}
          />
        </div>
      )}
      {latest?.error_summary && (
        <details className="batch-error">
          <summary>
            <CircleAlert size={14} />A run needs attention
          </summary>
          <p>{latest.error_summary}</p>
        </details>
      )}
      {!assets ? (
        <section className="card empty" role="status">
          <Loader2 className="spin" size={22} />
          <p>Loading your images…</p>
        </section>
      ) : !assets.length ? (
        <section className="card empty">
          <span className="upload-empty-icon">
            <ImageIcon size={28} />
          </span>
          <h2>Your images start here</h2>
          <p>
            Upload a few images, then run AI to draft the first set of labels.
          </p>
        </section>
      ) : (
        <section className="results-workbench">
          <aside className="asset-list">
            <div className="asset-list-head">
              Images <span>{assets.length}</span>
            </div>
            {assets.map((a, i) => (
              <button
                key={a.id}
                className={asset?.id === a.id ? 'is-selected' : ''}
                aria-current={asset?.id === a.id ? 'true' : undefined}
                onClick={() => selectAsset(a.id)}
              >
                <span className="asset-thumbnail">
                  <ImageIcon size={20} />
                  <img
                    src={api.getAssetPreviewUrl(a.id)}
                    alt=""
                    loading="lazy"
                    onError={(e) => {
                      e.currentTarget.style.visibility = 'hidden';
                    }}
                  />
                  <span>{String(i + 1).padStart(2, '0')}</span>
                </span>
                <b title={a.filename}>{a.filename}</b>
                <small>
                  <i
                    className={
                      a.inference_error
                        ? 'is-failed'
                        : isDrafted(a)
                          ? 'is-ready'
                          : ''
                    }
                  />
                  {a.inference_error
                    ? 'Failed'
                    : isDrafted(a)
                      ? `${a.annotation_count || 0} labels`
                      : 'Not processed'}
                </small>
              </button>
            ))}
          </aside>
          <div className="result-detail">
            {asset && (
              <>
                <div className="result-image-head">
                  <div>
                    <h2 title={asset.filename}>{asset.filename}</h2>
                    <span>
                      Image {assets.indexOf(asset) + 1} of {assets.length}
                    </span>
                  </div>
                  <DecisionBadge status={asset.review_status} />
                </div>
                <ImageBoxes
                  asset={asset}
                  annotations={annotations}
                  colours={colours}
                  selected={focused}
                  hovered={hovered}
                  onSelect={setFocused}
                  onHover={setHovered}
                />
                <div className="class-legend" aria-label="Detected classes">
                  {p.classes.map((c) => (
                    <span key={c} style={colourStyle(colours[c])}>
                      <i />
                      {c}
                      <b>
                        {
                          annotations.filter(
                            (a) =>
                              a.label === c && a.review_status !== 'rejected',
                          ).length
                        }
                      </b>
                    </span>
                  ))}
                </div>
                {asset.inference_error ? (
                  <p role="alert" className="error-note">
                    {asset.inference_error}
                  </p>
                ) : (
                  <div className="caption-note">
                    <Sparkles size={15} />
                    <div>
                      <span>AI scene note</span>
                      <p>
                        {asset.caption ||
                          (isDrafted(asset)
                            ? 'No caption saved for this image.'
                            : 'Run AI to draft labels and a scene description.')}
                      </p>
                    </div>
                  </div>
                )}
                {!loadingLabels && isDrafted(asset) && !annotations.length && (
                  <p className="result-empty-note">
                    No detections found. Inspect the image in review before
                    approving an empty result.
                  </p>
                )}
              </>
            )}
          </div>
          <aside className="predictions-panel">
            <div className="objects-head">
              <h2>
                Predictions <span>{annotations.length}</span>
              </h2>
              <Sparkles size={15} />
            </div>
            <label className="object-search">
              <Search size={14} />
              <input
                aria-label="Find predictions"
                placeholder="Find a class…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            <ul className="prediction-list">
              {loadingLabels ? (
                <li className="object-empty">Loading predictions…</li>
              ) : !predictions.length ? (
                <li className="object-empty">
                  <ImageIcon size={23} />
                  <b>
                    {annotations.length
                      ? 'No matching predictions'
                      : asset && isDrafted(asset)
                        ? 'No detections'
                        : 'No predictions yet'}
                  </b>
                  <span>
                    {annotations.length
                      ? 'Try a different class name.'
                      : 'Your image stays available for human review.'}
                  </span>
                </li>
              ) : (
                predictions.map((a) => (
                  <li
                    key={a.id}
                    className={`${a.id === focused ? 'is-selected' : ''} ${a.review_status === 'rejected' ? 'is-rejected' : ''}`}
                    style={colourStyle(colours[a.label])}
                    onMouseEnter={() => setHovered(a.id)}
                    onMouseLeave={() => setHovered('')}
                  >
                    <button
                      className="label-select"
                      aria-pressed={a.id === focused}
                      onClick={() => setFocused(a.id)}
                    >
                      <span className="object-number">
                        {String(annotations.indexOf(a) + 1).padStart(2, '0')}
                      </span>
                      <span className="object-name">
                        <b title={a.label}>{a.label}</b>
                        <small>{modelName(a)}</small>
                      </span>
                      <span
                        className={`object-confidence${a.confidence != null && a.confidence < (p.raw.confidence_threshold ?? 0.7) ? ' is-low' : ''}`}
                      >
                        {a.confidence == null
                          ? 'Human'
                          : `${Math.round(a.confidence * 100)}%`}
                      </span>
                    </button>
                  </li>
                ))
              )}
            </ul>
            <div className="prediction-inspector">
              {object ? (
                <>
                  <div className="inspector-heading">
                    <span>Model evidence</span>
                    <b>
                      #
                      {String(annotations.indexOf(object) + 1).padStart(2, '0')}
                    </b>
                  </div>
                  <h3>{object.label}</h3>
                  <div className="evidence-row">
                    <span>Confidence</span>
                    <b>
                      {object.confidence == null
                        ? 'Human'
                        : `${(object.confidence * 100).toFixed(1)}%`}
                    </b>
                  </div>
                  <div className="confidence-track">
                    <i
                      style={{
                        width: `${(object.confidence || 0) * 100}%`,
                        background: colours[object.label],
                      }}
                    />
                  </div>
                  <div className="evidence-row">
                    <span>Source</span>
                    <b>{modelName(object)}</b>
                  </div>
                  <DecisionBadge status={object.review_status} />
                  <a
                    className="inspector-review-link"
                    href={projectHref(p.id, 'review')}
                  >
                    Correct in review
                    <ArrowRight size={13} />
                  </a>
                </>
              ) : (
                <div className="inspector-placeholder">
                  <ImageIcon size={18} />
                  <p>
                    Select a prediction to inspect its confidence and source.
                  </p>
                </div>
              )}
            </div>
          </aside>
        </section>
      )}
    </div>
  );
}
