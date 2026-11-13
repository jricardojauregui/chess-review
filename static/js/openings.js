// Openings: the catalogue. Lesson cards (ranked for the linked account) and a
// search over the whole database of named openings.
import { Chessground } from '../vendor/chessground.min.js';
import { $, api, escapeHtml, showCoach, store } from './common.js';

let data = null;
let filter = store.get('openingsFilter', 'for-you');

/** Lessons whose main line was completed in practice mode: { id: true }. */
export function learned() {
  try { return JSON.parse(store.get('openingsLearned', '{}')) || {}; } catch (e) { return {}; }
}

const WHITE_FAMILIES = ['e4', 'd4', 'flank'];
const FAMILY_ORDER = ['e4', 'd4', 'flank', 'vs_e4', 'vs_d4'];

function coachText(p) {
  if (!data.username) return "Pick any opening and I'll walk you through it move by move. Link your chess.com account and I'll also tell you which ones fit the way you play.";
  if (!p.games) return "I don't have games of yours yet. Open the Games tab once so I can see what you play; meanwhile, pick any opening and I'll explain it move by move.";
  const parts = [`I went through your ${p.games} games.`];
  if (p.white.move) parts.push(`With White you start with 1.${p.white.move} in ${p.white.share}% of them.`);
  const replies = [];
  if (p.vs_e4.move) replies.push(`against 1.e4 you answer 1...${p.vs_e4.move} (${p.vs_e4.share}%)`);
  if (p.vs_d4.move) replies.push(`against 1.d4, 1...${p.vs_d4.move} (${p.vs_d4.share}%)`);
  if (replies.length) parts.push(`With Black, ${replies.join(' and ')}.`);
  parts.push('Under "For you" are the openings I would study first, each with the reason. Open one and I\'ll explain every move.');
  return parts.join(' ');
}

function wdlHTML(t) {
  if (!t.games) return '';
  return `<div class="wdl" title="${t.win} wins, ${t.draw} draws, ${t.loss} losses">
    ${t.win ? `<span class="w" style="flex:${t.win}"></span>` : ''}${t.draw ? `<span class="d" style="flex:${t.draw}"></span>` : ''}${t.loss ? `<span class="l" style="flex:${t.loss}"></span>` : ''}</div>`;
}

function cardHTML(c, withReasons) {
  const done = learned()[c.id];
  const stars = [1, 2, 3, 4, 5].map(i => `<i class="${i <= c.popularity ? 'fill' : ''}"></i>`).join('');
  const reasons = withReasons && c.reasons.length
    ? `<ul class="lc-reasons">${c.reasons.slice(0, 3).map(r => `<li>${escapeHtml(r)}</li>`).join('')}</ul>` : '';
  const mine = c.plays.games
    ? `<div class="lc-mine">${wdlHTML(c.plays)}<span class="muted">${c.plays.games} game${c.plays.games === 1 ? '' : 's'} · ${c.plays.win}W ${c.plays.draw}D ${c.plays.loss}L</span></div>` : '';
  // What the user's own games say about this opening: shown on hover, so every card is the same size
  const more = reasons || mine || c.needs_work
    ? `<div class="lc-more card" role="tooltip">${c.needs_work ? '<span class="tag work">Needs work</span>' : ''}${reasons}${mine}</div>` : '';
  return `<a class="card lesson-card ${c.needs_work ? 'needs-work' : ''} ${more ? 'has-more' : ''}" href="/openings/${c.id}">
    <div class="mini-board"><div class="mini" data-fen="${c.fen}" data-side="${c.side}"></div></div>
    <div class="lc-body">
      <div class="lc-top"><span class="piece-dot ${c.side}" title="${c.side === 'w' ? 'For White' : 'For Black'}"></span>
        <b class="lc-name">${escapeHtml(c.name)}</b>
        ${done ? '<span class="tag learned" title="You completed the main line in practice">✓ Learned</span>' : ''}</div>
      <div class="lc-moves">${escapeHtml(c.moves)}</div>
      <div class="lc-tagline">${escapeHtml(c.tagline)}</div>
      <div class="lc-meta"><span class="tag">${c.eco}</span><span class="tag level-${c.level}">${c.level_name}</span>
        <span class="meter" title="Popularity">${stars}</span>${more ? '<span class="lc-dot" aria-hidden="true"></span>' : ''}</div>
    </div>${more}</a>`;
}

