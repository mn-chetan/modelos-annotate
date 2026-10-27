/** Read-only visual regression: no project, label or review writes. Run from the repository root. */
import { chromium } from '../node_modules/playwright/index.mjs';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const pid = process.env.PROJECT_ID;
if (!pid)
  throw new Error(
    'Set PROJECT_ID to an image detection project containing reviewed or drafted boxes.',
  );
fs.mkdirSync('.demo', { recursive: true });
const base = process.env.DEMO_URL || 'http://127.0.0.1:8011';
const b = await chromium.launch({
  headless: true,
  ...(process.env.CHROMIUM_EXECUTABLE
    ? { executablePath: process.env.CHROMIUM_EXECUTABLE }
    : {}),
  args: ['--no-sandbox'],
});
const p = await b.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
p.on('pageerror', (e) => errors.push(String(e)));
for (const tab of ['ai', 'review']) {
  await p.goto(`${base}/app1/next.html#/p/${pid}/${tab}`);
  await p.locator('.label-select').first().waitFor({ timeout: 60000 });
  await p
    .locator(tab === 'review' ? '.review-image img' : '.image-boxes>img')
    .evaluate(
      (img) =>
        (img.complete && img.naturalWidth > 0) ||
        new Promise((r) => img.addEventListener('load', r, { once: true })),
    );
  assert.equal(await p.locator('.box-geometry text').count(), 0);
  const imageRatio = await p.locator(tab === 'review' ? '.review-image img' : '.image-boxes>img').evaluate(img => {
    const bounds=img.getBoundingClientRect();
    return Math.abs(bounds.height/bounds.width-img.naturalHeight/img.naturalWidth);
  });
  assert(imageRatio < 0.002, 'The image must retain its natural aspect ratio');
  await p.mouse.move(300, 100);
  await p.screenshot({ path: `.demo/ui-${tab}-desktop.png`, fullPage: true });
  await p.locator('.label-select').first().click();
  await p.locator('.box-caption.is-focused').waitFor();
  const firstSize = await p
    .locator('.box-caption.is-focused')
    .evaluate((el) => ({
      height: el.getBoundingClientRect().height,
      font: getComputedStyle(el).fontSize,
    }));
  assert.deepEqual(firstSize, { height: 27, font: '12px' });
  await p.screenshot({ path: `.demo/ui-${tab}-selected.png`, fullPage: true });
  if (tab === 'review') {
    await p.getByLabel('Zoom', { exact: true }).fill('2');
    const captionSize = await p
      .locator('.box-caption.is-focused')
      .evaluate((el) => ({
        height: el.getBoundingClientRect().height,
        font: getComputedStyle(el).fontSize,
      }));
    assert.deepEqual(captionSize, firstSize);
    await p.waitForFunction(() => {
      const r = document
        .querySelector('[data-handle=se]')
        .getBoundingClientRect();
      return Math.abs(r.width - 8) < 0.5 && Math.abs(r.height - 8) < 0.5;
    });
    const handle = await p.locator('[data-handle=se]').evaluate((el) => ({
      width: el.getBoundingClientRect().width,
      height: el.getBoundingClientRect().height,
    }));
    assert(
      Math.abs(handle.width - 8) < 0.5 && Math.abs(handle.height - 8) < 0.5,
    );
    console.log(
      'SCREEN_SIZED_CAPTION_HANDLES',
      captionSize,
      handle.width,
      handle.height,
    );
    await p.getByRole('button', { name: 'Fit', exact: true }).click();
  }
  if(tab === 'ai') {
    await p.getByRole('button',{name:'View original image',exact:true}).click();
    assert.equal(await p.getByLabel('AI bounding boxes').evaluate(el=>getComputedStyle(el).opacity),'0');
    await p.getByRole('button',{name:'Show bounding boxes',exact:true}).click();
    await p.getByLabel('Find predictions').fill('zzzz-no-matching-class');
    await p.getByText('No matching predictions',{exact:true}).waitFor();
    await p.getByLabel('Find predictions').fill('');
  } else {
    await p.getByRole('button',{name:'Low confidence',exact:true}).click();
    assert.equal(await p.locator('.review-labels .object-confidence:not(.is-low)').count(),0);
    await p.getByRole('button',{name:'All',exact:true}).click();
    await p.getByLabel('Find objects').fill('zzzz-no-matching-class');
    await p.getByText('No matching objects.',{exact:true}).waitFor();
    await p.getByLabel('Find objects').fill('');
  }
  await p.getByRole('checkbox', { name: 'Names', exact: true }).check();
  const overlap = await p.locator('.box-caption').evaluateAll((els) => {
    const r = els.map((el) => el.getBoundingClientRect());
    return r.some((a, i) =>
      r.some(
        (b, j) =>
          i !== j &&
          a.left < b.right &&
          a.right > b.left &&
          a.top < b.bottom &&
          a.bottom > b.top,
      ),
    );
  });
  assert(!overlap);
  console.log('SPACED_NAMES', tab, await p.locator('.box-caption').count());
  await p.screenshot({ path: `.demo/ui-${tab}-names.png`, fullPage: true });
  for (const width of [1024, 720, 390]) {
    await p.setViewportSize({ width, height: 1000 });
    await p.mouse.move(0, 0);
    await p.screenshot({
      path: `.demo/ui-${tab}-${width}.png`,
      fullPage: true,
    });
    const size = await p
      .locator('body')
      .evaluate((el) => ({ width: el.scrollWidth, viewport: innerWidth }));
    console.log('WIDTH', tab, size);
    assert(size.width === width);
  }
  await p.setViewportSize({ width: 1440, height: 1000 });
}
console.log('JS_ERRORS', errors);
assert.equal(errors.length, 0);
await b.close();
