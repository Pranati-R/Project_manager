import { del, get, post } from '../api.js';
import { h, clear, icon, button, badge, toast, drawer, confirmDialog, codeBlock, copyText } from '../ui.js';
import { openEditor } from './editor.js';

const MODE_LABEL = { subpath: 'subpath', strip: 'strip prefix', rewrite: 'rewrite (best effort)' };

export function renderProjects(view, app) {
  const list = h('div', { class: 'plist' });
  const gw = app.status && app.status.urls && app.status.urls.gateway ? app.status.urls.gateway[0] : '';
  view.append(
    h('div', { class: 'page-head' },
      h('div', {}, h('h1', { text: 'Projects' }),
        h('div', { class: 'sub', text: gw ? `All projects share one gateway: ${gw}` : 'All projects share one gateway port' })),
      h('div', { class: 'spacer' }),
      button('Add project', { kind: 'primary', icon: 'plus', onclick: () => openEditor(null, app, () => draw()) })),
    list);

  let health = {};
  const draw = () => {
    const projects = (app.data && app.data.projects) || [];
    if (!projects.length) {
      clear(list, h('div', { class: 'card empty' },
        h('h2', { text: 'No projects yet' }),
        h('p', { text: 'Add an app (its port and URL path) and the gateway route is created, tested with nginx -t and applied automatically.' }),
        button('Add your first project', { kind: 'primary', icon: 'plus', onclick: () => openEditor(null, app, () => draw()) })));
      return;
    }
    clear(list, projects.map(p => row(p, app, health[p.id], draw)));
  };
  draw();

  const loadHealth = () => get('projects/status').then(s => { health = s; draw(); }).catch(() => {});
  loadHealth();
  const t = setInterval(() => { if (!document.body.contains(list)) return clearInterval(t); if (!document.hidden) loadHealth(); }, 15000);
}

function publicUrl(p, app) {
  const s = app.data.settings;
  const host = gatewayHost(app);
  const port = p.exposure === 'port' ? p.dedicated_port : s.gateway_port;
  const path = p.exposure === 'port' || p.prefix === '/' ? '/' : `${p.prefix}/`;
  return `http://${host}:${port}${path}`;
}

function gatewayHost(app) {
  const ts = app.status && app.status.tailscale;
  if (ts && ts.dns_name) return ts.dns_name;
  if (ts && ts.ipv4 && ts.ipv4.length) return ts.ipv4[0];
  return location.hostname || '127.0.0.1';
}

function row(p, app, hs, redraw) {
  const feUp = hs ? hs.frontend : null;
  const beUp = hs ? hs.backend : null;
  const up = feUp === null ? '' : feUp && beUp !== false ? 'ok' : 'err';
  const where = p.exposure === 'port' ? `:${p.dedicated_port}` : p.prefix;
  const toggle = h('input', {
    type: 'checkbox', checked: p.enabled, 'aria-label': `${p.enabled ? 'Disable' : 'Enable'} ${p.name}`,
    onchange: async e => {
      e.target.disabled = true;
      try {
        app.afterChange(await post(`projects/${p.id}/${e.target.checked ? 'enable' : 'disable'}`));
      } catch (ex) {
        toast(ex.message, 'err');
      }
      redraw();
    },
  });
  const url = publicUrl(p, app);
  const actions = h('div', { class: 'pactions' },
    h('label', { class: 'switch', title: p.enabled ? 'Enabled' : 'Disabled' }, toggle, h('span')),
    p.enabled ? h('a', { class: 'btn ghost small', href: url, target: '_blank', rel: 'noopener', title: url }, icon('ext'), 'Open') : null,
    button('Test', { kind: 'ghost', small: true, icon: 'test', onclick: () => openTest(p, app) }),
    button('Guide', { kind: 'ghost', small: true, icon: 'book', onclick: () => openGuide(p) }),
    p.restart_target ? button('', { kind: 'ghost', small: true, icon: 'restart', title: 'Restart the app', onclick: () => restart(p) }) : null,
    button('', { kind: 'ghost', small: true, icon: 'edit', title: 'Edit', onclick: () => openEditor(p, app, redraw) }),
    button('', { kind: 'ghost danger', small: true, icon: 'trash', title: 'Delete', onclick: () => remove(p, app, redraw) }));

  return h('div', { class: `card prow${p.enabled ? '' : ' off'}` },
    h('div', { class: 'pname' },
      h('span', { class: `dot ${up}`, title: feUp === null ? 'checking' : up === 'ok' ? 'running' : 'not reachable' }),
      h('div', { class: 'stack-0' },
        h('div', { class: 'title', text: p.name }),
        h('div', { class: 'id', text: p.id + (p.enabled ? '' : ' · disabled') }))),
    h('div', { class: 'proute' },
      h('div', { class: 'line' },
        badge(where, 'accent'), h('span', { class: 'arrow', text: '→' }),
        h('span', { class: 'mono', text: `${hostport(p.frontend)}` }),
        p.exposure === 'path' && p.prefix !== '/' ? badge(MODE_LABEL[p.frontend.path_mode] || p.frontend.path_mode) : badge('site root')),
      p.backend ? h('div', { class: 'line' },
        badge(`${p.exposure === 'port' || p.prefix === '/' ? '' : p.prefix}${p.backend.api_path}`),
        h('span', { class: 'arrow', text: '→' }), h('span', { class: 'mono', text: hostport(p.backend) }),
        beUp === false ? badge('API down', 'err') : null) : null,
      feUp === false ? h('div', { class: 'line' }, badge('frontend not reachable', 'err')) : null),
    actions);
}