function pick() {
  const all = data.lessons.slice();
  const byName = (a, b) => a.name.localeCompare(b.name);
  if (filter === 'for-you') return all.sort((a, b) => b.fit - a.fit || byName(a, b)).slice(0, 8);
  if (filter === 'popular') return all.sort((a, b) => b.popularity - a.popularity || byName(a, b));
  if (filter === 'white') return all.filter(c => WHITE_FAMILIES.includes(c.family)).sort((a, b) => FAMILY_ORDER.indexOf(a.family) - FAMILY_ORDER.indexOf(b.family) || b.popularity - a.popularity);
  if (filter === 'vs_e4' || filter === 'vs_d4') return all.filter(c => c.family === filter).sort((a, b) => b.popularity - a.popularity);
  return all.sort((a, b) => FAMILY_ORDER.indexOf(a.family) - FAMILY_ORDER.indexOf(b.family) || b.popularity - a.popularity);
}

const NOTES = {
  'for-you': 'Ranked by what you already play, what you keep running into, and your level.',
  popular: 'The openings you will meet most often.',
  white: 'Openings to play with the white pieces.',
  vs_e4: 'Defences for when White opens with the king\'s pawn.',
  vs_d4: 'Defences for when White opens with the queen\'s pawn.',
  all: '',
};

function paint() {
  for (const b of document.querySelectorAll('#filters [data-filter]')) b.classList.toggle('on', b.dataset.filter === filter);
  const list = pick();
  $('#filter-note').textContent = NOTES[filter] || `${data.lessons.length} lessons, and ${data.database_size.toLocaleString()} named openings in the search.`;
  $('#lesson-grid').innerHTML = list.map(c => cardHTML(c, filter === 'for-you')).join('');
  for (const node of document.querySelectorAll('#lesson-grid .mini')) {
    Chessground(node, {
      fen: node.dataset.fen, orientation: node.dataset.side === 'b' ? 'black' : 'white',
      viewOnly: true, coordinates: false, drawable: { enabled: false },
    });
  }
}

$('#filters').addEventListener('click', e => {
  const button = e.target.closest('[data-filter]');
  if (!button || !data) return;
  filter = button.dataset.filter;
  store.set('openingsFilter', filter);
  paint();
});

// The hover box opens under its card, or above it when it would run off the screen
$('#lesson-grid').addEventListener('mouseover', e => {
  const card = e.target.closest('.lesson-card.has-more');
  if (!card || card.contains(e.relatedTarget)) return;
  const more = card.querySelector('.lc-more');
  more.style.display = 'grid';                       // it is display:none until hovered: measure it
  const height = more.offsetHeight;
  more.style.display = '';
  card.classList.toggle('up', card.getBoundingClientRect().bottom + height > window.innerHeight - 8);
});

// ------------------------------------------------------------------ search
let searchTimer = null, searchToken = 0;
async function runSearch(q) {
  const token = ++searchToken;
  const box = $('#search-box');
  if (!q.trim()) { box.hidden = true; $('#browse').hidden = false; return; }
  $('#browse').hidden = true;
  box.hidden = false;
  try {
    const { data: found } = await api(`/api/openings/search?q=${encodeURIComponent(q)}`);
    if (token !== searchToken) return;
    const rows = found.results;
    $('#search-title').textContent = rows.length ? `${rows.length}${rows.length >= 40 ? '+' : ''} openings` : 'No opening matches that';
    $('#search-results').innerHTML = rows.map(r => `<a class="named-row" href="/openings/${r.id}">
      <span class="tag">${r.eco}</span><b>${escapeHtml(r.name)}</b><span class="muted">${escapeHtml(r.moves)}</span></a>`).join('');
  } catch (e) {
    $('#search-title').textContent = e.message;
    $('#search-results').innerHTML = '';
  }
}
$('#opening-search').addEventListener('input', e => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => runSearch(e.target.value), 180);
});

// -------------------------------------------------------------------- boot
showCoach($('#coach-avatar'), 'thinking');
api('/api/openings').then(({ data: d }) => {
  data = d;
  if (!d.profile.games && filter === 'for-you') filter = 'popular';
  showCoach($('#coach-avatar'), 'happy');
  $('#coach-text').textContent = coachText(d.profile);
  paint();
}).catch(e => {
  $('#openings-error').textContent = e.message;
  $('#openings-error').hidden = false;
});
