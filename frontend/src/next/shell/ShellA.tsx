/*
 * Shell A — "Review Desk". Concept-07's rail: brand, project switcher, the project's
 * views, then workspace items. The rail becomes a drawer below 1024px.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Menu, Plus, X } from 'lucide-react';
import { BrandLockup } from '../../brand/BrandLockup';
import type { Project } from '../../showcase/content';
import { href, projectHref, type Route } from '../router';
import { PROJECT_TABS, WORKSPACE_ITEMS, crumbFor } from '../nav';
import { ProjectSwitcher } from './ProjectSwitcher';
import './shellA.css';

function RailContents({ route, project, onNavigate }: { route: Route; project: Project; onNavigate?: () => void }) {
  return (
    <>
      <a className="ra-brand" href={href({ id: 'projects' })} aria-label="ModelOS Annotate, all projects" onClick={onNavigate}>
        <BrandLockup stacked />
      </a>
      <ProjectSwitcher project={project} route={route} onNavigate={onNavigate} />
      <nav className="ra-nav" aria-label="Main">
        <p className="ra-group">This project</p>
        <ul>
          {PROJECT_TABS.map(({ tab, label, icon: Icon, badge }) => {
            const on = route.id === 'project' && route.tab === tab;
            const n = badge?.(project);
            return (
              <li key={tab}>
                <a className="ra-link" href={projectHref(project.id, tab)} aria-current={on ? 'page' : undefined} onClick={onNavigate}>
                  <Icon size={16} strokeWidth={1.7} aria-hidden />
                  <span>{label}</span>
                  {n !== undefined ? (
                    <span className={`ra-count${n === 0 ? ' is-zero' : ''}`} aria-label={`${n} waiting`}>
                      {n}
                    </span>
                  ) : null}
                </a>
              </li>
            );
          })}
        </ul>
        <p className="ra-group">Workspace</p>
        <ul>
          {WORKSPACE_ITEMS.map(({ id, label, icon: Icon, route: to }) => (
            <li key={id}>
              <a className="ra-link" href={href(to)} aria-current={route.id === id ? 'page' : undefined} onClick={onNavigate}>
                <Icon size={16} strokeWidth={1.7} aria-hidden />
                <span>{label}</span>
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <div className="ra-foot">
        <span className="ra-av" aria-hidden>
          AR
        </span>
        <div>
          Anika Rao
          <small>Project lead</small>
        </div>
      </div>
    </>
  );
}

export function ShellA({ route, project, children }: { route: Route; project: Project; children: ReactNode }) {
  const [drawer, setDrawer] = useState(false);
  const menuBtn = useRef<HTMLButtonElement>(null);
  const crumbs = crumbFor(route, project);

  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setDrawer(false);
        menuBtn.current?.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [drawer]);

  return (
    <div className="app-a">
      <aside className="ra-rail">
        <RailContents route={route} project={project} />
      </aside>

      {drawer ? (
        <div className="ra-drawer" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="ra-scrim" onClick={() => setDrawer(false)} />
          <div className="ra-drawer-panel">
            <button className="ra-icon ra-drawer-close" onClick={() => setDrawer(false)} aria-label="Close navigation" autoFocus>
              <X size={18} />
            </button>
            <RailContents route={route} project={project} onNavigate={() => setDrawer(false)} />
          </div>
        </div>
      ) : null}

      <div className="ra-main">
        <header className="ra-top">
          <button ref={menuBtn} className="ra-icon ra-menu" onClick={() => setDrawer(true)} aria-label="Open navigation">
            <Menu size={18} />
          </button>
          <span className="ra-top-brand">
            <BrandLockup size="sm" product={false} />
          </span>
          <ol className="ra-crumbs" aria-label="Breadcrumb">
            {crumbs.map((c, i) => (
              <li key={c} aria-current={i === crumbs.length - 1 ? 'page' : undefined}>
                {c}
              </li>
            ))}
          </ol>
          <span className="sample-chip">Sample data</span>
          <a className="btn btn-primary btn-sm" href={href({ id: 'new' })}>
            <Plus size={15} aria-hidden /> <span>New project</span>
          </a>
        </header>
        <main className="ra-content">{children}</main>
      </div>
    </div>
  );
}
