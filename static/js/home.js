// Home screen: the linked account's games (with a hover preview of the final
// position) and opening a game by its chess.com ID / link.
import { $, accountName, api, escapeHtml, formatTimeControl, presetByDepth, showCoach } from './common.js';
import { attachGamePreview } from './preview.js';
import { linkAccount } from './shell.js';

const username = accountName();
let games = [];

// ------------------------------------------------------------ onboarding
if (!username) {
  showCoach($('#home-coach'), 'happy');
  // a friendly wave every few seconds while it waits
  setInterval(() => showCoach($('#home-coach'), 'happy'), 6000);
  $('#onboard-form').addEventListener('submit', e => {
    e.preventDefault();
    linkAccount($('#onboard-input').value, $('#onboard-error'));
  });
}

// ------------------------------------------------------------- game list
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
  'September', 'October', 'November', 'December'];
let archives = [];        // "YYYY-MM", newest first

/** Year + month drop-downs, limited to the months that actually have games. */
function paintSlicers(current) {
  const [year, month] = current.split('-');
  const years = [...new Set(archives.map(a => a.slice(0, 4)))];
  $('#year').innerHTML = years.map(y => `<option ${y === year ? 'selected' : ''}>${y}</option>`).join('');
  $('#month').innerHTML = archives.filter(a => a.startsWith(year)).map(a => {
    const m = a.slice(5);
    return `<option value="${m}" ${m === month ? 'selected' : ''}>${MONTHS[Number(m) - 1]}</option>`;
  }).join('');
}

function renderGames(data) {
  const body = $('#games-body');
  games = data.games;
  archives = data.archives;
  paintSlicers(data.month);
  if (!games.length) {
    body.innerHTML = '<div class="empty">No standard chess games in this month.</div>';
    return;
  }
  const rows = games.map((g, i) => {
    const me = g.hero === 'w' ? g.white : g.black;
    const opp = g.hero === 'w' ? g.black : g.white;
    const letter = { win: 'W', loss: 'L', draw: 'D' }[g.outcome] || '–';
    const level = g.analysed_depth ? presetByDepth(g.analysed_depth) : null;
    const action = g.analysed_depth
      ? `<span class="tag" title="Analysed at depth ${g.analysed_depth}">✓ ${level ? level.name : 'Reviewed'}</span> <a class="btn btn-small" href="/review/${g.id}">Open</a>`
      : `<a class="btn btn-small btn-primary" href="/review/${g.id}">Review</a>`;
    return `<tr data-index="${i}">
      <td><span class="outcome ${g.outcome}" title="${g.outcome}">${letter}</span></td>
      <td><span class="piece-dot ${g.hero === 'w' ? 'b' : 'w'}"></span><b class="opp-name">${escapeHtml(opp.name)}</b> <span class="muted">(${opp.rating ?? '?'})</span></td>
      <td class="num">${me.rating ?? '?'}</td>
      <td>${g.result.replace('1/2-1/2', '½-½')}</td>
      <td>${formatTimeControl(g.time_control)} <span class="muted">${escapeHtml(g.time_class || '')}</span></td>
      <td>${g.date || ''}</td>
      <td class="opening-cell">${escapeHtml(g.opening || '–')}</td>
      <td class="num">${action}</td>
    </tr>`;
  }).join('');
  body.innerHTML = `<div class="table-scroll games-scroll"><table class="games">
    <thead><tr><th></th><th>Opponent</th><th class="num">My rating</th><th>Result</th>
      <th>Time control</th><th>Date</th><th>Opening</th><th></th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

async function loadGames(month) {
  const error = $('#games-error'), body = $('#games-body');
  error.hidden = true;
  body.innerHTML = '<div class="empty">Loading games<span class="dots"></span></div>';
  try {
    const query = month ? `?month=${month}` : '';
    const { data } = await api(`/api/games/${encodeURIComponent(username)}${query}`);
    renderGames(data);
  } catch (e) {
    body.innerHTML = '';
    error.textContent = e.message;
    error.hidden = false;
  }
}

if (username) {
  const body = $('#games-body');
  // Final position while hovering the opponent's name
  attachGamePreview(body, name => games[Number(name.closest('tr').dataset.index)]);
  // The whole row opens the game (the button still works on its own)
  body.addEventListener('click', e => {
    const row = e.target.closest('tr[data-index]');
    if (row && !e.target.closest('a')) location.href = `/review/${games[Number(row.dataset.index)].id}`;
  });
  $('#month').addEventListener('change', () => loadGames(`${$('#year').value}-${$('#month').value}`));
  // Changing the year jumps to its most recent month with games
  $('#year').addEventListener('change', () => loadGames(archives.find(a => a.startsWith($('#year').value))));
  loadGames();
}

// ------------------------------------------------------------ game by id
$('#lookup-form').addEventListener('submit', async e => {
  e.preventDefault();
  const error = $('#lookup-error'), button = $('#lookup-go');
  error.hidden = true;
  button.disabled = true;
  button.textContent = 'Looking…';
  try {
    const { data } = await api('/api/games/lookup', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ref: $('#lookup-input').value }),
    });
    location.href = `/review/${data.game_id}`;
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
    button.disabled = false;
    button.textContent = 'Open';
  }
});

api('/api/status').then(({ data }) => { $('#engine-warning').hidden = data.ok; }).catch(() => {});
