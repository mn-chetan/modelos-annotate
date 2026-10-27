import { StrictMode, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { MotionConfig } from 'motion/react';
import '@fontsource-variable/inter/index.css';
import '@fontsource-variable/jetbrains-mono/index.css';
import '@fontsource-variable/newsreader/opsz.css';
import './app.css';
import { href, navigate, useRoute, type Route } from './router';
import { useCurrentProject } from './useProject';
import { ShellA } from './shell/ShellA';
import { ShellB } from './shell/ShellB';
import { ProjectsPage } from './pages/Projects';
import { NewProjectPage } from './pages/NewProject';
import { OverviewPage } from './pages/Overview';
import { AiResultsPage } from './pages/AiResults';
import { ReviewPage } from './pages/Review';
import { QualityPage } from './pages/Quality';
import { ReportsPage } from './pages/Reports';
import { AdminPage } from './pages/Admin';
import type { Project } from '../showcase/content';

const params = new URLSearchParams(location.search);
const shell = params.get('v') === 'b' ? 'b' : 'a';
const showChrome = params.get('chrome') !== '0';
const Shell = shell === 'a' ? ShellA : ShellB;

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

function Switcher({ route }: { route: Route }) {
  const options = [
    ['a', 'Review Desk'],
    ['b', 'Workbench'],
  ] as const;
  return (
    <nav className="xp-switch" aria-label="Shell directions">
      {options.map(([k, name]) => (
        <a key={k} href={`?v=${k}${href(route)}`} aria-current={k === shell ? 'page' : undefined}>
          <b>{k.toUpperCase()}</b>
          <span>{name}</span>
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
    const crumb = route.id === 'project' ? `${project.name}` : 'Projects';
    document.title = `${crumb} · ModelOS Annotate`;
  }, [route, project]);

  return (
    <MotionConfig reducedMotion="user">
      <Shell route={route} project={project}>
        {page(route, project)}
      </Shell>
      {showChrome ? <Switcher route={route} /> : null}
    </MotionConfig>
  );
}

if (!location.hash) history.replaceState(null, '', href({ id: 'projects' }));

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
