const registry = new Map();

const SHADES = ['#111111', '#ffffff', '#6b6b6b', '#d4d4d4', '#3d3d3d', '#a6a6a6'];
const PATTERNS = ['diagonal', 'dots', 'horizontal', 'cross', 'vertical', 'backdiagonal'];
const fillCache = new Map();

function drawPattern(g, kind, size, ink) {
  g.strokeStyle = ink;
  g.fillStyle = ink;
  g.lineWidth = 1.2;
  g.beginPath();
  if (kind === 'diagonal') { g.moveTo(0, size); g.lineTo(size, 0); g.moveTo(-1, 1); g.lineTo(1, -1); g.moveTo(size - 1, size + 1); g.lineTo(size + 1, size - 1); g.stroke(); }
  else if (kind === 'backdiagonal') { g.moveTo(0, 0); g.lineTo(size, size); g.moveTo(-1, size - 1); g.lineTo(1, size + 1); g.moveTo(size - 1, -1); g.lineTo(size + 1, 1); g.stroke(); }
  else if (kind === 'horizontal') { g.moveTo(0, size / 2); g.lineTo(size, size / 2); g.stroke(); }
  else if (kind === 'vertical') { g.moveTo(size / 2, 0); g.lineTo(size / 2, size); g.stroke(); }
  else if (kind === 'cross') { g.moveTo(0, size / 2); g.lineTo(size, size / 2); g.moveTo(size / 2, 0); g.lineTo(size / 2, size); g.stroke(); }
  else if (kind === 'dots') { g.arc(size / 2, size / 2, 1.4, 0, Math.PI * 2); g.fill(); }
}

function color(index) {
  const key = index % 12;
  if (fillCache.has(key)) return fillCache.get(key);
  const cycle = Math.floor(key / SHADES.length);
  const shade = SHADES[key % SHADES.length];
  let kind = 'solid';
  if (key >= SHADES.length) kind = PATTERNS[(key - SHADES.length) % PATTERNS.length];
  let fill = shade;
  if (kind !== 'solid' || cycle > 0) {
    const size = 8;
    const tile = document.createElement('canvas');
    tile.width = size;
    tile.height = size;
    const g = tile.getContext('2d');
    g.fillStyle = shade;
    g.fillRect(0, 0, size, size);
    const dark = shade === '#111111' || shade === '#3d3d3d' || shade === '#6b6b6b';
    drawPattern(g, kind, size, dark ? '#ffffff' : '#111111');
    fill = g.createPattern(tile, 'repeat') || shade;
  }
  fillCache.set(key, fill);
  return fill;
}

function theme(light) {
  return { text: '#111111', grid: light ? 'rgba(17, 17, 17, 0.14)' : 'rgba(17, 17, 17, 0.10)', border: '#111111' };
}

function baseOptions(light, title) {
  const t = theme(light);
  const options = {
    responsive: !light,
    maintainAspectRatio: false,
    animation: light ? false : { duration: 400 },
    plugins: {
      legend: { position: 'bottom', labels: { color: t.text, boxWidth: 14, padding: 14, font: { family: 'Helvetica Neue, Helvetica, Arial, sans-serif' } } },
      title: { display: Boolean(title), text: title || '', color: t.text, font: { size: 13, weight: '600' } }
    }
  };
  if (light) options.devicePixelRatio = 1;
  return options;
}

function pieConfig(labels, values, title, light) {
  const t = theme(light);
  const options = baseOptions(light, title);
  options.plugins.tooltip = {
    callbacks: {
      label(context) {
        const total = context.dataset.data.reduce((a, b) => a + b, 0);
        const pct = total ? ((context.parsed * 100) / total).toFixed(1) : '0.0';
        return ' ' + context.label + ': ' + context.parsed + ' (' + pct + '%)';
      }
    }
  };
  return {
    type: 'pie',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: labels.map((_, i) => color(i)),
        borderColor: t.border,
        borderWidth: 1.5
      }]
    },
    options
  };
}

function barsConfig(labels, series, title, light, stacked) {
  const t = theme(light);
  const options = baseOptions(light, title);
  options.scales = {
    x: { stacked: Boolean(stacked), ticks: { color: t.text }, grid: { color: t.grid } },
    y: { stacked: Boolean(stacked), beginAtZero: true, ticks: { color: t.text, precision: 0 }, grid: { color: t.grid } }
  };
  if (series.length <= 1) options.plugins.legend.display = false;
  return {
    type: 'bar',
    data: {
      labels,
      datasets: series.map((s, i) => ({
        label: s.nombre,
        data: s.valores,
        backgroundColor: color(i),
        borderColor: '#111111',
        borderWidth: 1,
        borderRadius: 0
      }))
    },
    options
  };
}

export function destroyChart(id) {
  const entry = registry.get(id);
  if (entry) {
    entry.chart.destroy();
    registry.delete(id);
  }
  const canvas = document.getElementById(id);
  if (canvas && typeof Chart !== 'undefined') {
    const orphan = Chart.getChart(canvas);
    if (orphan) orphan.destroy();
  }
}

function mount(id, build) {
  destroyChart(id);
  const canvas = document.getElementById(id);
  if (!canvas || typeof Chart === 'undefined') return null;
  const chart = new Chart(canvas, build(false));
  registry.set(id, { chart, build });
  return chart;
}

export function renderPie(id, labels, values, title) {
  return mount(id, (light) => pieConfig(labels, values, title, light));
}

export function renderBars(id, labels, series, title, stacked) {
  return mount(id, (light) => barsConfig(labels, series, title, light, stacked));
}

export function renderSimpleBar(id, labels, values, label, title) {
  return renderBars(id, labels, [{ nombre: label, valores: values }], title, false);
}

export function chartImage(id) {
  const entry = registry.get(id);
  if (!entry) return null;
  try {
    const canvas = document.createElement('canvas');
    canvas.width = 1000;
    canvas.height = 560;
    const config = entry.build(true);
    const context = canvas.getContext('2d');
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, canvas.width, canvas.height);
    const plugin = {
      id: 'fondoBlanco',
      beforeDraw(chart) {
        const ctx = chart.ctx;
        ctx.save();
        ctx.globalCompositeOperation = 'destination-over';
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, chart.width, chart.height);
        ctx.restore();
      }
    };
    config.plugins = [plugin];
    const temp = new Chart(canvas, config);
    const data = canvas.toDataURL('image/png');
    temp.destroy();
    return data;
  } catch (e) {
    const live = document.getElementById(id);
    return live ? live.toDataURL('image/png') : null;
  }
}

export function chartImages(ids) {
  return ids.map((id) => chartImage(id)).filter(Boolean);
}
