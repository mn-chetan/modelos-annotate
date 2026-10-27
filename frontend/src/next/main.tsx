import { StrictMode, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/inter/index.css';
import '@fontsource-variable/jetbrains-mono/index.css';
import '@fontsource-variable/newsreader/opsz.css';
import './app.css';
import { href, navigate, useRoute, type Route } from './router';
import { useCurrentProject } from './useProject';
import { Shell } from './shell/Shell';
import { ProjectsPage } from './pages/Projects';
import { NewProjectPage } from './pages/new-project/NewProject';
import { OverviewPage } from './pages/Overview';
import { AiResultsPage } from './pages/AiResults';
import { ReviewPage } from './pages/Review';
import { QualityPage } from './pages/Quality';
import { ReportsPage } from './pages/Reports';
import { AdminPage } from './pages/Admin';
import type { Project } from '../showcase/content';

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
    <Shell route={route} project={project}>
      {page(route, project)}
    </Shell>
  );
}

if (!location.hash) history.replaceState(null, '', href({ id: 'projects' }));

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
