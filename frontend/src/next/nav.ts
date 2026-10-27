/*
 * The navigation model: the single source of every label, destination and count.
 * The rail renders from it, so labels and routes are defined once.
 */
import {
  ChartColumn,
  FolderOpen,
  FolderPlus,
  House,
  ScanEye,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';
import type { Project } from '../showcase/content';
import type { ProjectTab, Route } from './router';

export type TabItem = {
  tab: ProjectTab;
  label: string;
  icon: LucideIcon;
  badge?: (p: Project) => number;
};

export const PROJECT_TABS: readonly TabItem[] = [
  { tab: 'overview', label: 'Overview', icon: House },
  { tab: 'ai', label: 'AI results', icon: Sparkles },
  { tab: 'review', label: 'Review', icon: ScanEye, badge: (p) => p.reviewPending },
  { tab: 'quality', label: 'Quality check', icon: ShieldCheck, badge: (p) => p.qcPending },
  { tab: 'reports', label: 'Reports', icon: ChartColumn },
];

export type WorkspaceItem = { id: 'projects' | 'new' | 'admin'; label: string; icon: LucideIcon; route: Route };

export const WORKSPACE_ITEMS: readonly WorkspaceItem[] = [
  { id: 'projects', label: 'All projects', icon: FolderOpen, route: { id: 'projects' } },
  { id: 'new', label: 'New project', icon: FolderPlus, route: { id: 'new' } },
  { id: 'admin', label: 'Administration', icon: SlidersHorizontal, route: { id: 'admin' } },
];

export const modalityLabel = { image: 'Image', text: 'Text', video: 'Video' } as const;

export function crumbFor(route: Route, project: Project | undefined): string[] {
  if (route.id === 'project' && project) {
    const tab = PROJECT_TABS.find((t) => t.tab === route.tab)!;
    return [project.name, tab.label];
  }
  const item = WORKSPACE_ITEMS.find((w) => w.id === route.id);
  return [item?.label ?? 'All projects'];
}
