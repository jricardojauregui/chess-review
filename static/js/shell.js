// Runs on every page: theme toggle and the account-linking helper shared by
// the home and settings pages.
import './i18n.js';
import { $, api, efforts, el, escapeHtml, playSound, presetByDepth, saveSettings, settings, store } from './common.js';

$('#theme-toggle').addEventListener('click', () =>
  saveSettings({ theme: settings.theme === 'dark' ? 'light' : 'dark' }));

// Quick mute: the same setting as "Move sounds" in Settings
$('#sound-toggle').addEventListener('click', () => {
  saveSettings({ sound: !settings.sound });
  if (settings.sound) playSound('move');            // so you hear that it is back on
});

// Language: saved with the other settings; the page reloads so the server's
// coach texts come back in the new language too.
$('#lang-toggle').addEventListener('click', async () => {
  await saveSettings({ lang: settings.lang === 'es' ? 'en' : 'es' });
  location.reload();
});

/** Link a chess.com account, then reload so every page picks it up. */
export async function linkAccount(username, errorBox) {
  if (errorBox) errorBox.hidden = true;
  try {
    await api('/api/account', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: (username || '').trim() }),
    });
    location.reload();
  } catch (e) {
    if (errorBox) { errorBox.textContent = e.message; errorBox.hidden = false; }
  }
}

// ------------------------------------------------------------------ modal
/**
 * Small confirmation dialog. `actions` is [{ label, value, kind }] (kind:
 * 'primary' | 'danger' | undefined). Resolves with the chosen value, or null
 * when it is dismissed (Escape / click outside).
 */
export function modal({ title, text, actions }) {
  return new Promise(resolve => {
    const back = el('div', { class: 'modal-back' });
    back.innerHTML = `<div class="modal card" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
        <h3>${escapeHtml(title)}</h3><p>${escapeHtml(text)}</p>
        <div class="modal-actions">${actions.map((a, i) =>
          `<button class="btn ${a.kind === 'primary' ? 'btn-primary' : ''} ${a.kind === 'danger' ? 'btn-danger' : ''}" data-i="${i}">${escapeHtml(a.label)}</button>`).join('')}</div>
      </div>`;
    const close = value => { document.removeEventListener('keydown', onKey, true); back.remove(); resolve(value); };
    const onKey = e => { if (e.key === 'Escape') { e.stopPropagation(); close(null); } };
    back.addEventListener('click', e => {
      const button = e.target.closest('[data-i]');
      if (button) close(actions[Number(button.dataset.i)].value);
      else if (e.target === back) close(null);
    });
    document.addEventListener('keydown', onKey, true);
    document.body.appendChild(back);
    back.querySelector('.btn-primary, .btn').focus();
  });
}

// ------------------------------------------------- batch analysis (global)
// "Analyze my last N games" runs on the server, so it survives moving between
// pages. Every page shows it in a card at the bottom right, with a Stop button.
let batchState = null;
let pollTimer = null;
let widget = null;

/** Latest known state of the batch analysis (null until the first answer). */
export const currentBatch = () => batchState;

function setBatch(state) {
  const prev = batchState;
  batchState = state;
  paintWidget();
  document.dispatchEvent(new CustomEvent('batchupdate', { detail: { state, prev } }));
  if (state.active && !pollTimer) pollTimer = setInterval(pollBatch, 700);
  if (!state.active && pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

async function pollBatch() {
  try { setBatch((await api('/api/batch')).data); } catch (e) { /* server restarting: try again on the next tick */ }
}

/** Start analysing `gameIds` at `depth` (throws if one is already running). */
export async function startBatch(gameIds, depth) {
  try {
    const { data } = await api('/api/batch', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ game_ids: gameIds, depth }),
    });
    setBatch(data);
  } catch (e) {
    pollBatch();
    throw e;
  }
}

/** Ask what to do with the finished games, then stop the batch. */
export async function askStopBatch() {
  const s = batchState;
  if (!s || s.status !== 'running') return;
  const n = s.completed;
  const choice = await modal(n > 0 ? {
    title: 'Stop the analysis?',
    text: `${n} game${n === 1 ? ' is' : 's are'} already fully analysed at this level. You can keep ${n === 1 ? 'it' : 'them'}, or revert ${n === 1 ? 'it' : 'them'} to how ${n === 1 ? 'it was' : 'they were'} before this run. The game in progress is discarded either way.`,
    actions: [
      { label: 'Keep analysing', value: null },
      { label: `Stop and revert ${n === 1 ? 'it' : `all ${n}`}`, value: 'revert', kind: 'danger' },
      { label: `Stop, keep ${n === 1 ? 'it' : `the ${n}`}`, value: 'keep', kind: 'primary' },
    ],
  } : {
    title: 'Stop the analysis?',
    text: 'No game has been finished yet. The game in progress will be discarded.',
    actions: [{ label: 'Keep analysing', value: null }, { label: 'Stop analysis', value: 'keep', kind: 'primary' }],
  });
  if (!choice) return;
  const { data } = await api('/api/batch/stop', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ revert: choice === 'revert' }),
  });
  setBatch(data);
}

