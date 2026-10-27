/** Run from the repository root; creates one new demo project and leaves its review available. */
import { chromium } from '../node_modules/playwright/index.mjs';
import fs from 'node:fs';
import assert from 'node:assert/strict';
fs.mkdirSync('.demo', {recursive:true});
const browser=await chromium.launch({headless:true, ...(process.env.CHROMIUM_EXECUTABLE ? {executablePath:process.env.CHROMIUM_EXECUTABLE} : {}), args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(String(e)));
const root=process.env.DEMO_URL || 'http://127.0.0.1:8011';
const log=(...args)=>console.log(...args);
try{
 if(process.env.DEMO_RESUME){
  const {project_id:pid}=JSON.parse(fs.readFileSync('.demo/browser-session.json'));
  await page.goto(root+`/app1/next.html#/p/${pid}/review`);
 }else{
 await page.goto(root+'/app1/');await page.getByRole('link',{name:/Open workspace/}).first().click();
 await page.getByRole('heading',{name:'Projects',exact:true}).waitFor();log('LANDING_TO_PROJECTS');
 await page.getByRole('link',{name:'New project',exact:true}).first().click();
 await page.getByLabel('Project name',{exact:true}).fill('Browser demo verification');
 await page.locator('input[type=file]').first().setInputFiles('frontend/src/assets/images/urban_traffic_street_1790017644192.jpg');
 await page.getByRole('button',{name:'Create project',exact:true}).click();
 await page.getByRole('heading',{name:'Browser demo verification',exact:true}).waitFor({timeout:60000});
 const pid=page.url().match(/#\/p\/([^/]+)/)[1];fs.writeFileSync('.demo/browser-session.json',JSON.stringify({project_id:pid}));log('CREATED_UPLOADED',pid);
 await page.getByRole('link',{name:'Upload & run AI'}).click();
 await page.getByRole('button',{name:'Run AI',exact:true}).waitFor();
 await page.getByRole('button',{name:'Run AI',exact:true}).click();log('RUN_AI');
 await page.getByText(/1 images · 1 drafted · 0 approved/).waitFor({timeout:180000});log('ALL_MODELS_FINISHED');
 await page.screenshot({path:'.demo/ai-results-desktop.png',fullPage:true});
 await page.getByRole('link',{name:'Open review',exact:true}).click();
 }
 await page.getByRole('button',{name:'Accept remaining labels'}).waitFor();
 await page.locator('.review-image img').evaluate(img=>img.complete&&img.naturalWidth>0||new Promise(res=>img.addEventListener('load',res,{once:true})));
 await page.getByRole('button',{name:'Accept remaining labels'}).click();
 const svg=page.getByLabel('Editable image boxes');let r=await svg.boundingBox();
 await page.getByRole('button',{name:'Draw box',exact:true}).click();
 await page.mouse.move(r.x+r.width*.1,r.y+r.height*.1);await page.mouse.down();await page.mouse.move(r.x+r.width*.35,r.y+r.height*.35,{steps:5});await page.mouse.up();
 await page.getByLabel('Selected box class').selectOption('bus');
 const boxId=await page.locator('svg [data-handle="se"]').evaluate(el=>el.parentElement.getAttribute('data-id'));
 const geometry=async()=>page.locator(`svg [data-id="${boxId}"] > rect`).first().evaluate(el=>Object.fromEntries(['x','y','width','height'].map(k=>[k,+el.getAttribute(k)])));
 let g=await geometry();assert(Math.abs(g.x-10)<.5&&Math.abs(g.width-25)<.5);log('DRAWN',g);
 await page.getByLabel('Zoom',{exact:true}).fill('2');
 await page.getByRole('button',{name:'Select / move',exact:true}).click();r=await svg.boundingBox();
 const moving=page.locator(`svg [data-id="${boxId}"] > rect`).first();
 await page.mouse.move(r.x+r.width*.2,r.y+r.height*.2);await page.mouse.down();await page.mouse.move(r.x+r.width*.25,r.y+r.height*.25,{steps:5});await page.mouse.up();
 // Resize using the selected SE handle, keeping the action inside the visible viewport.
 const handle=page.locator(`svg [data-id="${boxId}"] [data-handle="se"]`);const h=await handle.boundingBox();
 await page.mouse.move(h.x+h.width/2,h.y+h.height/2);await page.mouse.down();await page.mouse.move(h.x+h.width/2+30,h.y+h.height/2+30,{steps:5});await page.mouse.up();
 g=await geometry();log('ZOOM_MOVE_RESIZE',g);
 await page.getByRole('button',{name:'Undo',exact:true}).click();await page.getByRole('button',{name:'Redo',exact:true}).click();assert.deepEqual(await geometry(),g);
 await page.getByRole('button',{name:'Fit',exact:true}).click();
 // Exercise a transport failure without dropping edits.
 await page.route('**/assets/*/annotations/batch',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Verification save failure'})}));
 await page.getByRole('button',{name:'Save edits',exact:true}).click();await page.getByRole('alert').filter({hasText:'Save failed'}).waitFor();assert.equal(await page.getByText('Unsaved edits',{exact:true}).count(),1);log('FAILED_SAVE_RETAINED');
 let dialogShown=false;page.once('dialog',async d=>{dialogShown=true;await d.dismiss();});
 await Promise.all([page.waitForEvent('dialog'),page.getByRole('link',{name:'Overview',exact:true}).click()]);
 await page.waitForURL(/\/review$/);assert(dialogShown);assert(page.url().endsWith('/review'));log('NAVIGATION_DISCARD_GUARDED');
 await page.unroute('**/assets/*/annotations/batch');
 await page.getByRole('button',{name:'Save edits',exact:true}).click();await page.getByText('Saved. Approve this image when review is complete.').waitFor({timeout:60000});log('SAVED');
 // Reload and compare actual persisted geometry by annotation ID.
 await page.reload();await page.locator(`svg [data-id="${boxId}"]`).waitFor({timeout:60000});assert.deepEqual(await geometry(),g);log('GEOMETRY_SURVIVED_RELOAD');
 await page.getByRole('button',{name:'Approve image',exact:true}).click();await page.getByText('Image approved. Accepted labels are ready to export.').waitFor({timeout:60000});
 const downloadPromise=page.waitForEvent('download');await page.getByRole('button',{name:'COCO JSON',exact:true}).click();const download=await downloadPromise;await download.saveAs('.demo/browser-coco-export.zip');log('APPROVED_EXPORTED',download.suggestedFilename());
 await page.getByRole('link',{name:'Overview',exact:true}).click();await page.getByText('1 of 1 images approved. Human approval is final in this demo.').waitFor({timeout:60000});
 await page.locator('.ov-score').nth(4).locator('.ov-score-value').filter({hasText:/^\d+$/}).waitFor({timeout:60000});
 await page.screenshot({path:'.demo/overview-loaded-desktop.png',fullPage:true});await page.setViewportSize({width:720,height:1000});await page.screenshot({path:'.demo/overview-loaded-narrow.png',fullPage:true});
 assert.equal(errors.length,0,errors.join('\n'));log('LIVE_BROWSER_FLOW_PASSED');
}catch(e){await page.screenshot({path:'.demo/browser-flow-failure.png',fullPage:true});throw e;}finally{await browser.close();}
