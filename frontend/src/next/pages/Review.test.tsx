import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { ReviewPage } from './Review';

const fixtures = vi.hoisted(() => ({
  persisted: [] as any[], failSave: false, failLoad: false,
  asset: { id:'image', filename:'sample.jpg', width:1000,height:500,status:'ready',review_status:'needs_review' },
  guard: null as null | (()=>boolean),
  request: vi.fn(),
}));
vi.mock('../store', () => ({
  useAssets: () => [fixtures.asset],
  getAnnotations: vi.fn(async () => { if(fixtures.failLoad)throw new Error('Disconnected');return structuredClone(fixtures.persisted); }),
  request: (...args:any[]) => fixtures.request(...args),
  refreshAssets: vi.fn(async()=>{}), refreshProjects: vi.fn(async()=>{}), exportLabels: vi.fn(),
  isApproved: (s:string) => s === 'final_approved', isDrafted:()=>true,
}));
vi.mock('../../services/api',()=>({api:{getAssetImageUrl:()=>'/sample.jpg'}}));
vi.mock('../router',()=>({setNavigationGuard:(fn:any)=>{fixtures.guard=fn;}}));
const project:any={id:'project',name:'Test',modality:'image',task:'Object detection',classes:['car','bus'],raw:{confidence_threshold:.7,label_ontology:[{name:'car',color:'#2a78d6'}]}};
let bounds={left:100,top:50,width:1000,height:500};
beforeEach(()=>{
  fixtures.persisted=[];fixtures.failSave=false;fixtures.failLoad=false;
  fixtures.request.mockImplementation(async (path,init)=>{
    if(fixtures.failSave)throw new Error('Service unavailable');
    if(path.endsWith('/annotations/batch')) fixtures.persisted=JSON.parse(init.body).annotations;
    return {status:'success'};
  });
  bounds={left:100,top:50,width:1000,height:500};
  vi.stubGlobal('PointerEvent',MouseEvent);
  Element.prototype.setPointerCapture=vi.fn();Element.prototype.hasPointerCapture=()=>false;
  vi.spyOn(SVGElement.prototype,'getBoundingClientRect').mockImplementation(()=>bounds as DOMRect);
});
afterEach(()=>{cleanup();vi.restoreAllMocks();});
async function mount(){
  const result=render(<ReviewPage project={project}/>);
  await waitFor(()=>expect((screen.getByRole('button',{name:'Draw box'}) as HTMLButtonElement).closest('fieldset')?.disabled).toBe(false));
  fireEvent.load(screen.getByAltText('sample.jpg'));
  return result;
}
function draw(x1:number,y1:number,x2:number,y2:number){
  fireEvent.click(screen.getByRole('button',{name:'Draw box'}));
  const svg=screen.getByLabelText('Editable image boxes');
  fireEvent.pointerDown(svg,{clientX:x1,clientY:y1,button:0,pointerId:1});
  fireEvent.pointerMove(svg,{clientX:x2,clientY:y2,button:0,pointerId:1});
  fireEvent.pointerUp(svg,{clientX:x2,clientY:y2,button:0,pointerId:1});
}
it('preserves natural percent geometry across zoom, moving, resizing, undo and redo',async()=>{
  const {container}=await mount();
  draw(200,100,500,300); // x=10 y=10 w=30 h=40
  expect(screen.getByText(/x 10.00/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Undo'}));
  expect(container.querySelectorAll('svg [data-id]').length).toBe(0);
  fireEvent.click(screen.getByRole('button',{name:'Redo'}));
  fireEvent.change(screen.getByLabelText('Zoom'),{target:{value:'2'}});
  expect((container.querySelector('.review-image') as HTMLElement).style.width).toBe('200%');
  bounds={left:100,top:50,width:2000,height:1000};
  fireEvent.click(screen.getByRole('button',{name:'Select / move'}));
  const svg=screen.getByLabelText('Editable image boxes');
  const rect=container.querySelector('svg [data-id] rect')!;
  fireEvent.pointerDown(rect,{clientX:400,clientY:200,button:0,pointerId:2});
  fireEvent.pointerMove(svg,{clientX:600,clientY:300,pointerId:2});
  fireEvent.pointerUp(svg,{clientX:600,clientY:300,pointerId:2}); // x20 y20, width unchanged
  expect(screen.getByText(/x 20.00/)).toBeTruthy();
  const handle=container.querySelector('[data-handle="se"]')!;
  fireEvent.pointerDown(handle,{clientX:1100,clientY:650,button:0,pointerId:3});
  fireEvent.pointerMove(svg,{clientX:3000,clientY:2000,pointerId:3});
  fireEvent.pointerUp(svg,{clientX:3000,clientY:2000,pointerId:3}); // clamp to right/bottom
  fireEvent.change(screen.getByLabelText('Selected box class'),{target:{value:'bus'}});
  fireEvent.click(screen.getByRole('button',{name:'Save edits'}));
  await waitFor(()=>expect(fixtures.persisted).toHaveLength(1));
  expect(fixtures.persisted[0]).toMatchObject({x:20,y:20,w:80,h:80,label:'bus'});
  await waitFor(()=>expect(screen.getByText('Saved')).toBeTruthy());
  expect(fixtures.request.mock.calls.every(([path])=>!path.endsWith('/review'))).toBe(true);
});
it('keeps rejected labels and unsaved edits on save failure, and guards navigation',async()=>{
  await mount();draw(200,100,500,300);
  fireEvent.click(screen.getByRole('button',{name:'Reject car'}));
  fixtures.failSave=true;
  fireEvent.click(screen.getByRole('button',{name:'Save edits'}));
  await screen.findByRole('alert');
  expect(screen.getByText('Unsaved edits')).toBeTruthy();
  expect((screen.getByRole('button',{name:'Approve image'}) as HTMLButtonElement).disabled).toBe(true);
  const submitted=JSON.parse(fixtures.request.mock.calls[0][1].body).annotations;
  expect(submitted[0]).toMatchObject({x:10,y:10,w:30,h:40,review_status:'rejected'});
  vi.spyOn(window,'confirm').mockReturnValue(false);
  expect(fixtures.guard?.()).toBe(false);
  fixtures.failSave=false;
  fireEvent.click(screen.getByRole('button',{name:'Save edits'}));
  await waitFor(()=>expect(screen.getByText('Saved')).toBeTruthy());
  expect(fixtures.persisted[0].review_status).toBe('rejected');
});
it('prevents empty approval when loading annotations failed',async()=>{
  fixtures.failLoad=true;render(<ReviewPage project={project}/>);
  await screen.findByRole('alert');fireEvent.load(screen.getByAltText('sample.jpg'));
  expect((screen.getByRole('button',{name:'Approve image'}) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole('button',{name:'Draw box'}) as HTMLButtonElement).closest('fieldset')?.disabled).toBe(true);
});
