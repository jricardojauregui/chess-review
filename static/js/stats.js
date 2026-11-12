// Stats page: aggregates over the user's analysed games, plus a batch
// "analyse my last N games" runner that reuses the SSE analysis endpoint.
import {
  $, CLS, accountName, api, badgeSVG, efforts, engineCount, enginesText, escapeHtml, estimateTime, presetByDepth,
  presetById, presets, saveSettings, settings, store,
} from './common.js';
import { askStopBatch, batchFraction, batchLine, currentBatch, startBatch } from './shell.js';
import { attachGamePreview } from './preview.js';

let trend = null;
let pending = [];     // games of the last N that still need analysis

const username = accountName();
let lastGames = [];
let listed = [];              // games in the table, newest first (for the hover preview)
let recent = [];              // the last N games from chess.com
let level = settings.engine;  // analysis level for the batch (default from Settings)
let running = false;          // a batch analysis is running on the server (started here or earlier)
$('#stats-who').textContent = username ? `${username} on chess.com` : '';
$('#level').innerHTML = presets.map(p => `<option value="${p.id}" ${p.id === level ? 'selected' : ''}>${p.name} · depth ${p.depth}</option>`).join('');
const paintEffort = () => {
  $('#effort').innerHTML = efforts.map(e =>
    `<option value="${e.id}" ${e.id === settings.effort ? 'selected' : ''}>${e.name} · ${enginesText(e.workers)}</option>`).join('');
};
paintEffort();
$('#count').value = store.get('statsCount', String(window.APP.statsGames));

const fmt = (v, suffix = '') => (v === null || v === undefined ? '–' : `${v}${suffix}`);

async function latestGames(username, n) {
  // Walk back through monthly archives until we have n games
  const first = (await api(`/api/games/${encodeURIComponent(username)}`)).data;
  let games = first.games;
  for (const month of first.archives.slice(1, 6)) {
    if (games.length >= n) break;
    const more = (await api(`/api/games/${encodeURIComponent(username)}?month=${month}`)).data;
    games = games.concat(more.games);
  }
  return games.slice(0, n);
}

async function load() {
  const n = Number($('#count').value);
  const error = $('#stats-error');
  error.hidden = true;
  $('#stats-empty').hidden = true;
  if (!username) {
    $('#stats-empty').hidden = false;
    $('#stats-empty').innerHTML = 'Link your chess.com account to see your stats. <a class="btn btn-small btn-primary" href="/settings#account">Link account</a>';
    return;
  }
  store.set('statsCount', String(n));
  try {
    recent = await latestGames(username, n);
    $('#batch').hidden = recent.length === 0 && !running;
    paintBatch();
    const { data } = await api(`/api/stats/${encodeURIComponent(username)}?n=${n}`);
    render(data);
  } catch (e) {
    error.textContent = e.message;
    error.hidden = false;
  }
}

/** Level picker + what the batch would do at that level (or what it is doing). */
function paintBatch() {
  const batch = currentBatch();
  const text = $('#batch-text');
  const button = $('#batch-start');
  $('#level').disabled = running;
  $('#batch-stop').hidden = !running;
  $('#batch-stop').disabled = !batch || batch.status !== 'running';
  $('#batch-progress').hidden = !running;
  if (running && batch) {
    // Already working (maybe started before you left this page): no second run
    const used = presetByDepth(batch.depth);
    $('#batch').classList.remove('warn');
    text.innerHTML = `Analysing ${batch.total} game${batch.total === 1 ? '' : 's'} at <b>${used ? used.name : `depth ${batch.depth}`}</b> ` +
      `with ${enginesText(engineCount())}. It keeps going if you leave this page.`;
    button.hidden = true;
    $('#batch-fill').style.width = `${100 * batchFraction(batch)}%`;
    $('#batch-label').textContent = batch.status === 'stopping' ? 'Stopping…' : batchLine(batch);
    return;
  }
  const p = presetById(level);
  // A game needs work when it has no analysis at this level or deeper
  pending = recent.filter(g => (g.analysed_depth || 0) < p.depth);
  const ready = recent.length - pending.length;
  const positions = pending.length * 70;
  $('#batch').classList.toggle('warn', p.cost >= 4 && pending.length > 0);
  if (!pending.length) {
    text.innerHTML = `All ${recent.length} games are analysed at <b>${p.name}</b> (depth ${p.depth}) or deeper.`;
  } else {
    text.innerHTML = `${ready} of your last ${recent.length} games are analysed at <b>${p.name}</b> (depth ${p.depth}) or deeper. ` +
      `Analysing the other ${pending.length} takes ${estimateTime(p, positions)} with ${enginesText(engineCount())}` +
      (p.cost >= 4 ? '. Consider a lighter level for batches.' : '.');
  }
  button.hidden = !pending.length;
  button.disabled = false;
  button.textContent = `Analyze ${pending.length} game${pending.length === 1 ? '' : 's'} at ${p.name}`;
  $('#batch-label').textContent = '';
}
$('#level').addEventListener('change', e => {
  if (running) { e.target.value = level; return; }
  level = e.target.value;
  paintBatch();
});
// Effort is a saved preference; during a run it applies from the next game
$('#effort').addEventListener('change', e => saveSettings({ effort: e.target.value }));
document.addEventListener('settingschange', e => { if (e.detail.effort) { paintEffort(); paintBatch(); } });

