import { get, post } from '../api.js';
import { h, clear, button, toast, codeBlock, diffBlock, confirmDialog, fmtBackupId, fmtTime } from '../ui.js';

export function renderConfig(view, app) {
  const result = h('div', { class: 'stack' });
  const pane = h('div');
  const tabs = h('div', { class: 'tabs', role: 'tablist' });
  const backups = h('div');
  let data = null;
  let tab = 'diff';

  view.append(
    h('div', { class: 'page-head' },
      h('div', {}, h('h1', { text: 'Nginx config' }),
        h('div', { class: 'sub', text: 'Generated from your projects. The only nginx file the gateway writes is /etc/nginx/nginx-gateway/gateway.conf.' })),
      h('div', { class: 'spacer' }),
      button('Validate', { onclick: () => validate(false), title: 'nginx -t in a private sandbox' }),
      button('Full nginx -t', { onclick: () => validate(true), title: 'nginx -t of the whole nginx config with this file in place; nothing is reloaded' }),
      button('Apply and reload', { kind: 'primary', onclick: apply })),
    result,
    h('div', { class: 'card' }, h('div', { class: 'card-body' }, tabs, pane)),
    h('h2', { class: 'section-title', text: 'Backups of the live file' }),
    h('div', { class: 'card' }, h('div', { class: 'card-body' }, backups)));

  const drawTabs = () => {
    const label = { diff: data && !data.in_sync ? 'Changes (not live yet)' : 'Changes', generated: 'Generated', live: 'Live' };
    clear(tabs, Object.keys(label).map(k => h('button', {
      class: tab === k ? 'active' : '', role: 'tab', 'aria-selected': String(tab === k), text: label[k],
      onclick: () => { tab = k; drawTabs(); drawPane(); },
    })));
  };
  const drawPane = () => {
    if (!data) return clear(pane, h('div', { class: 'muted', text: 'Loading…' }));
    if (data.errors && data.errors.length) {
      return clear(pane, h('ul', { class: 'issues' }, data.errors.map(e => h('li', { class: 'err', text: e.message }))));
    }
    if (tab === 'generated') return clear(pane, codeBlock(data.generated, { cls: 'tall' }));
    if (tab === 'live') return clear(pane, data.live === null
      ? h('div', { class: 'muted', text: 'No live gateway config yet (nothing applied, or the file is not readable).' })
      : codeBlock(data.live, { cls: 'tall' }));
    clear(pane, data.in_sync
      ? h('div', { class: 'banner info' }, h('div', { class: 'msg', text: 'The live config matches the dashboard.' }))
      : diffBlock(data.diff || ''));
  };
  const load = async () => {
    try { data = await get('config/preview'); } catch (e) { toast(e.message, 'err'); }
    drawTabs(); drawPane();
  };
  const loadBackups = async () => {
    try {
      const r = await get('config/backups');
      const list = r.backups || [];
      if (!r.ok) return clear(backups, h('div', { class: 'banner err' }, h('div', { class: 'msg', text: r.message || 'cannot list backups' })));
      if (!list.length) return clear(backups, h('div', { class: 'muted', text: 'No backups yet. One is made before every change to the live file (last 30 kept).' }));
      clear(backups, h('table', { class: 'table' },
        h('thead', {}, h('tr', {}, h('th', { text: 'Saved' }), h('th', { class: 'hide-sm', text: 'Size' }), h('th'))),
        h('tbody', {}, list.map(b => h('tr', {},
          h('td', { text: fmtBackupId(b.id) }), h('td', { class: 'hide-sm', text: `${(b.size / 1024).toFixed(1)} KB` }),
          h('td', {}, button('Restore', { small: true, onclick: () => restore(b.id) })))))));
    } catch (e) { clear(backups, h('div', { class: 'muted', text: e.message })); }
  };

  const showResult = (title, kind, lines, output) => clear(result,
    h('div', { class: `banner ${kind}` }, h('div', { class: 'msg' }, h('b', { text: title }),
      lines && lines.length ? h('ul', {}, lines.map(l => h('li', { text: l }))) : null)),
    output ? codeBlock(output, { cls: 'wrap' }) : null);

  async function validate(full) {
    showResult(full ? 'Running nginx -t on the whole nginx configuration…' : 'Validating…', 'info');
    try {
      const r = await post('config/validate', { full });
      const s = r.sandbox;
      if (!s.ok) return showResult('Not valid', 'err', s.errors.map(e => e.message), s.nginx_output);
      if (full && r.full && !r.full.ok) return showResult('nginx -t failed for the full configuration', 'err', [r.full.message].concat(r.full.errors || []), r.full.output);
      const warn = s.warnings.map(w => w.message);
      showResult(full ? 'The full nginx configuration is valid with this gateway config' : 'Valid' + (s.nginx_ok === null ? ' (nginx not available for nginx -t here)' : ''),
        warn.length ? 'warn' : 'info', warn, full && r.full ? r.full.output : s.nginx_output);
    } catch (e) { showResult(e.message, 'err'); }
  }

  async function apply() {
    showResult('Applying…', 'info');
    try {
      const r = await post('config/apply');
      app.afterChange(r);
      const a = r.apply;
      if (a.ok) showResult(a.message || 'Applied', 'info', a.backup ? [`previous version saved as backup ${fmtBackupId(a.backup)}`] : [], a.output);
      else showResult(`Not applied (${a.stage}): ${a.message}`, 'err', a.errors || [], a.output);
      load(); loadBackups();
    } catch (e) { showResult(e.message, 'err'); }
  }

  async function restore(id) {
    if (!await confirmDialog('Restore this backup?', `The live gateway config goes back to the version from ${fmtBackupId(id)} (tested with nginx -t first). The dashboard's projects are not changed, so they will show as "not applied" until you apply again.`, { confirm: 'Restore' })) return;
    try {
      const r = await post(`config/restore/${encodeURIComponent(id)}`);
      app.afterChange(r);
      const a = r.apply;
      showResult(a.ok ? `Restored the backup from ${fmtBackupId(id)}` : `Restore failed: ${a.message}`, a.ok ? 'info' : 'err', a.errors || [], a.output);
      load(); loadBackups();
    } catch (e) { toast(e.message, 'err'); }
  }

  const la = app.status && app.status.last_apply;
  if (la) {
    const when = fmtTime(la.at);
    if (la.ok) showResult(`Last apply ${when} by ${la.by}: ${la.message}`, 'info');
    else showResult(`Last apply failed ${when} (${la.stage}): ${la.message}`, 'err', la.errors, la.output);
  }
  load();
  loadBackups();
}
