import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { api } from '../../services/api';
import { getAnnotations, exportLabels, isApproved, isDrafted, refreshAssets, refreshProjects, request, useAssets, type Annotation, type LiveProject } from '../store';
import { PageHead, projectEyebrow } from './shared';
import { setNavigationGuard } from '../router';
import './review.css';

type Point={x:number;y:number};
type Gesture={start:Point; original:Annotation; kind:string};
const clamp=(v:number,min=0,max=100)=>Math.max(min,Math.min(max,v));
const snapshot=(rows:Annotation[])=>rows.map(a=>({...a,provenance:{...a.provenance}}));
export function ReviewPage({project:p}:{project:LiveProject}) {
  const assets=useAssets(p.id);
  const [assetId,setAssetId]=useState('');
  const asset=assets?.find(a=>a.id===assetId)||assets?.[0];
  const [rows,setRows]=useState<Annotation[]>([]);
  const [saved,setSaved]=useState('[]');
  const [selected,setSelected]=useState('');
  const [tool,setTool]=useState<'select'|'draw'>('select');
  const [label,setLabel]=useState(p.classes[0]||'');
  const [zoom,setZoom]=useState(1);
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const [loaded,setLoaded]=useState(false);
  const [imageReady,setImageReady]=useState(false);
  const [loadAttempt,setLoadAttempt]=useState(0);
  const [error,setError]=useState('');
  const [note,setNote]=useState('');
  const [past,setPast]=useState<Annotation[][]>([]),[future,setFuture]=useState<Annotation[][]>([]);
  const gesture=useRef<Gesture|null>(null);
  const svg=useRef<SVGSVGElement>(null);
  const dirty=JSON.stringify(rows)!==saved;
  const index=assets?.findIndex(a=>a.id===asset?.id)??0;
  const selectedRow=rows.find(a=>a.id===selected);
  const colours=Object.fromEntries((p.raw.label_ontology||[]).map(c=>[c.name,c.color]));
  useEffect(()=>{
    let alive=true; setLoading(true);setLoaded(false);setError('');setNote('');setRows([]);setSaved('[]');setPast([]);setFuture([]);setSelected('');
    if(!asset) {setLoading(false);return;}
    getAnnotations(asset.id).then(a=>{if(alive){setRows(a);setSaved(JSON.stringify(a));setLoading(false);setLoaded(true);}}).catch(e=>{if(alive){setError(String(e));setLoading(false);}});
    return()=>{alive=false;};
  },[asset?.id,loadAttempt]);
  useEffect(()=>{setImageReady(false);},[asset?.id]);
  useEffect(()=>{
    const confirm=()=>!dirty||window.confirm('Discard unsaved box edits?');
    setNavigationGuard(confirm);
    const before=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();e.returnValue='';}};
    window.addEventListener('beforeunload',before);
    return()=>{setNavigationGuard(null);window.removeEventListener('beforeunload',before);};
  },[dirty]);
  function change(next:Annotation[]) {setPast(h=>[...h,snapshot(rows)]);setFuture([]);setRows(next);setNote('');}
  function update(id:string,patch:Partial<Annotation>) {change(rows.map(a=>a.id===id?{...a,...patch}:a));}
  function undo(){if(!past.length||busy)return;setFuture(h=>[snapshot(rows),...h]);setRows(past[past.length-1]);setPast(h=>h.slice(0,-1));}
  function redo(){if(!future.length||busy)return;setPast(h=>[...h,snapshot(rows)]);setRows(future[0]);setFuture(h=>h.slice(1));}
  useEffect(()=>{
    const key=(e:KeyboardEvent)=>{
      if((e.target as HTMLElement).matches('input,select,textarea')||busy||loading)return;
      if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();e.shiftKey?redo():undo();}
      if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){e.preventDefault();redo();}
      if((e.key==='Delete'||e.key==='Backspace')&&selected){e.preventDefault();change(rows.filter(a=>a.id!==selected));setSelected('');}
      if(/^[1-9]$/.test(e.key) && p.classes[+e.key-1]) { setLabel(p.classes[+e.key-1]); if(selected) update(selected,{label:p.classes[+e.key-1],review_status:'edited'}); }
      if(e.key==='Escape'){setSelected('');setTool('select');}
    };
    window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);
  });
  function point(e:ReactPointerEvent):Point {
    const r=svg.current!.getBoundingClientRect();return{x:clamp((e.clientX-r.left)/r.width*100),y:clamp((e.clientY-r.top)/r.height*100)};
  }
  function down(e:ReactPointerEvent<SVGSVGElement>){
    if(busy||loading||!loaded||!imageReady||e.button!==0)return;
    const pos=point(e),target=e.target as SVGElement;
    const id=target.closest('[data-id]')?.getAttribute('data-id');
    const row=rows.find(a=>a.id===id);
    if(tool==='draw'){
      if(!label)return;
      const ann:Annotation={id:crypto.randomUUID(),asset_id:asset!.id,label,x:pos.x,y:pos.y,w:.01,h:.01,source:'human',geometry_type:'box',review_status:'approved',provenance:{}};
      change([...rows,ann]);setSelected(ann.id);gesture.current={start:pos,original:ann,kind:'draw'};
    }else if(row){
      setSelected(row.id);setPast(h=>[...h,snapshot(rows)]);setFuture([]);
      gesture.current={start:pos,original:{...row},kind:target.getAttribute('data-handle')||'move'};
    }else{setSelected('');return;}
    e.currentTarget.setPointerCapture(e.pointerId); e.preventDefault();
  }
  function move(e:ReactPointerEvent<SVGSVGElement>){
    const g=gesture.current;if(!g)return;
    const pos=point(e),a=g.original,dx=pos.x-g.start.x,dy=pos.y-g.start.y;
    let box={x:a.x,y:a.y,w:a.w,h:a.h};
    if(g.kind==='move')box={...box,x:clamp(a.x+dx,0,100-a.w),y:clamp(a.y+dy,0,100-a.h)};
    else if(g.kind==='draw')box={x:Math.min(g.start.x,pos.x),y:Math.min(g.start.y,pos.y),w:Math.max(.01,Math.abs(dx)),h:Math.max(.01,Math.abs(dy))};
    else{
      let left=a.x,top=a.y,right=a.x+a.w,bottom=a.y+a.h;
      if(g.kind.includes('w'))left=clamp(a.x+dx,0,right-.1);
      if(g.kind.includes('e'))right=clamp(a.x+a.w+dx,left+.1,100);
      if(g.kind.includes('n'))top=clamp(a.y+dy,0,bottom-.1);
      if(g.kind.includes('s'))bottom=clamp(a.y+a.h+dy,top+.1,100);
      box={x:left,y:top,w:right-left,h:bottom-top};
    }
    setRows(current=>current.map(r=>r.id===a.id?{...r,...box,review_status:'edited'}:r));
  }
  function up(e:ReactPointerEvent<SVGSVGElement>){
    const g=gesture.current;if(!g)return;
    if(g.kind==='draw')setRows(current=>current.filter(a=>a.id!==g.original.id||(a.w>=.15&&a.h>=.15)));
    gesture.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);
  }
  async function save(){
    if(!asset||busy)return;setBusy(true);setError('');setNote('');
    const submitted=snapshot(rows);
    try{
      await request(`/assets/${asset.id}/annotations/batch`,{method:'PUT',body:JSON.stringify({annotations:submitted})});
      const persisted=await getAnnotations(asset.id);setRows(persisted);setSaved(JSON.stringify(persisted));setPast([]);setFuture([]);
      await refreshAssets(p.id);await refreshProjects();setNote('Saved. Approve this image when review is complete.');
    }catch(e){setError(`Save failed. Your edits are still here. ${String(e)}`);}
    finally{setBusy(false);}
  }
  async function decide(action:'approve'|'reject'){
    if(!asset||dirty||busy)return;setBusy(true);setError('');
    try{await request(`/assets/${asset.id}/review`,{method:'POST',body:JSON.stringify({action,reviewer_id:'demo_reviewer'})});await refreshAssets(p.id);await refreshProjects();setNote(action==='approve'?'Image approved. Accepted labels are ready to export.':'Image rejected. It will not be exported.');}
    catch(e){setError(`Review was not confirmed. ${String(e)}`);}finally{setBusy(false);}
  }
  function selectAsset(id:string){if(dirty&&!window.confirm('Discard unsaved box edits?'))return;setAssetId(id);setZoom(1);}
  async function download(format:'coco'|'yolo'){try{await exportLabels(p.id,format);}catch(e){setError(String(e));}}
  if(p.modality!=='image'||p.task!=='Object detection')return <div className="page"><PageHead title="Review" lede="Review for this task is outside the image detection demo."/></div>;
  return <div className="page review-page">
    <PageHead eyebrow={projectEyebrow(p)} title="Review" lede="Select a box to move, resize or relabel it. Draw missing objects. Save edits, then explicitly approve the image." actions={<><button className="btn" onClick={()=>download('coco')}>COCO JSON</button><button className="btn" onClick={()=>download('yolo')}>YOLO</button></>}/>
    {error&&<p className="error-note" role="alert">{error} {!loaded&&<button className="btn" onClick={()=>setLoadAttempt(a=>a+1)}>Retry labels</button>}</p>}{note&&<p role="status">{note}</p>}
    {!assets?<p role="status">Loading images…</p>:!assets.length?<section className="card empty"><h2>No images to review</h2><p>Upload images in AI results.</p></section>:<>
    <div className="toolbar review-toolbar"><button className="btn btn-sm" disabled={busy||index===0} onClick={()=>selectAsset(assets[index-1].id)}>Previous</button><select aria-label="Review image" disabled={busy} value={asset?.id} onChange={e=>selectAsset(e.target.value)}>{assets.map((a,i)=><option value={a.id} key={a.id}>{i+1}. {a.filename} · {a.review_status}</option>)}</select><button className="btn btn-sm" disabled={busy||index===assets.length-1} onClick={()=>selectAsset(assets[index+1].id)}>Next</button><span className="spacer"/><span>{index+1}/{assets.length}</span><span>{asset?.review_status}</span></div>
    <fieldset className="review-tools" disabled={busy||loading||!loaded}>
      <button className="btn btn-sm" aria-pressed={tool==='select'} onClick={()=>setTool('select')}>Select / move</button><button className="btn btn-sm" aria-pressed={tool==='draw'} onClick={()=>setTool('draw')}>Draw box</button>
      <select aria-label="New box class" value={label} onChange={e=>setLabel(e.target.value)}>{p.classes.map(c=><option key={c}>{c}</option>)}</select>
      <button className="btn btn-sm" disabled={!past.length} onClick={undo}>Undo</button><button className="btn btn-sm" disabled={!future.length} onClick={redo}>Redo</button>
      <label>Zoom <input aria-label="Zoom" type="range" min="0.5" max="3" step="0.1" value={zoom} onChange={e=>setZoom(+e.target.value)}/></label><button className="btn btn-sm" onClick={()=>setZoom(1)}>Fit</button>
      <span className="spacer"/><span role="status">{dirty?'Unsaved edits':'Saved'}</span><button className="btn btn-primary btn-sm" disabled={!dirty} onClick={save}>{busy?'Saving…':'Save edits'}</button>
    </fieldset>
    <section className="card review-bench">
      <div className="review-scroll"><div className="review-image" style={{width:`${zoom*100}%`}}>
        <img src={asset?api.getAssetImageUrl(asset.id):''} alt={asset?.filename} draggable={false} onLoad={()=>setImageReady(true)} onError={()=>{setImageReady(false);setError('Image could not be loaded. Reload the image before reviewing.');}}/>
        <svg ref={svg} viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Editable image boxes" style={{cursor:tool==='draw'?'crosshair':'default'}} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
          {rows.filter(a=>(!a.geometry_type||a.geometry_type==='box')).map(a=>{const on=a.id===selected,colour=a.review_status==='rejected'?'#e31837':colours[a.label]||'#2a78d6';return <g key={a.id} data-id={a.id} style={{cursor:'move',opacity:a.review_status==='rejected'?.45:1}}>
            <rect x={a.x} y={a.y} width={a.w} height={a.h} stroke={colour} strokeWidth={on?2.5:1.5} vectorEffect="non-scaling-stroke" fill={on?'#ffffff12':'transparent'} strokeDasharray={a.review_status==='rejected'?'5 3':undefined}/>
            <text x={a.x} y={Math.max(2,a.y-.7)} fill="white" stroke="#15181e" strokeWidth=".08" fontSize="2">{a.label} {a.confidence?.toFixed(2)}</text>
            {on&&['nw','ne','sw','se'].map(corner=><rect key={corner} data-handle={corner} x={(corner.includes('w')?a.x:a.x+a.w)-.55} y={(corner.includes('n')?a.y:a.y+a.h)-.55} width="1.1" height="1.1" fill="white" stroke={colour} strokeWidth="1" vectorEffect="non-scaling-stroke" style={{cursor:`${corner}-resize`}}/>)}
          </g>;})}
        </svg>
      </div></div>
      <aside className="review-side"><h2>Labels <span className="muted">{rows.length}</span></h2>{loading?<p>Loading labels…</p>:!rows.length?<p>No boxes. Draw missing objects, or approve an empty image after inspection.</p>:null}
        <fieldset disabled={busy||loading||!loaded}>
          <button className="btn btn-sm" disabled={!rows.length} onClick={()=>change(rows.map(a=>a.review_status==='rejected'?a:{...a,review_status:'approved'}))}>Accept remaining labels</button>
          <ul className="review-labels">{rows.map(a=><li key={a.id} className={`${selected===a.id?'is-selected':''} ${a.confidence != null && a.confidence < (p.raw.confidence_threshold ?? .7) ? 'is-low-confidence' : ''}`}>
            <button className="label-select" onClick={()=>{setSelected(a.id);setTool('select');}}><b>{a.label}</b> <span>{a.confidence?.toFixed(3)??'Human'} · {a.review_status||'pending'}{a.confidence != null && a.confidence < (p.raw.confidence_threshold ?? .7) ? ' · Low confidence' : ''}</span></button>
            <div className="label-actions"><button aria-label={`Accept ${a.label}`} onClick={()=>update(a.id,{review_status:'approved'})}>Accept</button><button aria-label={`Reject ${a.label}`} onClick={()=>update(a.id,{review_status:'rejected'})}>Reject</button><button aria-label={`Delete ${a.label}`} onClick={()=>{change(rows.filter(r=>r.id!==a.id));setSelected('');}}>Delete</button></div>
          </li>)}</ul>
          {selectedRow&&<div className="box-details"><label>Class <select aria-label="Selected box class" value={selectedRow.label} onChange={e=>update(selected,{label:e.target.value,review_status:'edited'})}>{p.classes.map(c=><option key={c}>{c}</option>)}</select></label><p className="mono">x {selectedRow.x.toFixed(2)} · y {selectedRow.y.toFixed(2)}<br/>w {selectedRow.w.toFixed(2)} · h {selectedRow.h.toFixed(2)} (%)</p><p className="muted">{selectedRow.model_id||selectedRow.source}</p></div>}
        </fieldset>
      </aside>
    </section>
    <div className="review-footer"><p>{asset?.inference_error || (dirty?'Save edits before approving.':isApproved(asset?.review_status||'')?'This image is approved. Saving further edits reopens review.':'Saving does not approve this image.')}</p><div className="page-actions"><button className="btn" disabled={busy||dirty||loading||!loaded||!imageReady} onClick={()=>decide('reject')}>Reject image</button><button className="btn btn-primary" disabled={busy||dirty||loading||!loaded||!imageReady||asset?.status==='failed'||rows.some(a=>!['approved','edited','rejected'].includes(a.review_status||''))||isApproved(asset?.review_status||'')} onClick={()=>decide('approve')}>Approve image</button></div></div>
    </>}
  </div>;
}
