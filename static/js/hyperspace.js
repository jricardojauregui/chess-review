// "Hyperspace" hover effect for the Max cards (level and effort): small glowing
// pixels streak across the card from left to right, each with a short trail,
// like stars at warp speed. Drawn on a <canvas> placed behind the card's text.
// The card starts plain: the stream builds up after the pointer arrives and
// drains away when it leaves.

const RAMP_MS = 700;            // time for the stream to reach full density
const DENSITY = 0.9;            // particles per 1000 px² of card at full density
const SPEED = [140, 620];       // px per second
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

const effects = new WeakMap();  // card element -> its running effect

function colours(card) {
  const accent = getComputedStyle(card).getPropertyValue('--accent').trim() || '#79c398';
  // mostly the accent green, with a few near-white and warm pixels for sparkle
  return [accent, accent, accent, '#eafff3', '#ffffff', '#ffd866'];
}

function start(card) {
  if (reduceMotion.matches || effects.has(card)) { const fx = effects.get(card); if (fx) fx.hover = true; return; }
  const canvas = document.createElement('canvas');
  canvas.className = 'hyperspace';
  canvas.setAttribute('aria-hidden', 'true');
  card.prepend(canvas);
  const ctx = canvas.getContext('2d');
  const palette = colours(card);
  const fx = { hover: true, particles: [], since: performance.now(), last: performance.now() };
  effects.set(card, fx);
  let width = 0, height = 0, carry = 0;

  const resize = () => {
    const ratio = window.devicePixelRatio || 1;
    width = card.clientWidth; height = card.clientHeight;
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  };
  resize();

  const spawn = () => {
    const depth = Math.random();                       // 0 = far (slow, dim, small), 1 = near
    const size = depth > 0.82 ? 3 : depth > 0.4 ? 2 : 1;
    fx.particles.push({
      x: -8, y: Math.round(Math.random() * height),
      speed: SPEED[0] + depth * depth * (SPEED[1] - SPEED[0]),
      size, alpha: 0.35 + depth * 0.65, twinkle: Math.random() * Math.PI * 2,
      colour: palette[Math.floor(Math.random() * palette.length)],
    });
  };

  const frame = now => {
    const dt = Math.min(0.05, (now - fx.last) / 1000);
    fx.last = now;
    if (card.clientWidth !== width || card.clientHeight !== height) resize();
    if (fx.hover) {
      // density grows from zero, so the first frames are an empty card
      const ramp = Math.min(1, (now - fx.since) / RAMP_MS);
      const target = (width * height / 1000) * DENSITY * ramp;
      // spawn at the rate that keeps `target` particles in flight
      carry += dt * target * ((SPEED[0] + SPEED[1]) / 2) / (width + 16);
      while (carry >= 1) { spawn(); carry -= 1; }
    }
    ctx.clearRect(0, 0, width, height);
    for (const p of fx.particles) {
      p.x += p.speed * dt;
      p.twinkle += dt * 9;
      const alpha = p.alpha * (0.7 + 0.3 * Math.sin(p.twinkle));
      const trail = p.speed * 0.07;                     // faster pixels leave longer streaks
      ctx.fillStyle = p.colour;
      ctx.globalAlpha = alpha * 0.22;
      ctx.fillRect(Math.round(p.x - trail), p.y, Math.round(trail), p.size);
      ctx.globalAlpha = alpha * 0.5;
      ctx.fillRect(Math.round(p.x - trail * 0.35), p.y, Math.round(trail * 0.35), p.size);
      ctx.globalAlpha = alpha;                          // the bright pixel at the head
      ctx.shadowColor = p.colour; ctx.shadowBlur = p.size * 3;
      ctx.fillRect(Math.round(p.x), p.y, p.size, p.size);
      ctx.shadowBlur = 0;
    }
    ctx.globalAlpha = 1;
    fx.particles = fx.particles.filter(p => p.x - p.speed * 0.07 < width);
    if (!fx.hover && !fx.particles.length) { canvas.remove(); effects.delete(card); return; }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

function stop(card) {
  const fx = effects.get(card);
  if (fx) fx.hover = false;                             // the pixels in flight finish their run
}

/** Run the effect on every `selector` card inside `root` while it is hovered or focused. */
export function attachHyperspace(root, selector = '.preset.max') {
  const cardOf = e => (e.target.closest ? e.target.closest(selector) : null);
  root.addEventListener('mouseover', e => {
    const card = cardOf(e);
    if (!card || card.contains(e.relatedTarget)) return;
    const fx = effects.get(card);
    if (fx) { fx.hover = true; fx.since = performance.now(); } else start(card);
  });
  root.addEventListener('mouseout', e => {
    const card = cardOf(e);
    if (card && !card.contains(e.relatedTarget)) stop(card);
  });
  root.addEventListener('focusin', e => { const card = cardOf(e); if (card) start(card); });
  root.addEventListener('focusout', e => { const card = cardOf(e); if (card && !card.matches(':hover')) stop(card); });
}
