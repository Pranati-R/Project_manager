import { del, get, post, put } from '../api.js';
import { h, clear, button, toast, field, select, confirmDialog } from '../ui.js';

export function renderSettings(view, app) {
  const s = structuredClone(app.data.settings);
  view.append(h('div', { class: 'page-head' }, h('div', {}, h('h1', { text: 'Settings' }))));

  // ── gateway ──
  const gwPort = h('input', { class: 'input', type: 'number', min: 1024, max: 65535, value: s.gateway_port });
  const adminMode = select([{ value: 'dedicated_port', label: 'On its own port through nginx (Tailscale-only)' },
    { value: 'localhost_only', label: 'Only on 127.0.0.1 (use an SSH tunnel)' }], s.admin_mode);
  const adminPort = h('input', { class: 'input', type: 'number', min: 1024, max: 65535, value: s.admin_port });
  const listen = h('input', { class: 'input', value: s.listen_addresses.join(', ') });
  const cidrs = h('textarea', { class: 'input', rows: 4, text: s.allowed_cidrs.join('\n') });
  const body = h('input', { class: 'input', value: s.client_max_body_size });
  const landing = h('input', { type: 'checkbox', checked: s.landing_page });
  const autoApply = h('input', { type: 'checkbox', checked: s.auto_apply });
  const errs = h('ul', { class: 'issues' });
  const saveBtn = button('Save and apply', { kind: 'primary' });

  const gatewayForm = h('form', { class: 'card', onsubmit: async e => {
    e.preventDefault();
    const next = {
      gateway_port: Number(gwPort.value), admin_mode: adminMode.value, admin_port: Number(adminPort.value),
      listen_addresses: listen.value.split(/[\s,]+/).filter(Boolean),
      allowed_cidrs: cidrs.value.split(/[\s,]+/).filter(Boolean),
      client_max_body_size: body.value.trim(), landing_page: landing.checked, auto_apply: autoApply.checked,
    };
    const adminMoves = next.admin_mode !== s.admin_mode || next.admin_port !== s.admin_port;
    if (adminMoves && !await confirmDialog('Move the dashboard?', next.admin_mode === 'localhost_only'
      ? 'After this the dashboard is only reachable through an SSH tunnel: ssh -L 8790:127.0.0.1:8790 <server>, then http://127.0.0.1:8790/.'
      : `After this the dashboard is at port ${next.admin_port}. This page will stop answering on the current port.`, { confirm: 'Save' })) return;
    saveBtn.disabled = true;
    clear(errs);
    try {
      const r = await put('settings', next);
      Object.assign(s, next);
      app.afterChange(r);
    } catch (ex) {
      const list = (ex.detail && ex.detail.errors) || [];
      clear(errs, (list.length ? list : [{ message: ex.message }]).map(x => h('li', { class: 'err', text: (x.field ? x.field + ': ' : '') + x.message })));
    } finally { saveBtn.disabled = false; }
  } },
  h('div', { class: 'card-head' }, h('h2', { text: 'Gateway' })),
  h('div', { class: 'card-body stack' },
    h('div', { class: 'grid three' },
      field('Gateway port', gwPort, { help: 'the one port for every project' }),
      field('Dashboard', adminMode),
      field('Dashboard port', adminPort, { help: 'used when the dashboard has its own port' })),
    h('div', { class: 'grid two' },
      field('Listen addresses', listen, { help: '0.0.0.0 = all interfaces, restricted by the allowed networks below. Binding to the Tailscale IP itself can fail at boot.' }),
      field('Max upload size', body, { help: 'default for all projects, e.g. 100m' })),
    field('Allowed networks', cidrs, { help: 'one per line. 100.64.0.0/10 and fd7a:115c:a1e0::/48 are Tailscale; keep 127.0.0.1 for the Test buttons.' }),
    h('label', { class: 'check' }, landing, h('span', { text: 'Show a list of projects at / of the gateway' })),
    h('label', { class: 'check' }, autoApply, h('span', {}, 'Apply automatically after every change ', h('span', { class: 'faint', text: '(validated with nginx -t first)' }))),
    errs,
    h('div', { class: 'row' }, h('div', { class: 'spacer' }), saveBtn)));
  view.append(gatewayForm);

  // ── account ──
  const cur = h('input', { class: 'input', type: 'password', autocomplete: 'current-password' });
  const n1 = h('input', { class: 'input', type: 'password', autocomplete: 'new-password' });
  const n2 = h('input', { class: 'input', type: 'password', autocomplete: 'new-password' });
  view.append(h('div', { class: 'section-title', text: 'Account' }),
    h('form', { class: 'card', onsubmit: async e => {
      e.preventDefault();
      if (n1.value !== n2.value) return toast('The new passwords do not match', 'err');
      try {
        await post('auth/password', { current: cur.value, new: n1.value });
        cur.value = n1.value = n2.value = '';
        toast('Password changed', 'ok');
        app.refresh();
      } catch (ex) { toast(ex.message, 'err'); }
    } },
    h('div', { class: 'card-body stack' },
      h('div', { class: 'muted', text: `Signed in as ${app.me.username}` }),
      h('div', { class: 'grid three' }, field('Current password', cur), field('New password', n1, { help: 'at least 6 characters' }), field('Repeat', n2)),
      h('div', { class: 'row' }, h('div', { class: 'spacer' }), button('Change password', { kind: 'primary', type: 'submit' })))));

  // ── users ──
  const users = h('div');
  const nu = h('input', { class: 'input', type: 'email', placeholder: 'name@example.com', autocomplete: 'off' });
  const np = h('input', { class: 'input', type: 'password', autocomplete: 'new-password' });
  const drawUsers = list => clear(users, h('table', { class: 'table' },
    h('tbody', {}, list.map(u => h('tr', {},
      h('td', { text: u.username }),
      h('td', { class: 'faint', text: u.default_password ? 'default password' : '' }),
      h('td', {}, u.username === app.me.username ? h('span', { class: 'faint', text: 'you' }) :
        button('Remove', { small: true, kind: 'ghost danger', onclick: async () => {
          if (!await confirmDialog(`Remove ${u.username}?`, 'They will not be able to sign in any more.', { confirm: 'Remove', danger: true })) return;
          try { drawUsers((await del(`users/${encodeURIComponent(u.username)}`)).users); } catch (ex) { toast(ex.message, 'err'); }
        } })))))));
  get('users').then(r => drawUsers(r.users)).catch(e => clear(users, e.message));
  view.append(h('div', { class: 'section-title', text: 'Administrators' }),
    h('div', { class: 'card' }, h('div', { class: 'card-body stack' }, users,
      h('form', { class: 'grid three', onsubmit: async e => {
        e.preventDefault();
        try { drawUsers((await post('users', { username: nu.value, password: np.value })).users); nu.value = np.value = ''; toast('User added', 'ok'); }
        catch (ex) { toast(ex.message, 'err'); }
      } }, field('Email', nu), field('Password', np), h('div', { class: 'field' }, h('label', { text: ' ' }), button('Add administrator', { type: 'submit' }))))));

  // ── export / import ──
  const file = h('input', { type: 'file', accept: 'application/json,.json', class: 'input' });
  const mode = select([{ value: 'merge', label: 'Merge (add/replace by id)' }, { value: 'replace', label: 'Replace all projects' }], 'merge');
  view.append(h('div', { class: 'section-title', text: 'Backup of the projects' }),
    h('div', { class: 'card' }, h('div', { class: 'card-body stack' },
      h('div', { class: 'row wrap' },
        button('Export projects (JSON)', { onclick: async () => {
          try {
            const data = await get('export');
            const a = h('a', { href: URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })), download: 'gateway-projects.json' });
            document.body.append(a); a.click(); a.remove();
          } catch (ex) { toast(ex.message, 'err'); }
        } })),
      h('div', { class: 'grid three' }, field('Import file', file), field('Mode', mode),
        h('div', { class: 'field' }, h('label', { text: ' ' }), button('Import', { onclick: async () => {
          if (!file.files.length) return toast('Choose a JSON file first', 'err');
          try {
            const data = JSON.parse(await file.files[0].text());
            const r = await post('import', { projects: data.projects || [], mode: mode.value });
            app.afterChange(r);
            toast(`Imported ${(data.projects || []).length} project(s)`, 'ok');
          } catch (ex) { toast(ex.message, 'err'); }
        } }))))));

  // ── about ──
  view.append(h('div', { class: 'section-title', text: 'About' }),
    h('div', { class: 'card' }, h('div', { class: 'card-body muted' },
      h('div', { text: `Version ${app.meta.version} · helper: ${app.status.helper_mode} · manager on 127.0.0.1:${app.meta.manager_port}` }),
      h('div', { text: `Apps the dashboard may restart are listed in ${app.meta.restart_targets_file} (edit with: sudo nginx-gateway-ctl restart-targets).` }),
      h('div', { text: 'Update the code from GitHub with: sudo nginx-gateway-ctl update-code' }))));
}
