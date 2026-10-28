import { useState } from 'react';
import { Search } from 'lucide-react';
import { type Modality } from '../../showcase/content';
import { useProjects } from '../store';
import { navigate, projectHref } from '../router';
import { modalityLabel } from '../nav';
import { ProjectMark } from '../shell/ProjectSwitcher';
import { PageHead, fmt, pct } from './shared';

type Filter = 'all' | Modality;

export function ProjectsPage() {
  const { projects } = useProjects();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const stamp = (p: (typeof projects)[number]) => p.raw.updated_at ?? p.raw.created_at ?? '';
  const rows = projects
    .filter((p) => (filter === 'all' || p.modality === filter) && p.name.toLowerCase().includes(query.trim().toLowerCase()))
    .sort((a, b) => stamp(b).localeCompare(stamp(a)));

  return (
    <div className="page">
      <PageHead
        eyebrow="Workspace"
        title="Projects"
        lede="Every annotation project, how far its data has come through the pipeline, and what is waiting on people."
      />
      <div className="toolbar">
        <div className="seg" role="group" aria-label="Filter by data type">
          {(['all', 'image', 'text', 'video'] as Filter[]).map((f) => (
            <button key={f} aria-pressed={filter === f} onClick={() => setFilter(f)}>
              {f === 'all' ? 'All' : modalityLabel[f]}
            </button>
          ))}
        </div>
        <span className="spacer" />
        <span className="search" role="search">
          <Search size={15} aria-hidden /> <input aria-label="Search projects" placeholder="Search projects" value={query} onChange={e => setQuery(e.target.value)} />
        </span>
      </div>
      <div className="card table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Project</th>
              <th scope="col" className="num">
                Data
              </th>
              <th scope="col">Approved</th>
              <th scope="col" className="num">
                Review
              </th>
              <th scope="col" className="num">
                QC
              </th>
              <th scope="col">Updated</th>
            </tr>
          </thead>
          <tbody>
            {!rows.length ? (
              <tr>
                <td colSpan={6} className="muted">
                  {projects.length ? 'No projects match.' : 'No projects yet. Create one to begin.'}
                </td>
              </tr>
            ) : null}
            {rows.map((p) => (
              <tr key={p.id} className="row-link" onClick={() => navigate({ id: 'project', projectId: p.id, tab: 'overview' })}>
                <td>
                  <div className="row-title">
                    <ProjectMark modality={p.modality} />
                    <div>
                      <a href={projectHref(p.id)} onClick={(e) => e.stopPropagation()}>
                        {p.name}
                      </a>
                      <small>
                        {modalityLabel[p.modality]} · {p.task}
                      </small>
                    </div>
                  </div>
                </td>
                <td className="num">
                  {fmt(p.assets)} <span className="muted">{p.unit}</span>
                </td>
                <td>
                  <div className="bar" aria-label={`${pct(p.approved, p.assets)}% approved`}>
                    <div className="bar-track">
                      <div className="bar-fill" style={{ width: `${pct(p.approved, p.assets)}%` }} />
                    </div>
                    <span>{pct(p.approved, p.assets)}%</span>
                  </div>
                </td>
                <td className="num">{p.reviewPending ? <span className="chip is-review">{p.reviewPending}</span> : <span className="muted">0</span>}</td>
                <td className="num">
                  <span className="muted" title="Quality check isn’t connected to live projects yet">—</span>
                </td>
                <td className="muted">{p.updated}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
