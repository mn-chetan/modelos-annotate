import { StrictMode, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { CloudOff, Loader2 } from 'lucide-react';
import '@fontsource-variable/inter/index.css';
import '@fontsource-variable/jetbrains-mono/index.css';
import '@fontsource-variable/newsreader/opsz.css';
import './app.css';
import { href, useRoute, type Route } from './router';
import { useCurrentProject } from './useProject';
import { Shell } from './shell/Shell';
import { ProjectsPage } from './pages/Projects';
import { NewProjectPage } from './pages/new-project/NewProject';
import { OverviewPage } from './pages/overview/Overview';
import { AiResultsPage } from './pages/ai/AiResults';
import { ReviewPage } from './pages/review/ReviewPage';
import { QualityPage } from './pages/Quality';
import { AdminPage } from './pages/Admin';
import { PageHead } from './pages/shared';
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
      if (!project) return <ProjectMissing />;
      switch (route.tab) {
        case 'overview':
          return <OverviewPage project={project} />;
        case 'ai':
          return <AiResultsPage project={project} />;
        case 'review':
          return <ReviewPage project={project} itemId={route.itemId} />;
        case 'quality':
          return <QualityPage project={project} />;
      }
  }
}

function ProjectMissing() {
  return (
    <div className="page">
      <PageHead eyebrow="Workspace" title="Project not found" lede="It may have been removed, or the link is incomplete." />
      <a className="btn btn-ghost" href={href({ id: 'projects' })}>
        All projects
      </a>
    </div>
  );
}

function Loading() {
  return (
    <div className="page">
      <p className="page-status" role="status">
        <Loader2 size={16} className="spin" aria-hidden /> Loading projects…
      </p>
    </div>
  );
}

/** The service couldn't be reached and there is nothing cached to show. */
function Unreachable({ error }: { error: string }) {
  return (
    <div className="page">
      <section className="card empty" role="alert">
        <span className="empty-icon is-fail">
          <CloudOff size={22} aria-hidden />
        </span>
        <h2>The annotation service isn’t responding</h2>
        <p>{error}</p>
        <button className="btn btn-ghost" onClick={refreshProjects}>
          Try again
        </button>
      </section>
    </div>
  );
}

function App() {
  const route = useRoute();
  const project = useCurrentProject(route);
  const { projects, loading, error } = useProjects();

  useEffect(() => {
    refreshProjects();
  }, []);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [route.id, route.id === 'project' ? route.tab : '']);

  useEffect(() => {
    const crumb =
      route.id === 'project' ? (project?.name ?? 'Project') : route.id === 'new' ? 'New project' : route.id === 'admin' ? 'Administration' : 'Projects';
    document.title = `${crumb} · ModelOS Annotate`;
  }, [route, project]);

  return (
    <Shell route={route} project={project}>
      {loading ? <Loading /> : error && !projects.length ? <Unreachable error={error} /> : page(route, project)}
    </Shell>
  );
}

if (!location.hash) history.replaceState(null, '', href({ id: 'projects' }));

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
