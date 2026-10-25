// The Docs tab: sidebar of pages, the page itself, "On this page", search, previous / next.
import { get } from '../api.js';
import { h, clear, button, toast } from '../ui.js';
import { plainText, renderMarkdown } from '../markdown.js';

const cache = { nav: null, pages: new Map() };

async function loadNav() {
  if (!cache.nav) cache.nav = await get('docs');
  return cache.nav;
}

async function loadPage(slug) {
  if (!cache.pages.has(slug)) cache.pages.set(slug, await get(`docs/${encodeURIComponent(slug)}`));
  return cache.pages.get(slug);
}

const flatten = nav => nav.groups.flatMap(g => g.pages.map(p => ({ ...p, group: g.title })));

export async function renderDocs(view) {
  const loading = h('div', { class: 'muted', text: 'Loading the docs…' });
  view.append(loading);
  let nav;
  try {
    nav = await loadNav();
  } catch (e) {
    if (!loading.isConnected) return;
    return clear(view, h('div', { class: 'banner err' }, h('div', { class: 'msg', text: e.message })));
  }
  if (!loading.isConnected) return; // the user went to another tab while the docs loaded
  const pages = flatten(nav);
  const wanted = location.hash.replace(/^#\/?/, '').split('/')[1];
  const current = pages.find(p => p.slug === wanted) || pages[0];
  const files = new Map(pages.map(p => [p.file, p.slug]));

  const article = h('article', { class: 'docs-main' });
  const toc = h('aside', { class: 'docs-toc', 'aria-label': 'On this page' });
  const results = h('div', { class: 'docs-results hidden' });
  const side = h('aside', { class: 'docs-side', id: 'docs-side' });

  // ── sidebar ──
  const search = h('input', { class: 'input', type: 'search', placeholder: 'Search the docs', 'aria-label': 'Search the docs' });
  const menuBtn = button('Menu', { kind: 'small', onclick: () => side.classList.toggle('open') });
  menuBtn.classList.add('docs-menu-btn');
  clear(side,
    search,
    h('nav', { 'aria-label': 'Docs pages' }, nav.groups.map(g => h('div', { class: 'docs-group' },
      h('div', { class: 'section-title', text: g.title }),
      g.pages.map(p => h('a', {
        href: `#/docs/${p.slug}`, class: `docs-link${p.slug === current.slug ? ' active' : ''}`,
        'aria-current': p.slug === current.slug ? 'page' : null, text: p.title,
      }))))));

  view.replaceChildren(
    h('div', { class: 'docs' }, menuBtn, side, h('div', { class: 'docs-center' }, results, article), toc));
  window.scrollTo(0, 0);
  document.title = `${current.title} · Docs · Gateway Manager`;

  // ── page ──
  const drawPage = async () => {
    clear(article, h('div', { class: 'muted', text: 'Loading…' }));
    try {
      const page = await loadPage(current.slug);
      const { nodes, headings } = renderMarkdown(page.markdown, { slugFor: file => files.get(file) });
      const i = pages.indexOf(current);
      const prev = pages[i - 1];
      const next = pages[i + 1];
      clear(article,
        h('div', { class: 'crumbs faint', text: `${current.group}  /  ${current.title}` }),
        h('div', { class: 'doc' }, nodes),
        h('nav', { class: 'pager', 'aria-label': 'Previous and next page' },
          prev ? h('a', { class: 'pager-link', href: `#/docs/${prev.slug}` },
            h('span', { class: 'faint', text: 'Previous' }), h('span', { text: prev.title })) : h('span'),
          next ? h('a', { class: 'pager-link next', href: `#/docs/${next.slug}` },
            h('span', { class: 'faint', text: 'Next' }), h('span', { text: next.title })) : h('span')));
      const entries = headings.filter(x => x.level === 2 || x.level === 3);
      clear(toc, entries.length ? h('div', {},
        h('div', { class: 'section-title', text: 'On this page' }),
        entries.map(x => h('a', {
          href: '#', class: `toc-link l${x.level}`, text: x.text,
          onclick: e => { e.preventDefault(); x.el.scrollIntoView({ behavior: 'smooth', block: 'start' }); },
        }))) : null);
    } catch (e) {
      clear(article, h('div', { class: 'banner err' }, h('div', { class: 'msg', text: e.message })));
    }
  };

  // ── search ──
  let timer;
  const runSearch = async () => {
    const q = search.value.trim().toLowerCase();
    toc.classList.toggle('hidden', !!q); // "On this page" belongs to the open page, not to the results
    if (!q) {
      results.classList.add('hidden');
      article.classList.remove('hidden');
      return;
    }
    try {
      await Promise.all(pages.map(p => loadPage(p.slug)));
    } catch (e) {
      return toast(e.message, 'err');
    }
    if (search.value.trim().toLowerCase() !== q) return; // the box changed while loading
    const words = q.split(/\s+/);
    const hits = [];
    for (const p of pages) {
      const text = plainText(cache.pages.get(p.slug).markdown).replace(/[#>|]/g, ' ').replace(/\s+/g, ' ');
      const lower = text.toLowerCase();
      const title = p.title.toLowerCase();
      if (!words.every(w => lower.includes(w) || title.includes(w))) continue;
      const score = words.reduce((s, w) => s + (title.includes(w) ? 10 : 0) + (lower.split(w).length - 1), 0);
      hits.push({ p, text, lower, score });
    }
    hits.sort((a, b) => b.score - a.score);
    article.classList.add('hidden');
    results.classList.remove('hidden');
    clear(results,
      h('h1', { text: hits.length ? `${hits.length} result${hits.length === 1 ? '' : 's'}` : 'No results' }),
      hits.length ? null : h('p', { class: 'muted', text: `Nothing matches "${search.value.trim()}". Try one word, such as "basePath" or "docker".` }),
      hits.map(({ p, text, lower }) => {
        const at = Math.max(0, lower.indexOf(words.find(w => lower.includes(w)) || ''));
        const from = Math.max(0, at - 60);
        return h('a', { class: 'docs-hit card card-body', href: `#/docs/${p.slug}`, onclick: () => { search.value = ''; } },
          h('div', { class: 'faint', text: p.group }),
          h('h3', { text: p.title }),
          h('p', { class: 'muted' }, highlight(`${from > 0 ? '…' : ''}${text.slice(from, from + 170)}…`, words)));
      }));
  };
  search.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(runSearch, 200); });

  await drawPage();
}

// Wrap the search words in <mark> without innerHTML.
function highlight(text, words) {
  const re = new RegExp(`(${words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'ig');
  return text.split(re).map((part, i) => (i % 2 ? h('mark', { text: part }) : part));
}
