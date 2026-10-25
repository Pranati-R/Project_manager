import { post, put } from '../api.js';
import { h, clear, button, toast, modal, field, select, codeBlock } from '../ui.js';

const DEFAULTS = {
  id: '', name: '', enabled: true, exposure: 'path', prefix: '', dedicated_port: null,
  frontend: { host: '127.0.0.1', port: '', path_mode: 'subpath' }, backend: null,
  pass_host_header: true, read_timeout: 3600, max_body_size: null, health_path: null,
  app_kind: 'other', runtime: 'other', restart_target: null, app_dir: null, notes: '',
};
const NEW_BACKEND = { host: '127.0.0.1', port: '', api_path: '/api', api_mode: 'strip_prefix', buffering: false };

const slug = s => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
const num = v => (v === '' || v === null || v === undefined) ? null : (Number.isFinite(Number(v)) ? Number(v) : v);

export function openEditor(project, app, onSaved) {
  const editing = !!project;
  const f = structuredClone(project || DEFAULTS);
  let idTouched = editing;
  const meta = app.meta;
  const gwPort = app.data.settings.gateway_port;

  const m = modal(editing ? `Edit ${project.name}` : 'Add a project', { wide: true });
  const form = h('form', { class: 'stack', novalidate: true, onsubmit: e => { e.preventDefault(); save(); } });
  const preview = h('div', { class: 'stack' });
  m.body.append(h('div', { class: 'editor-grid' }, form, h('div', { class: 'editor-side' }, preview)));

  // ── controls ──
  const input = (path, attrs = {}) => {
    const el = h('input', { class: 'input', id: `f-${path}`, value: get(path) ?? '', ...attrs });
    el.addEventListener('input', () => { set(path, attrs.type === 'number' ? num(el.value) : el.value); changed(path); });
    return el;
  };
  const get = path => path.split('.').reduce((o, k) => (o ? o[k] : undefined), f);
  const set = (path, value) => {
    const keys = path.split('.');
    const last = keys.pop();
    const obj = keys.reduce((o, k) => o[k], f);
    obj[last] = value;
  };

  const name = input('name', { placeholder: 'My App', maxlength: 60, autocomplete: 'off' });
  const id = input('id', { placeholder: 'my-app', maxlength: 40, disabled: editing, autocomplete: 'off' });
  id.addEventListener('input', () => { idTouched = true; });
  name.addEventListener('input', () => {
    if (!idTouched) { f.id = slug(name.value); id.value = f.id; }
    if (!editing && !prefixTouched && f.exposure === 'path') { f.prefix = f.id ? '/' + f.id : ''; prefix.value = f.prefix; }
  });

  const kindHelp = h('div', { class: 'preset-help' });
  const kind = select(meta.presets.map(p => ({ value: p.value, label: p.label })), f.app_kind, { id: 'f-app_kind' });
  const showKindHelp = () => { const p = meta.presets.find(x => x.value === f.app_kind); kindHelp.textContent = p ? p.help : ''; };
  kind.addEventListener('change', () => {
    f.app_kind = kind.value;
    const p = meta.presets.find(x => x.value === f.app_kind);
    if (p) {
      if (p.sets.path_mode) { f.frontend.path_mode = p.sets.path_mode; mode.value = p.sets.path_mode; }
      if ('pass_host_header' in p.sets) { f.pass_host_header = p.sets.pass_host_header; passHost.checked = f.pass_host_header; }
      if (p.sets.exposure) { f.exposure = p.sets.exposure; syncExposure(); }
    }
    showKindHelp();
    changed('app_kind');
  });
  showKindHelp();

  // exposure
  let prefixTouched = editing;
  const prefix = input('prefix', { placeholder: '/my-app', maxlength: 120, autocomplete: 'off' });
  prefix.addEventListener('input', () => { prefixTouched = true; });
  prefix.addEventListener('blur', () => {
    let v = prefix.value.trim();
    if (v && !v.startsWith('/')) v = '/' + v;
    if (v.length > 1) v = v.replace(/\/+$/, '');
    prefix.value = v; f.prefix = v; changed('prefix');
  });
  const dport = input('dedicated_port', { type: 'number', min: 1024, max: 65535, placeholder: '8282' });
  const radio = (value, title, help) => h('label', { class: 'radio-card' },
    h('input', { type: 'radio', name: 'exposure', value, checked: f.exposure === value,
      onchange: () => { f.exposure = value; syncExposure(); changed('exposure'); } }),
    h('div', {}, h('div', { class: 'label', text: title }), h('div', { class: 'help faint', text: help })));
  const prefixField = field('URL path', prefix, { id: 'prefix', help: `Reached at http://<gateway>:${gwPort}/my-app/. Use / for one app that must own the site root.` });
  const portField = field('Gateway port for this app', dport, { id: 'dedicated_port', help: 'An unused port; nginx serves the app at / there (Tailscale-only, like the main port).' });
  const syncExposure = () => {
    prefixField.classList.toggle('hidden', f.exposure !== 'path');
    portField.classList.toggle('hidden', f.exposure !== 'port');
    for (const r of form.querySelectorAll('input[name=exposure]')) r.checked = r.value === f.exposure;
  };

  // frontend
  const feHost = input('frontend.host', { placeholder: '127.0.0.1' });
  const fePort = input('frontend.port', { type: 'number', min: 1, max: 65535, placeholder: '8200' });
  const modeHelp = h('div', { class: 'help' });
  const mode = select(meta.path_modes.map(x => ({ value: x.value, label: x.value })), f.frontend.path_mode, { id: 'f-frontend.path_mode' });
  const showModeHelp = () => { const x = meta.path_modes.find(y => y.value === f.frontend.path_mode); modeHelp.textContent = x ? x.help : ''; };
  mode.addEventListener('change', () => { f.frontend.path_mode = mode.value; showModeHelp(); changed('frontend.path_mode'); });
  showModeHelp();

  // backend
  const beBox = h('div', { class: 'stack' });
  const hasBe = h('input', { type: 'checkbox', checked: !!f.backend, onchange: () => {
    f.backend = hasBe.checked ? structuredClone(project && project.backend ? project.backend : NEW_BACKEND) : null;
    drawBackend(); changed('backend');
  } });
  const drawBackend = () => {
    clear(beBox);
    if (!f.backend) return;
    const apiMode = select(meta.api_modes.map(x => ({ value: x.value, label: x.help })), f.backend.api_mode, { id: 'f-backend.api_mode' });
    apiMode.addEventListener('change', () => { f.backend.api_mode = apiMode.value; changed('backend.api_mode'); });
    const buffering = h('input', { type: 'checkbox', checked: f.backend.buffering, onchange: e => { f.backend.buffering = e.target.checked; changed('backend.buffering'); } });
    beBox.append(
      h('div', { class: 'grid three' },
        field('API host', input('backend.host', { placeholder: '127.0.0.1' }), { id: 'backend.host' }),
        field('API port', input('backend.port', { type: 'number', min: 1, max: 65535, placeholder: '8201' }), { id: 'backend.port' }),
        field('API path', input('backend.api_path', { placeholder: '/api' }), { id: 'backend.api_path', help: 'under the project path' })),
      field('What the API server sees', apiMode, { id: 'backend.api_mode' }),
      h('label', { class: 'check' }, buffering, h('span', {}, 'Buffer API responses ', h('span', { class: 'faint', text: '(leave off for streaming: SSE, token streams, long polls)' }))));
  };

  // advanced
  const passHost = h('input', { type: 'checkbox', checked: f.pass_host_header, onchange: e => { f.pass_host_header = e.target.checked; changed('pass_host_header'); } });
  const runtime = select([{ value: 'systemd', label: 'systemd service' }, { value: 'docker', label: 'Docker container' },
    { value: 'tmux', label: 'tmux / started by hand' }, { value: 'other', label: 'other' }], f.runtime, { id: 'f-runtime' });
  runtime.addEventListener('change', () => { f.runtime = runtime.value; changed('runtime'); });
  const targets = [{ value: '', label: '(none)' }].concat((meta.restart_targets || []).map(t => ({ value: t.id, label: `${t.id} (${t.kind} ${t.name})` })));
  const restartSel = select(targets, f.restart_target || '', { id: 'f-restart_target' });
  restartSel.addEventListener('change', () => { f.restart_target = restartSel.value || null; changed('restart_target'); });
  const enabled = h('input', { type: 'checkbox', checked: f.enabled, onchange: e => { f.enabled = e.target.checked; changed('enabled'); } });
  const notes = h('textarea', { class: 'input', id: 'f-notes', maxlength: 500, rows: 2, text: f.notes || '' });
  notes.addEventListener('input', () => { f.notes = notes.value; });

  form.append(
    h('div', { class: 'grid two' },
      field('Name', name, { id: 'name' }),
      field('ID', id, { id: 'id', help: editing ? 'cannot be changed' : 'used in log file names' })),
    h('div', { class: 'section-title', text: 'How is the frontend served?' }),
    field('App type', kind, { id: 'app_kind' }), kindHelp,
    h('div', { class: 'section-title', text: 'Where on the gateway' }),
    h('div', { class: 'radio-cards' },
      radio('path', `A URL path on port ${gwPort}`, 'e.g. /my-app/ (recommended)'),
      radio('port', 'Its own gateway port', 'for apps that only work at /')),
    prefixField, portField,
    h('div', { class: 'section-title', text: 'The app (upstream)' }),
    h('div', { class: 'grid two' },
      field('Frontend host', feHost, { id: 'frontend.host', help: 'an IP address; 127.0.0.1 for apps on this server' }),
      field('Frontend port', fePort, { id: 'frontend.port' })),
    field('Path mode', mode, { id: 'frontend.path_mode' }), modeHelp,
    h('label', { class: 'check' }, hasBe, h('span', {}, h('b', { text: 'Separate API server' }), h('span', { class: 'faint', text: ' (e.g. FastAPI on its own port)' }))),
    beBox,
    h('details', {},
      h('summary', { class: 'section-title', text: 'Advanced' }),
      h('div', { class: 'stack' },
        h('label', { class: 'check' }, passHost, h('span', {}, 'Pass the original Host header ',
          h('span', { class: 'faint', text: '(turn off for Vite dev/preview: it blocks unknown host names)' }))),
        h('div', { class: 'grid three' },
          field('Timeout (s)', input('read_timeout', { type: 'number', min: 5, max: 86400 }), { id: 'read_timeout', help: 'for WebSockets and slow responses' }),
          field('Max upload', input('max_body_size', { placeholder: '100m' }), { id: 'max_body_size', help: 'empty = gateway default' }),
          field('Health path', input('health_path', { placeholder: '/health' }), { id: 'health_path', help: 'API path used by Test' })),
        h('div', { class: 'grid two' },
          field('Runs as', runtime, { id: 'runtime', help: 'only used for the setup guide' }),
          field('Restart target', restartSel, { id: 'restart_target', help: `from ${meta.restart_targets_file}` })),
        field('App folder', input('app_dir', { placeholder: '/home/me/my-app' }), { id: 'app_dir', help: 'only used in the guide commands' }),
        field('Notes', notes, { id: 'notes' }),
        h('label', { class: 'check' }, enabled, h('span', { text: 'Enabled' })))));
  drawBackend();
  syncExposure();

  const generalErrors = h('ul', { class: 'issues' });
  const saveBtn = button(editing ? 'Save and apply' : 'Add and apply', { kind: 'primary', onclick: () => save() });
  m.foot.append(generalErrors, h('div', { class: 'spacer' }), button('Cancel', { onclick: () => m.close() }), saveBtn);

  // ── validation and preview ──
  const payload = () => {
    const p = structuredClone(f);
    p.frontend.port = num(p.frontend.port);
    if (p.backend) p.backend.port = num(p.backend.port);
    p.dedicated_port = p.exposure === 'port' ? num(p.dedicated_port) : null;
    if (p.exposure === 'port') p.prefix = null;
    p.read_timeout = num(p.read_timeout) ?? 3600;
    for (const k of ['max_body_size', 'health_path', 'restart_target', 'app_dir']) if (!p[k]) p[k] = null;
    return p;
  };

  const showIssues = (errors = [], warnings = []) => {
    for (const el of form.querySelectorAll('.field')) { el.classList.remove('invalid'); el.querySelector('.error-text').textContent = ''; }
    const unplaced = [];
    for (const e of errors) {
      const el = e.field && form.querySelector(`.field[data-field="${CSS.escape(e.field)}"]`);
      if (el && !el.classList.contains('hidden')) { el.classList.add('invalid'); el.querySelector('.error-text').textContent = e.message; }
      else unplaced.push(e);
    }
    clear(generalErrors, unplaced.slice(0, 3).map(e => h('li', { class: 'err', text: (e.field ? e.field + ': ' : '') + e.message })));
    return { unplaced, warnings };
  };

  let timer = null;
  let seq = 0;
  function changed() { clearTimeout(timer); timer = setTimeout(runPreview, 350); }
  async function runPreview() {
    const mine = ++seq;
    let r;
    try { r = await post('projects/preview', payload()); } catch (e) { return; }
    if (mine !== seq) return;
    const { unplaced, warnings } = showIssues(r.errors, r.warnings);
    clear(preview,
      h('div', { class: 'row' }, h('h3', { text: 'Generated nginx routes' }), h('div', { class: 'spacer' }),
        r.errors.length ? h('span', { class: 'badge err', text: `${r.errors.length} to fix` }) : h('span', { class: 'badge ok', text: 'valid' })),
      warnings.length ? h('ul', { class: 'issues' }, warnings.map(w => h('li', { class: 'warn', text: w.message }))) : null,
      unplaced.length ? h('ul', { class: 'issues' }, unplaced.map(w => h('li', { class: 'err', text: (w.field ? w.field + ': ' : '') + w.message }))) : null,
      r.snippet ? codeBlock(r.snippet, { cls: 'tall' }) : h('div', { class: 'muted', text: 'Fill in the fields to see the routes.' }),
      h('p', { class: 'faint', text: 'On save the whole config is tested with nginx -t before nginx reloads; a failed test leaves the live gateway untouched.' }));
  }
  runPreview();

  async function save() {
    if (document.activeElement === prefix) prefix.blur();
    saveBtn.disabled = true;
    try {
      const body = payload();
      const r = editing ? await put(`projects/${project.id}`, body) : await post('projects', body);
      app.afterChange(r);
      m.close();
      onSaved && onSaved();
    } catch (e) {
      const d = e.detail || {};
      const { unplaced } = showIssues(d.errors || [], d.warnings || []);
      if (!d.errors || !d.errors.length || unplaced.length) toast(e.message, 'err');
      if (d.nginx_output) clear(preview, h('h3', { text: 'nginx -t output' }), codeBlock(d.nginx_output, { cls: 'wrap' }));
    } finally {
      saveBtn.disabled = false;
    }
  }
  (editing ? fePort : name).focus();
}
