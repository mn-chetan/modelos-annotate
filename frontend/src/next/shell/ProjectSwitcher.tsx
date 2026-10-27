import { useEffect, useRef } from 'react';
import { ChevronDown, FileText, Film, Image as ImageIcon, Plus, type LucideIcon } from 'lucide-react';
import { projects, type Modality, type Project } from '../../showcase/content';
import { href, projectHref, type ProjectTab, type Route } from '../router';
import { modalityLabel } from '../nav';

export const modalityIcon: Record<Modality, LucideIcon> = { image: ImageIcon, text: FileText, video: Film };

export function ProjectMark({ modality }: { modality: Modality }) {
  const Icon = modalityIcon[modality];
  return (
    <span className={`pmark is-${modality}`} aria-hidden>
      <Icon size={15} strokeWidth={1.8} />
    </span>
  );
}

/**
 * The persistent project switcher: a disclosure listing every project. Picking one keeps
 * the current tab, so moving between projects doesn't lose your place.
 */
export function ProjectSwitcher({
  project,
  route,
  onNavigate,
}: {
  project: Project;
  route: Route;
  onNavigate?: () => void;
}) {
  const ref = useRef<HTMLDetailsElement>(null);
  const tab: ProjectTab = route.id === 'project' ? route.tab : 'overview';

  useEffect(() => {
    const close = (e: Event) => {
      const el = ref.current;
      if (!el?.open) return;
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !el.contains(e.target as Node)) {
        el.open = false;
        if (e instanceof KeyboardEvent) el.querySelector('summary')?.focus();
      }
    };
    document.addEventListener('pointerdown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('pointerdown', close);
      document.removeEventListener('keydown', close);
    };
  }, []);

  const done = () => {
    if (ref.current) ref.current.open = false;
    onNavigate?.();
  };

  return (
    <details className="pswitch" ref={ref}>
      <summary className="pswitch-btn" aria-label={`Current project: ${project.name}. Switch project`}>
        <ProjectMark modality={project.modality} />
        <span className="pswitch-id">
          <span className="pswitch-name">{project.name}</span>
          <span className="pswitch-sub">
            {modalityLabel[project.modality]} · {project.task}
          </span>
        </span>
        <ChevronDown size={14} className="pswitch-caret" aria-hidden />
      </summary>
      <div className="pswitch-menu">
        <p className="pswitch-head">Switch project</p>
        <ul>
          {projects.map((p) => (
            <li key={p.id}>
              <a
                className="pswitch-item"
                href={projectHref(p.id, tab)}
                aria-current={p.id === project.id ? 'true' : undefined}
                onClick={done}
              >
                <ProjectMark modality={p.modality} />
                <span className="pswitch-id">
                  <b>{p.name}</b>
                  <small>
                    {modalityLabel[p.modality]} · {p.task}
                  </small>
                </span>
              </a>
            </li>
          ))}
        </ul>
        <div className="pswitch-divider" role="separator" />
        <a className="pswitch-item" href={href({ id: 'new' })} onClick={done}>
          <span className="pmark is-ghost" aria-hidden>
            <Plus size={15} />
          </span>
          <span className="pswitch-id">
            <b>New project</b>
            <small>Image, text or video</small>
          </span>
        </a>
      </div>
    </details>
  );
}
