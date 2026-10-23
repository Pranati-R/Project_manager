// Dashboard shell: login, navigation, status banners and the hash router.
import { get, post, setCsrf } from './api.js';
import { h, clear, icon, button, toast, confirmDialog } from './ui.js';
import { renderLogin } from './views/login.js';
import { renderProjects } from './views/projects.js';
import { renderConfig } from './views/config.js';
import { renderLogs } from './views/logs.js';
import { renderSettings } from './views/settings.js';

const root = document.getElementById('app');
const ROUTES = {
  projects: { label: 'Projects', render: renderProjects },
  config: { label: 'Nginx config', render: renderConfig },
  logs: { label: 'Logs', render: renderLogs },
  settings: { label: 'Settings', render: renderSettings },
};

// Shared state the views read; refresh() reloads it.
export const app = {
  me: null, meta: null, status: null, data: null,
  async refresh() {
    const [data, status] = await Promise.all([get('projects'), get('status')]);
    app.data = data;
    app.status = status;
    renderBanners();
    renderChips();
    return data;
  },
  // Run after any save/apply response that includes the new state.
  afterChange(resp) {
    if (resp && resp.state) app.data = resp.state;
    const result = resp && resp.apply;
    if (result) {
      if (result.ok) toast(result.reloaded ? 'Saved and applied: nginx reloaded' : (result.message || 'Saved'), result.reloaded ? 'ok' : '');
      else toast('Saved, but applying failed: ' + (result.message || 'see the banner'), 'err');
    } else if (resp && resp.check) {
      toast('Saved. Auto-apply is off: apply from the Nginx config tab', '');
    }
    get('status').then(s => { app.status = s; renderBanners(); renderChips(); }).catch(() => {});
  },
};

let banners, chips, view, timer;

function theme() {
  let t = null;
  try { t = localStorage.getItem('gw-theme'); } catch { /* storage blocked */ }
  if (t) document.documentElement.dataset.theme = t;
}

function toggleTheme() {
  const dark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === 'dark'
    : window.matchMedia('(prefers-color-scheme: dark)').matches;
  const next = dark ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('gw-theme', next); } catch { /* ignore */ }
}

async function boot() {
  theme();
  try {
    app.me = await get('auth/me');
  } catch (e) {
    if (e.status === 401) return showLogin();
    clear(root, h('div', { class: 'login-wrap' }, h('div', { class: 'card card-body', text: e.message })));
    return;
  }
  setCsrf(app.me.csrf);
  await startShell();
}

function showLogin() {
  clearInterval(timer);
  renderLogin(root, async me => {
    app.me = me;
    setCsrf(me.csrf);
    await startShell();
  });
}

async function startShell() {
  app.meta = await get('meta');
  const nav = h('nav', { class: 'nav', 'aria-label': 'Sections' },
    Object.entries(ROUTES).map(([k, r]) => h('a', { href: `#/${k}`, dataset: { route: k }, text: r.label })));
  chips = h('div', { class: 'row' });
  const userMenu = h('div', { class: 'row' },
    h('span', { class: 'muted hide-sm', text: app.me.username }),
    button('', { kind: 'ghost', icon: 'moon', title: 'Light / dark', onclick: toggleTheme }),
    button('', { kind: 'ghost', icon: 'logout', title: 'Log out', onclick: logout }));
  const top = h('header', { class: 'topbar' },
    h('div', { class: 'brand' }, h('div', { class: 'brand-mark', text: 'G' }), 'Gateway'),
    nav, h('div', { class: 'topbar-right' }, chips, userMenu));
  banners = h('div', { class: 'banners' });
  view = h('main', { id: 'view' });
  clear(root, top, banners, view);
  await app.refresh().catch(e => toast(e.message, 'err'));
  route();
  clearInterval(timer);
  timer = setInterval(() => {
    if (document.hidden) return;
    get('status').then(s => { app.status = s; renderBanners(); renderChips(); }).catch(() => {});
  }, 15000);
}

async function logout() {
  try { await post('auth/logout'); } catch { /* already gone */ }
  setCsrf(null);
  app.me = null;
  showLogin();
}

