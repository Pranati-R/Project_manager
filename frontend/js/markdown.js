// A small, safe Markdown renderer for the Docs tab.
// It builds DOM nodes with h() and never touches innerHTML, so a docs file cannot inject markup or
// script. Supported: # to #### headings, paragraphs, bullet / numbered / task lists (nested), fenced
// code, tables, > quotes (with **Note:** / **Tip:** / **Warning:** / **Why?:** callouts), rules, and
// `code`, **bold**, *italic*, [links](x.md). Anything else is shown as plain text.
import { h, codeBlock } from './ui.js';

const INLINE_SRC = '`([^`]+)`|\\*\\*(.+?)\\*\\*|\\[([^\\]]+)\\]\\(([^)\\s]+)\\)|\\*([^*\\s][^*]*?)\\*';
const LIST_RE = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
const RULE_RE = /^(-{3,}|\*{3,}|_{3,})$/;
const TABLE_SEP_RE = /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
const CALLOUT_RE = /^\*\*(note|tip|warning|why\?):\*\*\s*/i;
const CALLOUT_TITLE = { note: 'Note', tip: 'Tip', warning: 'Warning', 'why?': 'Why?' };

const indentOf = line => line.length - line.trimStart().length;

export function plainText(text) {
  return text.replace(/`/g, '').replace(/\*\*/g, '').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').trim();
}

function link(label, href, ctx) {
  const kids = inline(label, ctx);
  if (/^https?:\/\//i.test(href)) return h('a', { href, target: '_blank', rel: 'noopener noreferrer' }, kids);
  const m = /^([^#]+\.md)(?:#.*)?$/.exec(href);
  const slug = m && ctx.slugFor ? ctx.slugFor(m[1]) : null;
  if (slug) return h('a', { href: `#/docs/${slug}` }, kids);
  return h('span', {}, kids);
}

function inline(text, ctx) {
  const re = new RegExp(INLINE_SRC, 'g'); // a fresh regex: inline() calls itself for bold and link text
  const out = [];
  let last = 0;
  let m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1] !== undefined) out.push(h('code', { text: m[1] }));
    else if (m[2] !== undefined) out.push(h('strong', {}, inline(m[2], ctx)));
    else if (m[3] !== undefined) out.push(link(m[3], m[4], ctx));
    else out.push(h('em', {}, inline(m[5], ctx)));
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function splitRow(row) {
  let s = row.trim();
  if (s.startsWith('|')) s = s.slice(1);
  if (s.endsWith('|') && !s.endsWith('\\|')) s = s.slice(0, -1);
  const cells = [];
  let cur = '';
  for (let k = 0; k < s.length; k++) {
    if (s[k] === '\\' && s[k + 1] === '|') { cur += '|'; k++; } else if (s[k] === '|') { cells.push(cur.trim()); cur = ''; } else cur += s[k];
  }
  cells.push(cur.trim());
  return cells;
}

function startsBlock(line, next) {
  const t = line.trim();
  return /^`{3,}/.test(t) || /^#{1,4}\s/.test(t) || RULE_RE.test(t) || t.startsWith('>') || LIST_RE.test(line)
    || (t.startsWith('|') && next !== undefined && TABLE_SEP_RE.test(next.trim()));
}

function blocks(lines, ctx, headings) {
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();
    if (!t) { i++; continue; }

    let m = /^(`{3,})\s*[\w+-]*\s*$/.exec(t);
    if (m) {
      const fence = m[1];
      const indent = indentOf(line);
      const body = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith(fence)) {
        body.push(lines[i].slice(Math.min(indent, indentOf(lines[i]))));
        i++;
      }
      i++;
      out.push(codeBlock(body.join('\n')));
      continue;
    }

    m = /^(#{1,4})\s+(.+?)\s*$/.exec(t);
    if (m) {
      const level = m[1].length;
      const el = h(`h${level}`, { class: 'doc-h' }, inline(m[2], ctx));
      headings.push({ level, text: plainText(m[2]), el });
      out.push(el);
      i++;
      continue;
    }

    if (RULE_RE.test(t)) { out.push(h('hr')); i++; continue; }

    if (t.startsWith('|') && i + 1 < lines.length && TABLE_SEP_RE.test(lines[i + 1].trim())) {
      const head = splitRow(t);
      const rows = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(splitRow(lines[i++]));
      out.push(h('div', { class: 'table-wrap' }, h('table', { class: 'doc-table' },
        h('thead', {}, h('tr', {}, head.map(c => h('th', {}, inline(c, ctx))))),
        h('tbody', {}, rows.map(r => h('tr', {}, head.map((_, c) => h('td', {}, inline(r[c] || '', ctx)))))))));
      continue;
    }

    if (t.startsWith('>')) {
      const inner = [];
      while (i < lines.length && lines[i].trim().startsWith('>')) inner.push(lines[i++].trim().replace(/^>\s?/, ''));
      const c = CALLOUT_RE.exec(inner[0]);
      if (c) {
        inner[0] = inner[0].slice(c[0].length);
        const kind = c[1].toLowerCase();
        out.push(h('div', { class: `callout ${kind === 'why?' ? 'why' : kind}`, role: 'note' },
          h('div', { class: 'callout-title', text: CALLOUT_TITLE[kind] }), blocks(inner, ctx, [])));
      } else {
        out.push(h('blockquote', {}, blocks(inner, ctx, [])));
      }
      continue;
    }

    m = LIST_RE.exec(line);
    if (m) {
      const base = m[1].length;
      const ordered = /\d/.test(m[2]);
      const start = ordered ? parseInt(m[2], 10) : 1;
      const items = [];
      while (i < lines.length) {
        const mm = LIST_RE.exec(lines[i]);
        if (!mm || mm[1].length !== base || /\d/.test(mm[2]) !== ordered) break;
        const width = mm[1].length + mm[2].length + 1;
        const body = [mm[3]];
        i++;
        while (i < lines.length) {
          const l = lines[i];
          if (!l.trim()) {
            let j = i;
            while (j < lines.length && !lines[j].trim()) j++;
            if (j < lines.length && indentOf(lines[j]) > base) { body.push(''); i++; continue; }
            break;
          }
          if (indentOf(l) > base) { body.push(l.replace(new RegExp(`^ {0,${width}}`), '')); i++; continue; }
          break;
        }
        items.push(body);
      }
      const lis = items.map(body => {
        let box = null;
        const task = /^\[( |x|X)\]\s+/.exec(body[0]);
        if (task) {
          body[0] = body[0].slice(task[0].length);
          box = h('input', { type: 'checkbox', disabled: true, checked: task[1] !== ' ', 'aria-hidden': 'true', class: 'doc-task' });
        }
        const kids = blocks(body, ctx, []);
        if (kids[0] && kids[0].tagName === 'P') kids.splice(0, 1, ...kids[0].childNodes);
        return h('li', { class: box ? 'task' : null }, box, kids);
      });
      out.push(ordered ? h('ol', { start: start !== 1 ? start : null }, lis) : h('ul', {}, lis));
      continue;
    }

    const para = [];
    do { para.push(lines[i].trim()); i++; } while (i < lines.length && lines[i].trim() && !startsBlock(lines[i], lines[i + 1]));
    out.push(h('p', {}, inline(para.join(' '), ctx)));
  }
  return out;
}

// Returns { nodes, headings: [{ level, text, el }] }. ctx.slugFor(file) maps "x.md" to a docs slug.
export function renderMarkdown(src, ctx = {}) {
  const headings = [];
  const nodes = blocks(src.replace(/\r\n?/g, '\n').split('\n'), ctx, headings);
  return { nodes, headings };
}
