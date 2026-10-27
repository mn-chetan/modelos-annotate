import { beforeEach, afterEach, it, expect, vi } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import { BoxOverlay } from './BoxOverlay';
const annotations = Array.from({ length: 18 }, (_, i) => ({
  id: `a${i}`,
  asset_id: 'image',
  label: i % 2 ? 'person' : 'car',
  geometry_type: 'box',
  x: 10 + (i % 3),
  y: 20 + (i % 3),
  w: 8,
  h: 15,
  confidence: 0.8123,
  source: 'ai',
}));
beforeEach(() => {
  vi.spyOn(SVGElement.prototype, 'getBoundingClientRect').mockReturnValue({
    width: 960,
    height: 300,
    left: 0,
    top: 0,
  } as DOMRect);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
it('keeps names out of the stretched SVG and focuses only the selected object by default', () => {
  const { container } = render(
    <BoxOverlay
      annotations={annotations}
      colours={{ car: '#123', person: '#456' }}
      selected="a7"
    />,
  );
  expect(container.querySelectorAll('svg text')).toHaveLength(0);
  expect(container.querySelectorAll('svg [data-id]')).toHaveLength(18);
  const labels = container.querySelectorAll('.box-caption');
  expect(labels).toHaveLength(1);
  expect(labels[0].textContent).toContain('person');
  expect(labels[0].textContent).toContain('81%');
  expect(labels[0].closest('svg')).toBeNull();
});
it('spaces dense labels rather than overlapping them, while keeping every box inspectable', () => {
  const { container } = render(
    <BoxOverlay annotations={annotations} colours={{}} names selected="a17" />,
  );
  const captions = [
    ...container.querySelectorAll<HTMLElement>('.box-caption'),
  ].map((el) => ({
    x: parseFloat(el.style.left),
    y: parseFloat(el.style.top),
    w: parseFloat(el.style.width),
    h: 27,
  }));
  expect(container.querySelectorAll('svg [data-id]')).toHaveLength(18);
  expect(captions.length).toBeGreaterThan(0);
  expect(captions.length).toBeLessThan(annotations.length);
  expect(
    container.querySelector('.box-caption.is-focused')?.textContent,
  ).toContain('18');
  for (let i = 0; i < captions.length; i++)
    for (let j = i + 1; j < captions.length; j++) {
      const a = captions[i],
        b = captions[j];
      expect(
        a.x < b.x + b.w &&
          a.x + a.w > b.x &&
          a.y < b.y + b.h &&
          a.y + a.h > b.y,
      ).toBe(false);
    }
});
