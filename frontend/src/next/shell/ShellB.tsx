/*
 * Shell B — "Workbench". One top bar carries brand, project switcher and workspace links;
 * the project's views sit beneath it as tabs, so the full width goes to the work.
 */
import { useEffect, useRef, type ReactNode } from 'react';
import { motion } from 'motion/react';
import { Menu, Plus } from 'lucide-react';
import { BrandLockup } from '../../brand/BrandLockup';
import type { Project } from '../../showcase/content';
import { href, projectHref, type Route } from '../router';
import { PROJECT_TABS, WORKSPACE_ITEMS } from '../nav';
import { ProjectSwitcher } from './ProjectSwitcher';
import './shellB.css';

function WorkspaceMenu({ route }: { route: Route }) {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const close = (e: Event) => {
      const el = ref.current;
      if (el?.open && (e instanceof KeyboardEvent ? e.key === 'Escape' : !el.contains(e.target as Node))) el.open = false;
    };
    document.addEventListener('pointerdown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('pointerdown', close);
      document.removeEventListener('keydown', close);
    };
  }, []);
  return (
    <details className="rb-wmenu" ref={ref}>
      <summary className="rb-icon" aria-label="Workspace menu">
        <Menu size={18} />
      </summary>
      <div className="rb-wmenu-panel">
        {WORKSPACE_ITEMS.map(({ id, label, icon: Icon, route: to }) => (
          <a
            key={id}
            href={href(to)}
            aria-current={route.id === id ? 'page' : undefined}
            onClick={() => ref.current && (ref.current.open = false)}
          >
            <Icon size={16} aria-hidden /> {label}
          </a>
        ))}
      </div>
    </details>
  );
}

export function ShellB({ route, project, children }: { route: Route; project: Project; children: ReactNode }) {
  const inProject = route.id === 'project';

  return (
    <div className="app-b">
      <header className="rb-top">
        <div className="rb-bar">
          <a className="rb-brand" href={href({ id: 'projects' })} aria-label="ModelOS Annotate, all projects">
            <BrandLockup size="sm" />
          </a>
          <span className="rb-rule" aria-hidden />
          <ProjectSwitcher project={project} route={route} />
          <nav className="rb-links" aria-label="Workspace">
            {WORKSPACE_ITEMS.filter((w) => w.id !== 'new').map(({ id, label, route: to }) => (
              <a key={id} href={href(to)} aria-current={route.id === id ? 'page' : undefined}>
                {label}
              </a>
            ))}
          </nav>
          <span className="sample-chip">Sample data</span>
          <a className="btn btn-accent btn-sm rb-new" href={href({ id: 'new' })}>
            <Plus size={15} aria-hidden /> <span>New project</span>
          </a>
          <WorkspaceMenu route={route} />
          <span className="rb-av" title="Anika Rao · Project lead" aria-label="Signed in as Anika Rao, project lead">
            AR
          </span>
        </div>
        {inProject ? (
          <nav className="rb-tabs" aria-label="Project views">
            {PROJECT_TABS.map(({ tab, label, badge }) => {
              const on = route.tab === tab;
              const n = badge?.(project);
              return (
                <a key={tab} className="rb-tab" href={projectHref(project.id, tab)} aria-current={on ? 'page' : undefined}>
                  {label}
                  {n !== undefined ? <span className={`rb-count${n === 0 ? ' is-zero' : ''}`}>{n}</span> : null}
                  {on ? <motion.span layoutId="rb-underline" className="rb-underline" transition={{ type: 'spring', stiffness: 500, damping: 40 }} /> : null}
                </a>
              );
            })}
          </nav>
        ) : null}
      </header>
      <main className="rb-content">{children}</main>
    </div>
  );
}