function route() {
  const name = (location.hash.replace(/^#\/?/, '').split('/')[0]) || 'projects';
  const r = ROUTES[name] || ROUTES.projects;
  for (const a of document.querySelectorAll('.nav a')) a.classList.toggle('active', a.dataset.route === (ROUTES[name] ? name : 'projects'));
  document.title = `${r.label} · Gateway Manager`;
  clear(view);
  r.render(view, app);
}

function renderChips() {
  if (!chips || !app.status) return;
  const s = app.status;
  const n = s.nginx || {};
  const nginxOk = n.nginx_active;
  const items = [
    h('span', { class: `badge ${nginxOk ? 'ok' : 'err'}`, title: n.message || '' },
      h('span', { class: `dot ${nginxOk ? 'ok' : 'err'}` }),
      s.helper_mode === 'sandbox' ? 'sandbox nginx' : `nginx ${n.nginx_version || ''}`.trim()),
  ];
  if (s.drift && !s.drift.in_sync) items.push(h('a', { class: 'badge warn', href: '#/config', text: 'not applied' }));
  const url = (s.urls && s.urls.gateway && s.urls.gateway[0]) || '';
  if (url) items.push(h('a', { class: 'badge accent hide-sm', href: url, target: '_blank', rel: 'noopener', text: url.replace(/^http:\/\//, '') }));
  clear(chips, items);
}

function renderBanners() {
  if (!banners || !app.status) return;
  const s = app.status;
  const out = [];
  if (s.password_is_default) {
    out.push(banner('warn', 'You are signed in with the default login (a@g.com / 123456). Change the password in Settings.',
      button('Change password', { small: true, onclick: () => { location.hash = '#/settings'; } })));
  }
  const n = s.nginx || {};
  if (n.ok === false) {
    out.push(banner('err', 'The privileged helper did not answer: ' + (n.message || 'unknown error')));
  } else if (n.nginx_installed === false) {
    out.push(banner('err', 'nginx is not installed on this server. Run: sudo nginx-gateway-ctl setup'));
  } else if (!n.nginx_active) {
    out.push(banner('warn', 'nginx is stopped, so the gateway is not serving. Starting nginx also starts any other sites it has enabled.',
      button('Start nginx', { small: true, kind: 'primary', onclick: startNginx })));
  }
  const la = s.last_apply;
  if (la && !la.ok) {
    const msg = 'The last change was saved but could not be applied: ' + la.message +
      (la.errors && la.errors.length ? ' (' + la.errors.join('; ') + ')' : '');
    out.push(banner('err', msg,
      button('Details', { small: true, onclick: () => { location.hash = '#/config'; } }),
      button('Retry apply', { small: true, onclick: applyNow }),
      s.applied ? button('Revert to last applied', { small: true, onclick: revertNow }) : null));
  } else if (s.drift && !s.drift.in_sync && n.nginx_installed !== false) {
    out.push(banner('info', s.drift.live_present
      ? 'The live nginx config differs from the dashboard (auto-apply is off, or a backup was restored).'
      : 'The gateway config has not been applied yet.',
      button('Review and apply', { small: true, onclick: () => { location.hash = '#/config'; } })));
  }
  if (s.helper_mode === 'sandbox') {
    out.push(banner('info', 'Development mode: changes go to a private sandbox nginx, not the system nginx.'));
  }
  clear(banners, out);
}

function banner(kind, message, ...actions) {
  return h('div', { class: `banner ${kind}`, role: kind === 'err' ? 'alert' : 'status' },
    h('div', { class: 'msg', text: message }), actions);
}

async function startNginx() {
  if (!await confirmDialog('Start nginx?', 'nginx will start with its whole configuration: the gateway and any other sites that are enabled in /etc/nginx.', { confirm: 'Start nginx' })) return;
  try {
    const r = await post('nginx/start');
    toast(r.message || 'nginx started', 'ok');
  } catch (e) { toast(e.message, 'err'); }
  app.refresh();
}

export async function applyNow() {
  try {
    const r = await post('config/apply');
    app.afterChange(r);
    if (r.apply && r.apply.ok) toast(r.apply.message || 'Applied', 'ok');
  } catch (e) { toast(e.message, 'err'); }
}

async function revertNow() {
  if (!await confirmDialog('Revert to the last applied state?', 'Projects and settings go back to what nginx last accepted. Changes since then are lost (they stay in the history files).', { confirm: 'Revert' })) return;
  try {
    app.afterChange(await post('config/revert'));
    route();
  } catch (e) { toast(e.message, 'err'); }
}

window.addEventListener('hashchange', () => { if (app.me) route(); });
window.addEventListener('auth-required', () => { if (app.me) { app.me = null; toast('Your session ended; please log in again'); showLogin(); } });
boot();
