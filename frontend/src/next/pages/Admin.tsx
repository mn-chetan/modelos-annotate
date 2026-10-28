import { useState } from 'react';
import { PageHead, SampleNote } from './shared';

type Tab = 'users' | 'models' | 'audit';

const users = [
  ['Anika Rao', 'Project lead', '3 projects', 'Now'],
  ['Marcus Lee', 'Reviewer', '2 projects', '8 min ago'],
  ['Sara Okafor', 'Reviewer', '1 project', '1 h ago'],
  ['Daniel Costa', 'Quality checker', '4 projects', 'Yesterday'],
  ['Priya Nair', 'Annotator', '1 project', '2 days ago'],
];

const models = [
  ['Object detector', 'Image · Video', 'yolo26n', 'Active'],
  ['Segmenter', 'Image', 'sam2.1_t', 'Active'],
  ['Language model', 'Text', 'Gemini Flash', 'Active'],
];

const audit = [
  ['10:42', 'Daniel Costa', 'Approved QC sample of 24 images', 'Urban traffic detection'],
  ['10:05', 'Marcus Lee', 'Corrected 7 labels', 'Street camera PII'],
  ['09:31', 'AI', 'Drafted 120 documents', 'Operations report entities'],
  ['Yesterday', 'Anika Rao', 'Changed review threshold to 0.70', 'Urban traffic detection'],
  ['Yesterday', 'Anika Rao', 'Created project', 'Junction camera tracking'],
];

const tables: Record<Tab, { head: string[]; rows: string[][] }> = {
  users: { head: ['Name', 'Role', 'Access', 'Last active'], rows: users },
  models: { head: ['Model', 'Data', 'Version', 'Status'], rows: models },
  audit: { head: ['When', 'Who', 'What', 'Project'], rows: audit },
};

export function AdminPage() {
  const [tab, setTab] = useState<Tab>('users');
  const t = tables[tab];
  return (
    <div className="page">
      <PageHead eyebrow="Workspace" title="Administration" lede="People and their roles, the models drafting labels, and a record of who changed what."
        actions={<span className="sample-chip">Sample data</span>}
      />
      <SampleNote>Administration isn’t connected to the workspace yet. The people, models and log below are sample entries.</SampleNote>
      <div className="subtabs" role="tablist" aria-label="Administration">
        {(
          [
            ['users', 'Users'],
            ['models', 'Models'],
            ['audit', 'Audit log'],
          ] as [Tab, string][]
        ).map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>
            {label}
          </button>
        ))}
      </div>
      <div className="card table-wrap" role="tabpanel">
        <table className="table">
          <thead>
            <tr>
              {t.head.map((h) => (
                <th key={h} scope="col">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {t.rows.map((r) => (
              <tr key={r.join()}>
                {r.map((c, i) => (
                  <td key={i} className={i === 0 ? '' : i === r.length - 1 && tab !== 'audit' ? 'muted' : ''}>
                    {i === 3 && tab === 'models' ? <span className="chip is-pass">{c}</span> : i === 0 ? <b style={{ fontWeight: 600 }}>{c}</b> : c}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
