/*
 * Exploration entry (dev only, not part of the app build): three New project directions
 * inside the real shell. ?v=a|b|c picks one; ?chrome=0 hides the switcher for captures.
 * Every other route renders the app's own pages, so the rail and switcher stay live.
 */
import { StrictMode, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/inter/index.css';
import '@fontsource-variable/jetbrains-mono/index.css';
import '@fontsource-variable/newsreader/opsz.css';
import '../../src/next/app.css';
import './explore.css';
import { href, navigate, useRoute, type Route } from '../../src/next/router';
import { useCurrentProject } from '../../src/next/useProject';
import { Shell } from '../../src/next/shell/Shell';
import { ProjectsPage } from '../../src/next/pages/Projects';
import { OverviewPage } from '../../src/next/pages/Overview';
import { AiResultsPage } from '../../src/next/pages/AiResults';
import { ReviewPage } from '../../src/next/pages/Review';
import { QualityPage } from '../../src/next/pages/Quality';
import { ReportsPage } from '../../src/next/pages/Reports';
import { AdminPage } from '../../src/next/pages/Admin';
import type { Project } from '../../src/showcase/content';
import BriefVariant from './BriefVariant';
import StepsVariant from './StepsVariant';
import WorkbenchVariant from './WorkbenchVariant';

const variants = {
  a: { name: 'Brief', line: 'One document', View: BriefVariant },
  b: { name: 'Steps', line: 'One question at a time', View: StepsVariant },
  c: { name: 'Workbench', line: 'Live preview', View: WorkbenchVariant },
} as const;
type Key = keyof typeof variants;

const params = new URLSearchParams(location.search);
const key: Key = (params.get('v') as Key) in variants ? (params.get('v') as Key) : 'a';
const showChrome = params.get('chrome') !== '0';
const Variant = variants[key].View;

function page(route: Route, project: Project) {
  switch (route.id) {
    case 'projects':
      return <ProjectsPage />;
    case 'new':
      return <Variant />;
    case 'admin':
      return <AdminPage />;
    case 'project':
      switch (route.tab) {
        case 'overview':
          return <OverviewPage project={project} />;
        case 'ai':
          return <AiResultsPage project={project} />;
        case 'review':
          return <ReviewPage project={project} />;
        case 'quality':
          return <QualityPage project={project} />;
        case 'reports':
          return <ReportsPage project={project} />;
      }
  }
}

function Switcher() {
  return (
    <nav className="xp-switch" aria-label="New project directions">
      {(Object.keys(variants) as Key[]).map((k) => (
        <a key={k} href={`?v=${k}#/projects/new`} aria-current={k === key ? 'page' : undefined}>
          <b>{k.toUpperCase()}</b>
          <span>
            {variants[k].name}
            <small>{variants[k].line}</small>
          </span>
        </a>
      ))}
    </nav>
  );
}

function App() {
  const route = useRoute();
  const project = useCurrentProject(route);
  const unknownProject = route.id === 'project' && route.projectId !== project.id;

  useEffect(() => {
    if (unknownProject) navigate({ id: 'projects' });
  }, [unknownProject]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [route.id, route.id === 'project' ? route.tab : '']);

  useEffect(() => {
    document.title = `${variants[key].name} · New project directions`;
  }, []);

  return (
    <Shell route={route} project={project}>
      {/* Remount per direction visit so each opens on a fresh draft. */}
      <div key={route.id}>{page(route, project)}</div>
    </Shell>
  );
}

if (!location.hash) history.replaceState(null, '', `${location.search}${href({ id: 'new' })}`);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    {showChrome ? <Switcher /> : null}
  </StrictMode>,
);