async function runBatch() {
  if (running) return;
  $('#batch-start').disabled = true;
  $('#stats-error').hidden = true;
  try {
    await startBatch(pending.map(g => g.id), presetById(level).depth);
  } catch (e) {
    $('#stats-error').textContent = e.message;
    $('#stats-error').hidden = false;
    $('#batch-start').disabled = false;
  }
}

// The batch runs on the server; shell.js polls it and tells every page.
document.addEventListener('batchupdate', e => {
  const { state, prev } = e.detail;
  const was = running;
  running = Boolean(state.active);
  // Coming back to this page mid-run: show the level that is being used
  const used = running ? presetByDepth(state.depth) : null;
  if (used && used.id !== level) { level = used.id; $('#level').value = level; }
  if (was && !running) { load(); return; }          // finished or stopped: refresh the numbers
  if (!running && prev === null) return;            // nothing going on
  if (username) paintBatch();
});
$('#batch-stop').addEventListener('click', askStopBatch);

function render(s) {
  const body = $('#stats-body');
  if (!s.games) {
    body.hidden = true;
    $('#stats-empty').hidden = false;
    $('#stats-empty').textContent = pending.length
      ? 'None of these games has been analysed yet. Use the button above to analyse them.'
      : 'No games found for this user.';
    return;
  }
  body.hidden = false;
  const o = s.outcomes;
  $('#tiles').innerHTML = [
    ['Games analysed', s.games, `${o.win} W · ${o.draw} D · ${o.loss} L`],
    ['Average accuracy', fmt(s.accuracy, '%'), `White ${fmt(s.accuracy_white, '%')} · Black ${fmt(s.accuracy_black, '%')}`],
    ['Blunders per game', fmt(s.blunders_per_game), `${s.totals.blunder} in total`],
    ['Mistakes per game', fmt(s.mistakes_per_game), `${s.totals.mistake} in total`],
    ['Misses per game', fmt(s.misses_per_game), `${s.totals.miss} in total`],
  ].map(([label, value, sub]) =>
    `<div class="card tile"><div class="label">${label}</div><div class="value">${value}</div><div class="sub">${sub}</div></div>`
  ).join('');

  // Openings
  $('#openings').innerHTML = `<table class="games"><thead><tr><th>Opening</th><th class="num">Games</th>
    <th>W / D / L</th><th class="num">Lost</th><th class="num">Accuracy</th></tr></thead><tbody>${
    s.openings.slice(0, 10).map(op => `<tr>
      <td>${escapeHtml(op.name)}</td><td class="num">${op.games}</td>
      <td><div class="wdl" title="${op.win} wins, ${op.draw} draws, ${op.loss} losses">
        ${op.win ? `<span class="w" style="flex:${op.win}"></span>` : ''}${op.draw ? `<span class="d" style="flex:${op.draw}"></span>` : ''}${op.loss ? `<span class="l" style="flex:${op.loss}"></span>` : ''}</div>
        <span class="muted" style="font-size:12px">${op.win} / ${op.draw} / ${op.loss}</span></td>
      <td class="num">${op.loss_rate}%</td><td class="num">${fmt(op.accuracy, '%')}</td></tr>`).join('')
  }</tbody></table>`;

  // Time pressure
  const tp = s.time_pressure;
  if (!tp.pressure.moves && !tp.normal.moves) {
    $('#pressure').innerHTML = '<div class="muted">No clock data in these games.</div>';
  } else {
    const maxRate = Math.max(tp.pressure.error_rate || 0, tp.normal.error_rate || 0, 1);
    const row = (label, d, warn) => `<div class="bar-pair"><span>${label}</span>
      <div class="bar-track"><div class="bar-fill ${warn ? 'warn' : ''}" style="width:${(100 * (d.error_rate || 0)) / maxRate}%"></div></div>
      <b class="num">${fmt(d.error_rate, '%')}</b></div>
      <div class="muted" style="font-size:12px;margin:-4px 0 8px 140px">${d.errors} errors in ${d.moves} moves · accuracy ${fmt(d.accuracy, '%')}</div>`;
    $('#pressure').innerHTML =
      `<div class="muted" style="font-size:13px;margin-bottom:6px">Share of my moves that were a mistake, miss or blunder</div>
       ${tp.pressure.moves ? row('Low on time', tp.pressure, true)
          : '<div class="muted" style="font-size:13px;margin:8px 0">You did not play any move low on time in these games.</div>'}${row('Normal time', tp.normal, false)}
       <div class="muted" style="font-size:12px">Low on time = under 10% of the starting clock (or under 10 seconds).</div>`;
  }

  // Classification totals
  const totalMoves = Object.values(s.totals).reduce((a, b) => a + b, 0) || 1;
  const maxCount = Math.max(...Object.values(s.totals), 1);
  $('#totals').innerHTML = Object.entries(s.totals).filter(([, n]) => n > 0).map(([cls, n]) =>
    `<div class="bar-pair"><span>${badgeSVG(cls, 18)} ${CLS[cls].label}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${(100 * n) / maxCount}%;background:${CLS[cls].color}"></div></div>
      <span class="num">${n} <span class="muted" style="font-size:12px">${Math.round((100 * n) / totalMoves)}%</span></span></div>`
  ).join('');

  // Game list
  $('#game-list').className = 'table-scroll games-scroll';
  $('#game-list').innerHTML = `<table class="games"><thead><tr><th></th><th>Opponent</th><th>Date</th><th>Opening</th>
    <th class="num">Accuracy</th><th class="num">Mistakes</th><th class="num">Misses</th><th class="num">Blunders</th><th></th></tr></thead><tbody>${
    s.game_list.map((g, i) => `<tr>
      <td><span class="outcome ${g.outcome}">${{ win: 'W', loss: 'L', draw: 'D' }[g.outcome] || '–'}</span></td>
      <td><span class="piece-dot ${g.color === 'w' ? 'b' : 'w'}"></span><b class="opp-name" data-index="${i}">${escapeHtml(g.opponent)}</b> <span class="muted">(${g.opponent_rating ?? '?'})</span></td>
      <td>${g.date || ''}</td><td class="opening-cell">${escapeHtml(g.opening)}</td>
      <td class="num"><b>${fmt(g.accuracy, '%')}</b></td><td class="num">${g.mistakes}</td><td class="num">${g.misses}</td><td class="num">${g.blunders}</td>
      <td class="num"><a class="btn btn-small" href="/review/${g.id}">Review</a></td></tr>`).join('')
  }</tbody></table>`;

  listed = s.game_list;
  lastGames = s.game_list.slice().reverse();
  renderTrend(lastGames);
}

