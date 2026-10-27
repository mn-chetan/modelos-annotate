/*
 * Exploration entry (dev only, not part of the app build): three Overview directions, with
 * Reports folded in, inside the real shell. ?v=a|b|c picks one; ?chrome=0 hides the
 * switcher for captures. Reports routes land on Overview, and the rail hides the Reports
 * tab, so the information architecture reads as it would ship.
 */
import { StrictMode, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/inter/index.css';
import '@fontsource-variable/jetbrains-mono/index.css';
import '@fontsource-variable/newsreader/opsz.css';
import '../../src/next/app.css';
import './overview.css';
import { navigate, projectHref, useRoute, type Route } from '../../src/next/router';
import { useCurrentProject } from '../../src/next/useProject';
import { Shell } from '../../src/next/shell/Shell';
import { ProjectsPage } from '../../src/next/pages/Projects';
import { NewProjectPage } from '../../src/next/pages/new-project/NewProject';
import { AiResultsPage } from '../../src/next/pages/AiResults';
import { ReviewPage } from '../../src/next/pages/Review';
import { QualityPage } from '../../src/next/pages/Quality';
import { AdminPage } from '../../src/next/pages/Admin';
import type { Project } from '../../src/showcase/content';
import ReportVariant from './ReportVariant';
import FieldVariant from './FieldVariant';
import DeskVariant from './DeskVariant';
import LibraryVariant from './library/LibraryVariant';

const variants = {
  a: { name: 'Report', line: 'Read it as a document', View: ReportVariant },
  b: { name: 'Field', line: 'Explore the work itself', View: FieldVariant },
  c: { name: 'Desk', line: 'The chosen overview', View: DeskVariant },
  l: { name: 'Chart library', line: 'Pick charts to add', View: LibraryVariant },
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
      return <NewProjectPage />;
    case 'admin':
      return <AdminPage />;
    case 'project':
      switch (route.tab) {
        case 'overview':
        case 'reports':
          return <Variant project={project} />;
        case 'ai':
          return <AiResultsPage project={project} />;
        case 'review':
          return <ReviewPage project={project} />;
        case 'quality':
          return <QualityPage project={project} />;
      }
  }
}

function Switcher() {
  return (
    <nav className="xp-switch" aria-label="Overview directions">
      {(Object.keys(variants) as Key[]).map((k) => (
        <a key={k} href={`?v=${k}${location.hash}`} aria-current={k === key ? 'page' : undefined}>
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
    else if (route.id === 'project' && route.tab === 'reports') history.replaceState(null, '', `${location.search}${projectHref(project.id)}`);
  }, [unknownProject, route, project.id]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [route.id, route.id === 'project' ? route.tab : '', project.id]);

  useEffect(() => {
    document.title = `${variants[key].name} · Overview directions`;
  }, []);

  return (
    <Shell route={route} project={project}>
      <div key={`${route.id}:${project.id}`}>{page(route, project)}</div>
    </Shell>
  );
}

if (!location.hash) history.replaceState(null, '', `${location.search}${projectHref('urban-traffic')}`);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    {showChrome ? <Switcher /> : null}
  </StrictMode>,
);
