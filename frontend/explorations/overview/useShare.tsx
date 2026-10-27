import { useEffect, useState } from 'react';

/** Copy the page link, with a short confirmation announced to screen readers. */
export function useShare() {
  const [msg, setMsg] = useState('');
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(''), 2400);
    return () => clearTimeout(t);
  }, [msg]);
  const share = async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      setMsg('Link copied');
    } catch {
      setMsg('Copy the address bar to share this page');
    }
  };
  const note = (
    <span className={`ov-toast${msg ? ' is-on' : ''}`} role="status" aria-live="polite">
      {msg}
    </span>
  );
  return { share, note };
}
