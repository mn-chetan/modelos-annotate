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
import { OverviewPage } from './pages/overview/Overview';
import { AiResultsPage } from './pages/AiResults';
import { ReviewPage } from './pages/Review';
import { QualityPage } from './pages/Quality';
import { AdminPage } from './pages/Admin';
import { refreshProjects, useProjects, type LiveProject } from './store';

function page(route: Route, project: LiveProject | undefined) {
  switch (route.id) {
    case 'projects':
      return <ProjectsPage />;
    case 'new':
      return <NewProjectPage />;
    case 'admin':
      return <AdminPage />;
    case 'project':
      if (!project) return <div className="card empty"><h1>Project not found</h1><a href={href({ id: 'projects' })}>All projects</a></div>;
      switch (route.tab) {
        case 'overview':
          return <OverviewPage project={project} />;
        case 'ai':
          return <AiResultsPage project={project} />;
        case 'review':
          return <ReviewPage project={project} />;
        case 'quality':
          return <QualityPage project={project} />;
      }
  }
}

function App() {
  const route = useRoute();
  const project = useCurrentProject(route);
  const { projects, loading, error } = useProjects();
  useEffect(() => { refreshProjects(); }, []);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [route.id, route.id === 'project' ? route.tab : '']);

  useEffect(() => {
    const crumb = route.id === 'project' ? `${project?.name || 'Project'}` : route.id === 'new' ? 'New project' : route.id === 'admin' ? 'Administration' : 'Projects';
    document.title = `${crumb} · ModelOS Annotate`;
  }, [route, project]);

  return (
    <Shell route={route} project={project}>
      {loading ? <p role="status">Loading projects…</p> : error && !projects.length ? <div role="alert" className="card empty"><h2>Service unavailable</h2><p>{error}</p><button className="btn" onClick={refreshProjects}>Retry</button></div> : <>{error && <p role="alert">{error} <button className="btn" onClick={refreshProjects}>Retry connection</button></p>}{page(route, project)}</>}
    </Shell>
  );
}

if (!location.hash) history.replaceState(null, '', href({ id: 'projects' }));

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
