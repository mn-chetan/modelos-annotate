import { useState } from 'react';
import { Search } from 'lucide-react';
import { projects, type Modality } from '../../showcase/content';
import { navigate, projectHref } from '../router';
import { modalityLabel } from '../nav';
import { ProjectMark } from '../shell/ProjectSwitcher';
import { PageHead, fmt, pct } from './shared';

type Filter = 'all' | Modality;

export function ProjectsPage() {
  const [filter, setFilter] = useState<Filter>('all');
  const rows = projects.filter((p) => filter === 'all' || p.modality === filter);

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
          <Search size={15} aria-hidden /> Search projects
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
              <th scope="col">Lead</th>
              <th scope="col">Updated</th>
            </tr>
          </thead>
          <tbody>
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
                <td className="num">{p.qcPending ? <span className="chip is-review">{p.qcPending}</span> : <span className="muted">0</span>}</td>
                <td>{p.lead}</td>
                <td className="muted">{p.updated}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
