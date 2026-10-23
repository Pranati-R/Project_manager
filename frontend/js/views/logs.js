import { get } from '../api.js';
import { h, clear, button, select } from '../ui.js';

const SOURCES = [
  { value: 'access', label: 'Gateway access log' },
  { value: 'error', label: 'Gateway error log' },
  { value: 'admin-access', label: 'Dashboard access log' },
  { value: 'admin-error', label: 'Dashboard error log' },
  { value: 'nginx-error', label: 'nginx error.log (all sites)' },
  { value: 'journal', label: 'nginx service journal' },
  { value: 'manager', label: 'Manager service journal' },
  { value: 'audit', label: 'Audit trail (who changed what)' },
];

export function renderLogs(view, app) {
  let source = 'access';
  try { source = sessionStorage.getItem('gw-log-source') || 'access'; } catch { /* storage blocked */ }
  const src = select(SOURCES, source, { 'aria-label': 'Log source' });
  const lines = select([100, 200, 500, 1000, 2000].map(n => ({ value: n, label: `${n} lines` })), 200, { 'aria-label': 'Lines' });
  const filter = h('input', { class: 'input', placeholder: 'Filter, e.g. /prajna or 502', 'aria-label': 'Filter' });
  const auto = h('input', { type: 'checkbox' });
  const out = h('pre', { class: 'code tall wrap', text: 'Loading…' });
  const meta = h('div', { class: 'faint' });

  const load = async () => {
    try {
      const params = new URLSearchParams({ source: src.value, lines: lines.value, filter: filter.value });
      const r = await get(`logs?${params}`);
      const text = (r.lines || []).join('\n');
      out.textContent = r.ok === false ? (r.message || 'cannot read the log') : (text || r.message || '(empty)');
      meta.textContent = r.path ? r.path : '';
      out.scrollTop = out.scrollHeight;
    } catch (e) { out.textContent = e.message; }
  };
  src.addEventListener('change', () => { try { sessionStorage.setItem('gw-log-source', src.value); } catch { /* ignore */ } load(); });
  lines.addEventListener('change', load);
  let debounce;
  filter.addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(load, 300); });

  view.append(
    h('div', { class: 'page-head' }, h('div', {}, h('h1', { text: 'Logs' }),
      h('div', { class: 'sub', text: 'Read through the helper; nothing here can change the server.' }))),
    h('div', { class: 'card' }, h('div', { class: 'card-body stack' },
      h('div', { class: 'row wrap' },
        h('div', { class: 'field' }, src), h('div', { class: 'field' }, lines), h('div', { class: 'field spacer' }, filter),
        h('label', { class: 'check' }, auto, h('span', { text: 'Auto-refresh' })),
        button('Refresh', { icon: 'refresh', onclick: load })),
      out, meta)));
  load();
  const t = setInterval(() => {
    if (!document.body.contains(out)) return clearInterval(t);
    if (auto.checked && !document.hidden) load();
  }, 5000);
}
