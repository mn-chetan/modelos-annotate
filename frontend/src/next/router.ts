/*
 * Hash routes for the new shell. Hash routing needs no server change while the app is
 * served under /app1/ by the backend.
 *
 *   #/projects            all projects
 *   #/projects/new        new project
 *   #/admin               administration
 *   #/p/:id[/:tab]        one project; tab defaults to overview
 *   #/p/:id/review/:item  review, opened on one item
 */
import { useSyncExternalStore } from 'react';

export type ProjectTab = 'overview' | 'ai' | 'review' | 'quality';

export type Route =
  | { id: 'projects' }
  | { id: 'new' }
  | { id: 'admin' }
  | { id: 'project'; projectId: string; tab: ProjectTab; itemId?: string };

// Reports folded into Overview; old #/p/:id/reports links fall back to it.
const TABS: readonly ProjectTab[] = ['overview', 'ai', 'review', 'quality'];

export function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
  if (parts[0] === 'projects' && parts[1] === 'new') return { id: 'new' };
  if (parts[0] === 'admin') return { id: 'admin' };
  if (parts[0] === 'p' && parts[1]) {
    const tab = TABS.includes(parts[2] as ProjectTab) ? (parts[2] as ProjectTab) : 'overview';
    return { id: 'project', projectId: parts[1], tab, itemId: tab === 'review' ? parts[3] : undefined };
  }
  return { id: 'projects' };
}

export function href(route: Route): string {
  switch (route.id) {
    case 'projects':
      return '#/projects';
    case 'new':
      return '#/projects/new';
    case 'admin':
      return '#/admin';
    case 'project':
      return `#/p/${encodeURIComponent(route.projectId)}${route.tab === 'overview' ? '' : `/${route.tab}`}${route.itemId ? `/${encodeURIComponent(route.itemId)}` : ''}`;
  }
}

export const projectHref = (projectId: string, tab: ProjectTab = 'overview', itemId?: string) =>
  href({ id: 'project', projectId, tab, itemId });

export function navigate(route: Route) {
  location.hash = href(route);
}

let navigationGuard: (() => boolean) | null = null;
export const setNavigationGuard = (guard: (() => boolean) | null) => { navigationGuard = guard; };
const subscribe = (onChange: () => void) => {
  let previous = location.hash;
  const changed = () => {
    if (location.hash === previous) return;
    if (navigationGuard && !navigationGuard()) {
      history.replaceState(null, '', previous);
      return;
    }
    previous = location.hash;
    onChange();
  };
  window.addEventListener('hashchange', changed);
  return () => window.removeEventListener('hashchange', changed);
};

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => location.hash);
  return parse(hash);
}