/** Fraction (0..1) of the batch that is done, counting the game in progress. */
export function batchFraction(s) {
  if (!s || !s.total) return 0;
  if (s.status === 'done') return 1;
  const part = s.positions ? s.done / s.positions : 0;
  return Math.min(1, (s.index + part) / s.total);
}

/** "Game 3/12 vs someone · move 23/61" */
export function batchLine(s) {
  const move = s.positions ? ` · move ${Math.min(s.done + 1, s.positions)}/${s.positions}` : '';
  return `Game ${Math.min(s.index + 1, s.total)}/${s.total} vs ${s.label}${move}`;
}

function paintWidget() {
  const s = batchState;
  const dismissed = store.get('batchDismissed') === String(s && s.id);
  const show = s && s.id && (s.active || !dismissed);
  if (!show) { if (widget) widget.hidden = true; return; }
  if (!widget) {
    widget = el('aside', { class: 'batch-widget card', role: 'status', 'aria-live': 'polite' });
    widget.innerHTML = `
      <div class="bw-head"><b class="bw-title"></b><span class="bw-count"></span>
        <button class="bw-close" title="Dismiss" aria-label="Dismiss">×</button></div>
      <div class="bw-sub"></div>
      <div class="progress"><div class="progress-fill"></div></div>
      <div class="bw-actions">
        <label class="bw-effort" title="How much of the CPU the engine may use. Applies from the next game.">Effort
          <select aria-label="Effort">${efforts.map(e => `<option value="${e.id}">${e.name}</option>`).join('')}</select></label>
        <span class="spacer"></span>
        <a class="btn btn-small bw-stats" href="/stats">Open stats</a>
        <button class="btn btn-small btn-danger bw-stop">Stop</button>
      </div>`;
    widget.querySelector('.bw-stop').addEventListener('click', askStopBatch);
    widget.querySelector('.bw-close').addEventListener('click', () => {
      store.set('batchDismissed', String(batchState.id));
      widget.hidden = true;
    });
    widget.querySelector('select').addEventListener('change', e => saveSettings({ effort: e.target.value }));
    document.body.appendChild(widget);
  }
  widget.hidden = false;
  const level = presetByDepth(s.depth);
  const levelName = level ? level.name : `depth ${s.depth}`;
  const title = {
    running: 'Analyzing games<span class="dots"></span>', stopping: 'Stopping<span class="dots"></span>',
    done: 'Analysis finished', stopped: 'Analysis stopped', error: 'Analysis failed',
  }[s.status] || '';
  const titleNode = widget.querySelector('.bw-title');
  if (titleNode.dataset.status !== s.status) { titleNode.dataset.status = s.status; titleNode.innerHTML = title; }
  widget.querySelector('.bw-count').textContent = s.active ? `${Math.round(100 * batchFraction(s))}%` : '';
  let sub;
  if (s.status === 'running') sub = `${batchLine(s)} · ${levelName}`;
  else if (s.status === 'stopping') sub = 'Closing the engines…';
  else if (s.status === 'done') sub = `${s.completed} game${s.completed === 1 ? '' : 's'} analysed at ${levelName}.`;
  else if (s.status === 'stopped') {
    sub = s.reverted ? `${s.reverted} finished game${s.reverted === 1 ? ' was' : 's were'} reverted.`
      : `${s.completed} game${s.completed === 1 ? '' : 's'} analysed at ${levelName} ${s.completed === 1 ? 'was' : 'were'} kept.`;
  } else sub = s.error || '';
  widget.querySelector('.bw-sub').textContent = sub;
  widget.querySelector('.progress').hidden = !s.active;
  widget.querySelector('.progress-fill').style.width = `${100 * batchFraction(s)}%`;
  widget.querySelector('.bw-stop').hidden = s.status !== 'running';
  widget.querySelector('.bw-effort').hidden = !s.active;
  widget.querySelector('.bw-close').hidden = s.active;
  widget.querySelector('.bw-stats').hidden = location.pathname === '/stats';
  widget.querySelector('select').value = settings.effort;
  widget.classList.toggle('finished', !s.active);
}
document.addEventListener('settingschange', () => { if (widget && !widget.hidden) paintWidget(); });
pollBatch();
