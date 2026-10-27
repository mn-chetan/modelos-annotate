import { useEffect } from 'react';
import { projects, type Project } from '../showcase/content';
import type { Route } from './router';

const KEY = 'annotate.currentProject';

function remembered(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/**
 * The current project follows the route, then the project last worked on, then the first
 * project, so the project tabs never empty out on workspace pages.
 */
export function useCurrentProject(route: Route): Project {
  const routeId = route.id === 'project' ? route.projectId : null;
  const id = routeId ?? remembered();
  const project = projects.find((p) => p.id === id) ?? projects[0];

  useEffect(() => {
    if (!routeId) return;
    try {
      localStorage.setItem(KEY, routeId);
    } catch {
      /* storage unavailable: the route still carries the project */
    }
  }, [routeId]);

  return project;
}