export function hostport(up) {
  return (up.host.includes(':') ? `[${up.host}]` : up.host) + ':' + up.port;
}

async function remove(p, app, redraw) {
  if (!await confirmDialog(`Delete ${p.name}?`, `The route ${p.exposure === 'port' ? ':' + p.dedicated_port : p.prefix + '/'} is removed from the gateway. The app itself is not touched.`, { confirm: 'Delete', danger: true })) return;
  try {
    app.afterChange(await del(`projects/${p.id}`));
    redraw();
  } catch (e) { toast(e.message, 'err'); }
}

async function restart(p) {
  if (!await confirmDialog(`Restart ${p.name}?`, `Runs the restart listed for "${p.restart_target}" in restart-targets.conf.`, { confirm: 'Restart' })) return;
  try {
    const r = await post(`projects/${p.id}/restart`);
    toast(r.message || 'Restarted', 'ok');
  } catch (e) { toast(e.message, 'err'); }
}

export async function openTest(p, app) {
  const d = drawer(`Test: ${p.name}`, 'Runs from the server: direct to the app, then through the gateway');
  const out = h('div', { class: 'checks' }, h('div', { class: 'muted', text: 'Testing…' }));
  const again = button('Run again', { icon: 'refresh', onclick: () => run() });
  d.body.append(out, h('div', { class: 'row', style: null }, again));
  const run = async () => {
    clear(out, h('div', { class: 'muted', text: 'Testing…' }));
    again.disabled = true;
    try {
      const r = await post(`projects/${p.id}/test`);
      clear(out, h('div', { class: 'row' },
        h('h3', { text: 'Result' }),
        badge(r.status === 'ok' ? 'all good' : r.status === 'warn' ? 'works, with warnings' : 'problems found',
          r.status === 'ok' ? 'ok' : r.status === 'warn' ? 'warn' : 'err')),
        r.checks.map(c => h('div', { class: `check-item ${c.status}` },
          icon(c.status === 'ok' ? 'ok' : c.status === 'warn' ? 'warn' : c.status === 'error' ? 'error' : 'skip', 'icon'),
          h('div', {}, h('div', {}, h('b', { text: c.label }), c.detail ? h('span', { class: 'muted', text: ` · ${c.detail}` }) : null),
            c.hint ? h('div', { class: 'hint', text: c.hint }) : null))),
        r.status !== 'ok' ? h('p', { class: 'muted' }, 'The Guide explains how to start or build this app for its path. ',
          h('a', { href: '#', onclick: e => { e.preventDefault(); d.close(); openGuide(p); }, text: 'Open the guide' })) : null);
    } catch (e) {
      clear(out, h('div', { class: 'check-item error' }, icon('error', 'icon'), h('div', { text: e.message })));
    } finally {
      again.disabled = false;
    }
  };
  run();
}

export async function openGuide(p) {
  const d = drawer(`Setup guide: ${p.name}`, 'What to change in the app so it works under its gateway path');
  d.body.append(h('div', { class: 'muted', text: 'Loading…' }));
  try {
    const g = await get(`projects/${p.id}/guide`);
    clear(d.body,
      h('div', { class: 'banner info' }, h('div', { class: 'msg' }, 'Address: ', h('a', { href: g.url, target: '_blank', rel: 'noopener', text: g.url })),
        button('', { small: true, icon: 'copy', title: 'Copy address', onclick: () => copyText(g.url) })),
      g.warnings.map(w => h('div', { class: 'banner warn' }, h('div', { class: 'msg', text: w }))),
      g.sections.map(s => h('section', { class: 'guide-sec' },
        h('h3', { text: s.title }),
        s.text ? h('p', { text: s.text }) : null,
        s.code ? codeBlock(s.code, { cls: 'wrap' }) : null)));
  } catch (e) {
    clear(d.body, h('div', { class: 'banner err' }, h('div', { class: 'msg', text: e.message })));
  }
}
