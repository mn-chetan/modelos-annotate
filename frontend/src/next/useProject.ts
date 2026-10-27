import { useEffect } from 'react';
import { useProjects } from './store';
import type { Route } from './router';
export function useCurrentProject(route: Route) {
  const { projects } = useProjects();
  const routeId = route.id === 'project' ? route.projectId : null;
  let remembered: string | null = null;
  try { remembered = localStorage.getItem('annotate.currentProject'); } catch {}
  const project = projects.find(p => p.id === (routeId || remembered)) || (routeId ? undefined : projects[0]);
  useEffect(() => { if (routeId && project) { try { localStorage.setItem('annotate.currentProject', routeId); } catch {} } }, [routeId, project?.id]);
  return project;
}
