import type { Overview } from './model';

/** Recent events on the project (sample). `noQc` swaps quality-check events for review and team ones. */
export function Activity({ o, noQc = false }: { o: Overview; noQc?: boolean }) {
  const u = o.unit;
  const rows: [string, string, string, string][] = noQc
    ? [
        ['is-review', 'Review', 'Corrected 7 labels, rejected 1', '12 min'],
        ['is-ai', 'AI', `Drafted labels for 120 new ${u}`, '2 h'],
        ['is-review', 'Review', `Approved 64 ${u}`, '3 h'],
        ['is-neutral', 'Team', 'Raised the auto-accept line to 0.95', 'Yesterday'],
        ['is-neutral', 'Team', 'Added classes to the guidelines', 'Yesterday'],
      ]
    : [
        ['is-pass', 'QC', `Approved a sample of 24 ${u}`, '12 min'],
        ['is-review', 'Review', 'Corrected 7 labels, rejected 1', '40 min'],
        ['is-ai', 'AI', `Drafted labels for 120 new ${u}`, '2 h'],
        ['is-fail', 'QC', `Sent 3 ${u} back for rework`, '5 h'],
        ['is-neutral', 'Team', 'Added classes to the guidelines', 'Yesterday'],
      ];
  return (
    <ul className="ov-activity">
      {rows.map(([cls, tag, text, time]) => (
        <li key={text}>
          <span className={`chip ${cls}`}>{tag}</span>
          <span>{text}</span>
          <time>{time}</time>
        </li>
      ))}
    </ul>
  );
}
