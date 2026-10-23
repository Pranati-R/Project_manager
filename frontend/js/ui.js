// Small DOM toolkit. Text always goes in through textContent, never innerHTML.

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k === 'value') el.value = v;
    else if (k === 'checked' || k === 'disabled' || k === 'selected') el[k] = !!v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

export function clear(el, ...children) {
  el.replaceChildren();
  append(el, children);
  return el;
}

const ICONS = {
  plus: 'M12 5v14M5 12h14',
  edit: 'M4 20h4L19 9l-4-4L4 16v4zM14 6l4 4',
  trash: 'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
  play: 'M8 5v14l11-7z',
  test: 'M9 3h6M10 3v6L5 19a1 1 0 0 0 1 2h12a1 1 0 0 0 1-2l-5-10V3',
  book: 'M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2V5zM4 19a2 2 0 0 1 2-2h13',
  ext: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
  restart: 'M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7',
  copy: 'M8 8h11v12H8zM5 16H4V4h12v1',
  close: 'M6 6l12 12M18 6L6 18',
  ok: 'M5 12l5 5L20 7',
  warn: 'M12 3l10 18H2zM12 10v5M12 18v.5',
  error: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM9 9l6 6M15 9l-6 6',
  skip: 'M5 12h14',
  moon: 'M21 13A9 9 0 1 1 11 3a7 7 0 0 0 10 10z',
  logout: 'M15 4h4v16h-4M10 8l-4 4 4 4M6 12h11',
  refresh: 'M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7',
};

export function icon(name, cls = '') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '2');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  if (cls) svg.setAttribute('class', cls);
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', ICONS[name] || ICONS.skip);
  svg.append(path);
  return svg;
}

export function button(label, { kind = '', icon: ic, onclick, title, small, disabled, type = 'button' } = {}) {
  const cls = ['btn', kind, small ? 'small' : '', !label ? 'icon' : ''].filter(Boolean).join(' ');
  return h('button', { class: cls, type, onclick, title: title || (label ? null : ''), 'aria-label': title || label, disabled },
    ic ? icon(ic) : null, label || null);
}

export function toast(message, kind = '') {
  const box = document.getElementById('toasts');
  const t = h('div', { class: `toast ${kind}`, text: message });
  box.append(t);
  setTimeout(() => t.remove(), kind === 'err' ? 8000 : 4000);
}

// A modal dialog. Returns { el, body, foot, close }.
export function modal(title, { wide = false, onclose } = {}) {
  const body = h('div', { class: 'modal-body' });
  const foot = h('div', { class: 'modal-foot' });
  const prev = document.activeElement;
  const close = () => {
    overlay.remove();
    document.removeEventListener('keydown', onKey);
    if (prev && prev.focus) prev.focus();
    if (onclose) onclose();
  };
  const onKey = e => { if (e.key === 'Escape') close(); };
  const box = h('div', { class: `modal${wide ? ' wide' : ''}`, role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
    h('div', { class: 'modal-head' }, h('h2', { text: title }), h('div', { class: 'spacer' }),
      button('', { kind: 'ghost', icon: 'close', title: 'Close', onclick: () => close() })),
    body, foot);
  const overlay = h('div', { class: 'overlay', onmousedown: e => { if (e.target === overlay) close(); } }, box);
  document.body.append(overlay);
  document.addEventListener('keydown', onKey);
  return { el: box, body, foot, close };
}

export function drawer(title, subtitle) {
  const body = h('div', { class: 'drawer-body' });
  const close = () => { ov.remove(); dr.remove(); document.removeEventListener('keydown', onKey); };
  const onKey = e => { if (e.key === 'Escape') close(); };
  const ov = h('div', { class: 'drawer-overlay', onclick: close });
  const dr = h('aside', { class: 'drawer', role: 'dialog', 'aria-label': title },
    h('div', { class: 'drawer-head' },
      h('div', {}, h('h2', { text: title }), subtitle ? h('div', { class: 'muted', text: subtitle }) : null),
      h('div', { class: 'spacer' }),
      button('', { kind: 'ghost', icon: 'close', title: 'Close', onclick: close })),
    body);
  document.body.append(ov, dr);
  document.addEventListener('keydown', onKey);
  return { body, close };
}

export function confirmDialog(title, message, { confirm = 'Confirm', danger = false } = {}) {
  return new Promise(resolve => {
    let answered = false;
    const m = modal(title, { onclose: () => { if (!answered) resolve(false); } });
    m.body.append(h('p', { class: 'muted', text: message }));
    m.foot.append(
      button('Cancel', { onclick: () => m.close() }),
      button(confirm, { kind: danger ? 'primary danger-solid' : 'primary', onclick: () => { answered = true; m.close(); resolve(true); } }));
    m.foot.lastChild.focus();
  });
}

export function codeBlock(text, { cls = '', copy = true } = {}) {
  const pre = h('pre', { class: `code ${cls}`, text });
  if (!copy) return pre;
  return h('div', { class: 'copy-wrap' }, pre,
    button('', { kind: 'small', icon: 'copy', title: 'Copy', small: true, onclick: () => copyText(text) }));
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('Copied');
  } catch {
    toast('Copy is not available here (the page is not on HTTPS); select the text instead', 'err');
  }
}

export function diffBlock(diff) {
  const pre = h('pre', { class: 'code tall' });
  for (const line of diff.split('\n')) {
    let cls = '';
    if (line.startsWith('+') && !line.startsWith('+++')) cls = 'diff-add';
    else if (line.startsWith('-') && !line.startsWith('---')) cls = 'diff-del';
    else if (line.startsWith('@@')) cls = 'diff-hunk';
    pre.append(h('span', { class: cls, text: line + '\n' }));
  }
  return pre;
}

export function fmtTime(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export function fmtBackupId(id) {
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/.exec(id);
  if (!m) return id;
  return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6])).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'medium' });
}

export function field(label, control, { help, id, error } = {}) {
  const f = h('div', { class: 'field' + (error ? ' invalid' : '') , dataset: id ? { field: id } : {} },
    h('label', { text: label, for: control.id || null }), control,
    help ? h('div', { class: 'help', text: help }) : null,
    h('div', { class: 'error-text', text: error || '' }));
  return f;
}

export function select(options, value, attrs = {}) {
  return h('select', { class: 'select', ...attrs },
    options.map(o => h('option', { value: o.value, text: o.label, selected: String(o.value) === String(value) })));
}

export function badge(text, kind = '') {
  return h('span', { class: `badge ${kind}`, text });
}