/** Our own tooltip for the accuracy chart (Chart.js "external" tooltip). */
function trendTooltip(games) {
  return ({ chart, tooltip }) => {
    const holder = chart.canvas.parentNode;
    let tip = holder.querySelector('.chart-tip');
    if (!tip) {
      tip = document.createElement('div');
      tip.className = 'chart-tip';
      holder.appendChild(tip);
    }
    const point = tooltip.dataPoints && tooltip.dataPoints[0];
    if (tooltip.opacity === 0 || !point) { tip.classList.remove('show'); return; }
    const index = point.dataIndex, g = games[index];
    if (tip.dataset.index !== String(index)) {          // only rebuild when the game changes
      tip.dataset.index = String(index);
      const letter = { win: 'W', loss: 'L', draw: 'D' }[g.outcome] || '–';
      const err = (cls, n) => `<span class="${n ? '' : 'zero'}" title="${CLS[cls].label}">${badgeSVG(cls, 18)}${n}</span>`;
      tip.innerHTML = `
        <div class="head"><span class="outcome ${g.outcome}">${letter}</span>
          <span class="who">vs ${escapeHtml(g.opponent)} <span class="muted">(${g.opponent_rating ?? '?'})</span></span></div>
        <div class="sub">${escapeHtml([g.date, g.opening].filter(Boolean).join(' · '))}</div>
        <div class="acc">${fmt(g.accuracy, '%')}<small>accuracy</small></div>
        <div class="errs">${err('mistake', g.mistakes)}${err('miss', g.misses)}${err('blunder', g.blunders)}</div>
        <div class="hint">Click to open the review</div>`;
    }
    // Beside the point (never under the pointer), kept inside the chart
    const gap = 16, w = tip.offsetWidth, h = tip.offsetHeight;
    const x = point.element.x, y = point.element.y;
    let left = x + gap;
    if (left + w > holder.clientWidth) left = x - gap - w;
    const top = Math.max(0, Math.min(holder.clientHeight - h, y - h / 2));
    tip.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
    tip.classList.add('show');
  };
}

