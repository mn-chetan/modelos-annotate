import { useEffect, useState } from 'react';
import { ArrowRight, Download, Link2 } from 'lucide-react';
import { getAnnotations, exportLabels, isDrafted, isApproved, needsReview, useAssets, type Annotation, type LiveProject } from '../../store';
import { projectHref } from '../../router';
import { fmt, pct, projectEyebrow } from '../shared';
import { Figure } from './charts';
import './overview.css';

export function OverviewPage({ project: p }: { project: LiveProject }) {
  const assets = useAssets(p.id);
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  useEffect(() => {
    let alive = true; setLoaded(false);
    if (assets) Promise.all(assets.map(a => getAnnotations(a.id))).then(rows => { if(alive) {setAnnotations(rows.flat());setLoaded(true);} }).catch(e=>{if(alive)setError(String(e));});
    return () => {alive=false;};
  }, [p.id, assets]);
  const total=assets?.length || 0, drafted=assets?.filter(isDrafted).length || 0, approved=assets?.filter(a=>isApproved(a.review_status)).length || 0;
  const pending=assets?.filter(needsReview).length || 0;
  const rejected=annotations.filter(a=>a.review_status==='rejected').length;
  const reviewed=annotations.filter(a=>['approved','rejected','edited'].includes(a.review_status || ''));
  const aiReviewed=reviewed.filter(a=>a.source==='ai'||!!a.model_id);
  const unchanged=aiReviewed.filter(a=>a.review_status==='approved' && !a.provenance?.human_edited && a.source==='ai').length;
  const mixups = new Map<string, number>();
  for (const a of annotations) {
    const before = a.provenance?.original_ai_label;
    if (typeof before === 'string' && before !== a.label) {
      const key = `${before} → ${a.label}`; mixups.set(key, (mixups.get(key) || 0) + 1);
    }
  }
  const corrections = annotations.filter(a => a.provenance?.human_edited).length;
  const hardest = [...(assets || [])].filter(a => a.mean_confidence != null).sort((a,b) => a.mean_confidence! - b.mean_confidence!).slice(0,5);
  const scores=[['Total '+p.unit,total],['Annotated by AI',drafted],['Waiting for review',pending],['Approved',approved],['Labels',loaded ? annotations.length : '—'],['AI labels kept',aiReviewed.length ? `${pct(unchanged,aiReviewed.length)}%` : '—']];
  async function download(format: 'coco'|'yolo') {setError('');try {await exportLabels(p.id,format);}catch(e){setError(String(e));}}
  return <div className="ov">
    <header className="ov-head"><div><p className="page-eyebrow">{projectEyebrow(p)}</p><h1 className="page-title">{p.name}</h1><p className="page-lede">{assets ? `${approved} of ${total} ${p.unit} approved. Human approval is final in this demo.` : 'Loading persisted project results…'}</p></div>
      <div className="page-actions"><button className="btn btn-ghost btn-sm" onClick={async()=>{try{await navigator.clipboard.writeText(location.href);setNote('Link copied');}catch{setNote('Copy the address bar to share.');}}}><Link2 size={15}/> Share</button><a className="btn btn-primary" href={projectHref(p.id,'ai')}>Upload & run AI <ArrowRight size={15}/></a><a className="btn" href={projectHref(p.id,'review')}>Open review</a></div>
    </header>
    {error&&<p role="alert">{error}</p>}{note&&<p role="status">{note}</p>}
    <section className="ov-scores" aria-label="Scorecards">{scores.map(([label,value])=><div className="ov-score" key={label}><p className="ov-score-label">{label}</p><p className="ov-score-value">{assets ? value : '—'}</p><p className="ov-score-share">{label==='AI labels kept' ? (aiReviewed.length ? `${aiReviewed.length} explicit AI label decisions; not ground-truth accuracy` : 'No label review evidence yet') : 'Persisted project data'}</p><span className="ov-score-meter"><span style={{flexGrow:1,background:label==='Approved'?'#1f8a5b':'var(--ink)'}} /></span></div>)}</section>
    <section className="ov-row is-1-1"><Figure title="Review routing"><p>All demo images require human approval. Low confidence is highlighted at {p.raw.confidence_threshold ?? 0.7}.</p><p>{drafted} drafted · {pending} waiting · {approved} approved</p><div className="bar-track"><div className="bar-fill" style={{width:`${pct(approved,total)}%`}} /></div></Figure>
      <Figure title="Can we trust the AI’s confidence?"><p className="muted">Calibration unavailable. A confidence score is model evidence; accuracy needs reviewed ground truth across enough examples.</p></Figure></section>
    <section className="ov-row is-1"><Figure title="Labels by class" sub="Counts from saved annotations; rejected labels are excluded from exports."><div className="ov-table-wrap"><table className="table"><thead><tr><th>Class</th><th>Labels</th><th>Reviewed</th><th>Rejected</th></tr></thead><tbody>{p.classes.map(c=><tr key={c}><td>{c}</td><td>{loaded?annotations.filter(a=>a.label===c).length:'—'}</td><td>{loaded?reviewed.filter(a=>a.label===c).length:'—'}</td><td>{loaded?annotations.filter(a=>a.label===c&&a.review_status==='rejected').length:'—'}</td></tr>)}</tbody></table></div></Figure></section>
    <section className="ov-row is-1-1"><Figure title="Most common mix-ups"><p>Saved changes from the original AI class to the reviewed class.</p>{mixups.size ? <div className="ov-table-wrap"><table className="table"><tbody>{[...mixups].sort((a,b)=>b[1]-a[1]).map(([label,n])=><tr key={label}><td>{label}</td><td>{n}</td></tr>)}</tbody></table></div> : <p className="muted">No saved class corrections yet.</p>}</Figure><Figure title="What kind of fixes reviewers make"><p>{corrections} labels with saved class or geometry corrections.</p><p>{rejected} rejected labels · {reviewed.length} explicit label decisions</p><p className="muted">Deleted labels are excluded from current counts.</p></Figure></section>
    <section className="ov-row is-1"><Figure title="Hardest items" sub="Lowest recorded mean model confidence. Confidence is not measured accuracy."><div className="ov-table-wrap"><table className="table"><thead><tr><th>Image</th><th>Confidence</th><th>Review</th></tr></thead><tbody>{hardest.length ? hardest.map(a=><tr key={a.id}><td>{a.filename}</td><td>{a.mean_confidence?.toFixed(3)}</td><td>{a.review_status}</td></tr>) : <tr><td colSpan={3}>No model confidence recorded yet.</td></tr>}</tbody></table></div></Figure></section>
    <section className="ov-row is-1-1"><Figure title="Reviewers"><p className="muted">Reviewer speed and agreement are unavailable until sufficient attributed review evidence exists.</p></Figure><Figure title="Who corrects which classes"><p className="muted">Per-reviewer class comparisons are unavailable in this demo.</p></Figure></section>
    <section className="card card-pad"><h2 className="h-section">Approved export</h2><p>{approved} approved images. Export includes accepted labels and reviewed geometry.</p><div className="page-actions"><button className="btn" disabled={!approved} onClick={()=>download('coco')}><Download size={15}/> COCO JSON</button><button className="btn" disabled={!approved} onClick={()=>download('yolo')}><Download size={15}/> YOLO</button></div></section>
    <p className="ov-sample-note">Counts come from persisted assets, labels and explicit review decisions. QC sampling is bypassed in this demo.</p>
  </div>;
}
