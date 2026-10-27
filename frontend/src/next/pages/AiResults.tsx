import { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { getAnnotations, isApproved, isDrafted, refreshAssets, refreshProjects, request, useAssets, type Annotation, type LiveProject } from '../store';
import { projectHref } from '../router';
import { PageHead, projectEyebrow } from './shared';
import { ImageBoxes } from './ImageBoxes';

type Batch = { id: string; status: string; total: number; completed: number; failed: number; completed_items?: number; succeeded_items?: number; failed_items?: number; error_summary?: string; items?: { asset_id: string; status: string; error_message?: string }[] };
export function AiResultsPage({ project: p }: { project: LiveProject }) {
  const assets = useAssets(p.id);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [selected, setSelected] = useState('');
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const active = batches.some(b => ['queued','running'].includes(b.status));
  const asset = assets?.find(a => a.id === selected) || assets?.[0];
  async function poll() {
    const rows = await request<Batch[]>(`/projects/${p.id}/batches`);
    setBatches(rows); return rows;
  }
  useEffect(() => {
    let alive = true, timer: ReturnType<typeof setTimeout>;
    async function tick() {
      try {
        const rows = await request<Batch[]>(`/projects/${p.id}/batches`);
        if (!alive) return;
        setBatches(rows);
        await refreshAssets(p.id);
        if (alive) timer = setTimeout(tick, rows.some(b => ['queued','running'].includes(b.status)) ? 2500 : 10000);
      } catch(e) { if (alive) { setError(String(e)); timer = setTimeout(tick, 5000); } }
    }
    tick(); return () => { alive = false; clearTimeout(timer); };
  }, [p.id]);
  useEffect(() => {
    if (!asset) return;
    let alive = true;
    getAnnotations(asset.id).then(a => { if (alive) setAnnotations(a); }).catch(e => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [asset?.id, asset?.updated_at]);
  async function run() {
    setBusy(true); setError('');
    try { await api.triggerAiAnnotation(p.id); await poll(); await refreshAssets(p.id); }
    catch(e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function upload(files: File[]) {
    setBusy(true); setError('');
    try {
      for (let i=0;i<files.length;i++) {
        await api.uploadAssets(p.id, [files[i]]);
        setNote(`${i+1} of ${files.length} files uploaded`);
      }
    } catch(e) { setError(`Upload stopped. Successfully uploaded files are saved. ${String(e)}`); }
    finally { await refreshAssets(p.id); await refreshProjects(); setBusy(false); }
  }
  if (p.modality !== 'image' || p.task !== 'Object detection') return <div className="page"><PageHead title="AI results" lede="Processing this task is outside the image detection demo." /></div>;
  return <div className="page">
    <PageHead eyebrow={projectEyebrow(p)} title="AI results" lede="Florence describes the image; YOLO26 and Grounding DINO draft boxes using your classes. Every image requires human approval." actions={<>
      <label className="btn btn-ghost">Upload images<input disabled={busy || active} style={{display:'none'}} type="file" accept="image/*" multiple onChange={e => { const fs=Array.from(e.target.files || []); e.target.value=''; upload(fs); }} /></label>
      <button className="btn btn-primary" disabled={busy || active || !assets?.some(a => ['uploaded','failed'].includes(a.status))} onClick={run}>{active ? 'AI running…' : 'Run AI'}</button>
      <a className="btn" href={projectHref(p.id,'review')}>Open review</a>
    </>} />
    {error && <p role="alert" className="error-note">{error}</p>}{note && <p role="status">{note}</p>}
    <div className="card card-pad" aria-live="polite">{!assets ? 'Loading images…' : `${assets.length} images · ${assets.filter(isDrafted).length} drafted · ${assets.filter(a=>isApproved(a.review_status)).length} approved`}
      {batches.slice(0,3).map(b => <p key={b.id}>Batch {b.id.slice(0,8)} · {b.status} · {b.items?.filter(i => ['succeeded','failed','human_review'].includes(i.status)).length ?? b.completed ?? 0}/{b.total || b.items?.length || 0} finished {b.error_summary && <span role="alert">· {b.error_summary}</span>}</p>)}
    </div>
    {!assets?.length ? <section className="card empty"><h2>Add your first images</h2><p>Upload images, then choose Run AI.</p></section> : <section className="card result-grid">
      <aside className="asset-list">{assets.map(a => <button key={a.id} className={asset?.id===a.id?'is-selected':''} onClick={()=>setSelected(a.id)}><b>{a.filename}</b><small>{a.inference_error ? 'Inference failed' : a.status} · {a.annotation_count || 0} labels</small></button>)}</aside>
      <div className="result-detail">{asset && <><ImageBoxes asset={asset} annotations={annotations} /><p>{asset.caption || (isDrafted(asset) ? 'No caption recorded.' : 'AI has not completed this image.')}</p>{asset.inference_error && <p role="alert">{asset.inference_error}</p>}
      {isDrafted(asset) && annotations.length === 0 && <p>No detections found. Review the image before approving an empty result.</p>}
      <table className="table"><thead><tr><th>Class</th><th>Confidence</th><th>Model</th><th>Decision</th></tr></thead><tbody>{annotations.map(a=><tr key={a.id}><td>{a.label}</td><td>{a.confidence?.toFixed(3) ?? 'Human'}</td><td>{a.model_id || a.source}</td><td>{a.review_status || 'pending'}</td></tr>)}</tbody></table></>}</div>
    </section>}
  </div>;
}
