// Evaluation chart (Chart.js): white's win% as an area, white on the bottom
// half up to the line, black above it. Dots mark the notable moves.
import { CLS, NOTABLE } from './common.js';

const WHITE_AREA = '#f4f1ea';
const LINE = '#8f887b';
const CURSOR = '#79c398';

/**
 * @param canvas   <canvas> element
 * @param review   review payload (start + moves)
 * @param options  { onSelect(ply), compact }
 * @returns { setCursor(ply), destroy() }
 */
export function createEvalChart(canvas, review, { onSelect, compact = false } = {}) {
  const moves = review.moves;
  const wins = [review.start.win_white, ...moves.map(m => m.win_white)];
  const clsAt = i => (i > 0 ? moves[i - 1].cls : null);
  const notable = i => NOTABLE.has(clsAt(i));
  let cursor = null;

  // Draws the 50% line, the current-move cursor and the hover crosshair.
  const overlay = {
    id: 'overlay',
    afterDatasetsDraw(chart) {
      const { ctx, chartArea: area, scales } = chart;
      const mid = scales.y.getPixelForValue(50);
      ctx.save();
      ctx.strokeStyle = 'rgba(120,126,138,.9)';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(area.left, mid); ctx.lineTo(area.right, mid); ctx.stroke();
      const vertical = (index, color, width) => {
        const x = scales.x.getPixelForValue(index);
        ctx.strokeStyle = color; ctx.lineWidth = width;
        ctx.beginPath(); ctx.moveTo(x, area.top); ctx.lineTo(x, area.bottom); ctx.stroke();
      };
      const active = chart.getActiveElements()[0];
      if (active && !compact) vertical(active.index, 'rgba(121,195,152,.5)', 1);
      if (cursor !== null) vertical(cursor, CURSOR, 2);
      ctx.restore();
    },
  };

  const chart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: wins.map((_, i) => i),
      datasets: [{
        data: wins,
        borderColor: LINE,
        borderWidth: 2,
        tension: 0.25,
        fill: { target: 'origin', above: WHITE_AREA },
        pointRadius: wins.map((_, i) => (notable(i) ? (compact ? 3.5 : 4.5) : 0)),
        pointHoverRadius: wins.map((_, i) => (notable(i) ? 6 : 3)),
        pointHitRadius: 8,
        pointBackgroundColor: wins.map((_, i) => (notable(i) ? CLS[clsAt(i)].color : LINE)),
        pointBorderColor: '#24211c',
        pointBorderWidth: wins.map((_, i) => (notable(i) ? 2 : 0)),
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      layout: { padding: 0 },
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { display: false, type: 'linear', min: 0, max: Math.max(1, wins.length - 1) },
        y: { display: false, min: 0, max: 100 },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          enabled: true,
          displayColors: true,
          callbacks: {
            title(items) {
              const i = items[0].dataIndex;
              if (i === 0) return 'Start position';
              const m = moves[i - 1];
              return `${m.move_number}${m.color === 'w' ? '.' : '...'} ${m.san}`;
            },
            label(item) {
              const i = item.dataIndex;
              if (i === 0) return ` ${review.start.eval.text}`;
              const m = moves[i - 1];
              return ` ${CLS[m.cls].label}  ·  ${m.eval.text}`;
            },
            labelColor(item) {
              const c = item.dataIndex > 0 ? CLS[clsAt(item.dataIndex)].color : LINE;
              return { borderColor: c, backgroundColor: c, borderRadius: 6 };
            },
          },
        },
      },
      onClick(event, _els, chartRef) {
        if (!onSelect) return;
        const value = chartRef.scales.x.getValueForPixel(event.x);
        onSelect(Math.max(0, Math.min(wins.length - 1, Math.round(value))));
      },
    },
    plugins: [overlay],
  });

  return {
    setCursor(ply) { cursor = ply; chart.draw(); },
    destroy() { chart.destroy(); },
  };
}
