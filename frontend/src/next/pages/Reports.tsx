import { useState } from 'react';
import { Download } from 'lucide-react';
import { approvalsByDay, correctionsByClass, type Project } from '../../showcase/content';
import { BarChart, ChartCard, ColumnChart } from './charts';
import { PageHead, fmt, pct, projectEyebrow } from './shared';

type View = 'production' | 'quality';

const days = ['14 Oct', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24', '25', '26', '27 Oct'];

export function ReportsPage({ project: p }: { project: Project }) {
  const [view, setView] = useState<View>('production');
  // Scale the illustrative series to the project's size so small projects read sensibly.
  const scale = p.assets / 1240;
  const perDay: [string, number][] = approvalsByDay.map((v, i) => [days[i], Math.max(1, Math.round(v * scale))]);
  const corrections = correctionsByClass[p.view];
  const correctedTotal = corrections.reduce((s, [, n]) => s + n, 0);

  return (
    <div className="page">
      <PageHead
        eyebrow={projectEyebrow(p)}
        title="Reports"
        lede="Production shows how much work has moved; quality shows how good it is."
        actions={
          <button className="btn btn-ghost">
            <Download size={16} aria-hidden /> Export labels
          </button>
        }
      />
      <div className="seg" role="group" aria-label="Report">
        <button aria-pressed={view === 'production'} onClick={() => setView('production')}>
          Production
        </button>
        <button aria-pressed={view === 'quality'} onClick={() => setView('quality')}>
          Quality
        </button>
      </div>

      {view === 'production' ? (
        <>
          <section className="card stats" aria-label="Production summary">
            <div className="stat">
              <div className="stat-label">In project</div>
              <div className="stat-value">{fmt(p.assets)}</div>
              <div className="stat-note">{p.unit}</div>
            </div>
            <div className="stat">
              <div className="stat-label">Approved</div>
              <div className="stat-value">{fmt(p.approved)}</div>
              <div className="stat-note">{pct(p.approved, p.assets)}% of the project</div>
            </div>
            <div className="stat">
              <div className="stat-label">Waiting for review</div>
              <div className="stat-value">{fmt(p.reviewPending)}</div>
              <div className="stat-note">lowest confidence first</div>
            </div>
            <div className="stat">
              <div className="stat-label">Waiting for QC</div>
              <div className="stat-value">{fmt(p.qcPending)}</div>
              <div className="stat-note">sampled for audit</div>
            </div>
          </section>
          <ChartCard title={`${p.unit[0].toUpperCase()}${p.unit.slice(1)} approved per day`} sub="Last 14 days · sample data" rows={perDay} valueName="Approved">
            <ColumnChart rows={perDay} valueName="Approved" />
          </ChartCard>
        </>
      ) : (
        <>
          <section className="card stats" aria-label="Quality summary">
            <div className="stat">
              <div className="stat-label">Reviewers agreed with AI</div>
              <div className="stat-value">91%</div>
              <div className="stat-note">of labels accepted as drafted</div>
            </div>
            <div className="stat">
              <div className="stat-label">QC pass rate</div>
              <div className="stat-value">96%</div>
              <div className="stat-note">of sampled items</div>
            </div>
            <div className="stat">
              <div className="stat-label">Sent back</div>
              <div className="stat-value">14</div>
              <div className="stat-note">reworked after QC</div>
            </div>
            <div className="stat">
              <div className="stat-label">Corrections</div>
              <div className="stat-value">{correctedTotal}</div>
              <div className="stat-note">made by reviewers</div>
            </div>
          </section>
          <ChartCard title="Corrections by class" sub="Where reviewers changed the AI draft · sample data" rows={corrections} valueName="Corrections">
            <BarChart rows={corrections} valueName="Corrections" />
          </ChartCard>
        </>
      )}
    </div>
  );
}
