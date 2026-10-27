import { PageHead } from './shared';
export function QualityPage({ project }: { project?: unknown }) { return <div className="page"><PageHead eyebrow="Workspace" title="Quality check" /><section className="card empty"><h2>Unavailable</h2><p>Unavailable in this demo. Human approval is final; QC sampling is bypassed.</p></section></div>; }
