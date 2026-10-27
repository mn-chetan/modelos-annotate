import { StrictMode, lazy, Suspense } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/inter/index.css';
import '@fontsource-variable/jetbrains-mono/index.css';
import '@fontsource-variable/newsreader/opsz.css';
import '@fontsource-variable/newsreader/opsz-italic.css';
import './base.css';

const variants = {
  a: { name: 'Editorial', load: lazy(() => import('./a/ReviewDesk')) },
  b: { name: 'Live specimen', load: lazy(() => import('./b/LiveSpecimen')) },
  c: { name: 'Cinematic', load: lazy(() => import('./c/PipelineInMotion')) },
} as const;

type Key = keyof typeof variants;

const params = new URLSearchParams(location.search);
const key = (params.get('v') ?? 'a') as Key;
const current = variants[key] ?? variants.a;
const showChrome = params.get('chrome') !== '0';
const Variant = current.load;

document.title = `ModelOS Annotate | Tech Mahindra · ${current.name}`;

function Switcher() {
  return (
    <nav className="xp-switch" aria-label="Landing page directions">
      {(Object.keys(variants) as Key[]).map((k) => (
        <a key={k} href={`?v=${k}`} aria-current={k === key ? 'page' : undefined}>
          <b>{k.toUpperCase()}</b>
          <span>{variants[k].name}</span>
        </a>
      ))}
    </nav>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Suspense fallback={null}>
      <Variant />
    </Suspense>
    {showChrome ? <Switcher /> : null}
  </StrictMode>,
);