function renderTrend(games) {
  if (trend) trend.destroy();
  const colors = { win: CLS.best.color, loss: CLS.blunder.color, draw: CLS.forced.color, other: CLS.forced.color };
  const css = getComputedStyle(document.documentElement);
  const ink = css.getPropertyValue('--muted').trim(), grid = css.getPropertyValue('--line').trim();
  const accent = css.getPropertyValue('--accent').trim(), surface = css.getPropertyValue('--panel').trim();
  // A soft vertical guide through the game under the pointer
  const guide = {
    id: 'guide',
    beforeDatasetsDraw(chart) {
      const active = chart.getActiveElements()[0];
      if (!active) return;
      const { ctx, chartArea: area } = chart;
      ctx.save();
      ctx.strokeStyle = grid; ctx.lineWidth = 1.5; ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.moveTo(active.element.x, area.top); ctx.lineTo(active.element.x, area.bottom); ctx.stroke();
      ctx.restore();
    },
  };
  trend = new Chart($('#trend'), {
    type: 'line',
    data: {
      labels: games.map((_, i) => i + 1),
      datasets: [{
        data: games.map(g => g.accuracy),
        borderColor: accent, borderWidth: 2, tension: 0.25, spanGaps: true,
        pointRadius: 5, pointHoverRadius: 8, pointBorderColor: surface, pointBorderWidth: 2, pointHoverBorderWidth: 3,
        pointBackgroundColor: games.map(g => colors[g.outcome]),
        pointHoverBackgroundColor: games.map(g => colors[g.outcome]), pointHoverBorderColor: surface,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      // no entrance animation, but hovered points grow and shrink smoothly
      animation: { duration: 0 },
      transitions: { active: { animation: { duration: 160 } } },
      // the nearest game along the x axis, wherever the pointer is in the chart
      interaction: { mode: 'index', intersect: false, axis: 'x' },
      layout: { padding: { top: 10, right: 8 } },
      scales: {
        x: { grid: { display: false }, ticks: { color: ink }, border: { color: grid } },
        y: { suggestedMin: 40, max: 100, grid: { color: grid }, ticks: { color: ink, callback: v => `${v}%` }, border: { display: false } },
      },
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false, external: trendTooltip(games) },
      },
      onHover(event, els) { event.native.target.style.cursor = els.length ? 'pointer' : 'default'; },
      onClick(_e, els) { if (els[0]) location.href = `/review/${games[els[0].index].id}`; },
    },
    plugins: [guide],
  });
}

// Final position while hovering an opponent's name in the games table
attachGamePreview($('#game-list'), name => {
  const g = listed[Number(name.dataset.index)];
  return g ? { ...g, hero: g.color } : null;
});

$('#count').addEventListener('change', () => load());
$('#batch-start').addEventListener('click', runBatch);
// Chart colours follow the theme
document.addEventListener('settingschange', e => { if (e.detail.theme && lastGames.length) renderTrend(lastGames); });
load();
