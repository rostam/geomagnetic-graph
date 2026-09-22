const $ = s => document.querySelector(s);
const NS = 'http://www.w3.org/2000/svg';
const el = (t, a = {}, k = []) => {
  const n = document.createElementNS(NS, t);
  for (const [x, v] of Object.entries(a)) if (v != null) n.setAttribute(x, v);
  for (const c of [].concat(k)) n.append(c);
  return n;
};

const state = { i: 0, thr: 0.6, metric: 'mean_r', playing: null };
let net, land, corr, nPairs;

const METRIC_LABEL = {
  mean_r: 'mean correlation', density: 'edge density', modularity: 'modularity',
  alg_conn: 'algebraic connectivity', amplitude: 'largest field swing (nT)',
};

async function boot() {
  const [n, l, b64] = await Promise.all([
    fetch('data/network.json').then(r => r.json()),
    fetch('data/land.json').then(r => r.json()),
    fetch('data/corr.b64').then(r => r.text()),
  ]);
  net = n; land = l;
  nPairs = net.pairs.length;

  // the correlation matrices arrive as one packed int8 block: r * 100, -128 = no data
  const bin = atob(b64.trim());
  corr = new Int8Array(bin.length);
  for (let i = 0; i < bin.length; i++) corr[i] = (bin.charCodeAt(i) << 24) >> 24;

  // open on the largest storm in the record
  const big = net.windows.findIndex(w => w.t === '2015-03-17');
  state.i = big >= 0 ? big : 0;

  $('#stormList').innerHTML = net.storms.map(s =>
    `<button data-t="${s.t}"><span class="d">${s.t}</span><span class="dst">${s.dst} nT</span></button>`).join('');
  $('#stormList').onclick = e => {
    const b = e.target.closest('button'); if (!b) return;
    const i = net.windows.findIndex(w => w.t === b.dataset.t);
    if (i >= 0) { state.i = i; stop(); render(); }
  };

  $('#thr').oninput = e => { state.thr = +e.target.value; $('#thrVal').textContent = state.thr.toFixed(2); render(); };
  $('#metric').onchange = e => { state.metric = e.target.value; render(); };
  $('#showStorms').onchange = render;
  $('#date').onchange = e => {
    const i = net.windows.findIndex(w => w.t === e.target.value);
    if (i >= 0) { state.i = i; stop(); render(); }
  };
  $('#play').onclick = () => state.playing ? stop() : play();

  const tl = $('#tl');
  const seek = e => {
    const r = tl.getBoundingClientRect();
    const f = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    state.i = Math.round(f * (net.windows.length - 1));
    render();
  };
  let down = false;
  tl.addEventListener('pointerdown', e => { down = true; stop(); tl.setPointerCapture(e.pointerId); seek(e); });
  tl.addEventListener('pointermove', e => { if (down) seek(e); });
  tl.addEventListener('pointerup', e => { down = false; try { tl.releasePointerCapture(e.pointerId); } catch {} });

  addEventListener('keydown', e => {
    if (e.key === 'ArrowRight') { state.i = Math.min(net.windows.length - 1, state.i + 1); stop(); render(); }
    if (e.key === 'ArrowLeft') { state.i = Math.max(0, state.i - 1); stop(); render(); }
  });
  addEventListener('resize', render);
  render();
}

function play() {
  $('#play').textContent = 'Stop';
  state.playing = setInterval(() => {
    state.i = (state.i + 1) % net.windows.length;
    render();
  }, 60);
}
function stop() {
  if (state.playing) clearInterval(state.playing);
  state.playing = null;
  $('#play').textContent = 'Play the year';
}

const rAt = (wi, p) => {
  const v = corr[wi * nPairs + p];
  return v === -128 ? null : v / 100;
};

function render() {
  const w = net.windows[state.i];
  $('#date').value = w.t;
  drawMap(w);
  drawTimeline();
  const z = w.z ?? 0;
  $('#dayStats').innerHTML = [
    ['Date', w.t],
    ['Stations reporting', w.stations],
    ['Mean correlation', w.mean_r.toFixed(3)],
    ['Edges at this threshold', countEdges(state.i)],
    ['Modularity', w.modularity.toFixed(3)],
    ['Largest swing', w.amplitude.toFixed(0) + ' nT'],
    ['Synchronisation', (z >= 0 ? '+' : '') + z.toFixed(2) + 'σ'],
  ].map(([k, v], idx) => `<div><dt>${k}</dt><dd class="${idx === 6 && z > 2 ? 'hot' : ''}">${v}</dd></div>`).join('');

  $('#stormNote').innerHTML = w.storm
    ? `<div class="storm-note"><b>${w.storm.note}.</b> Dst minimum ${w.storm.dst} nT.
       The network ran ${w.storm.z >= 0 ? '+' : ''}${w.storm.z}σ above its usual synchronisation.</div>`
    : '';

  $('#readout').innerHTML =
    `<span>Showing <b>${w.t}</b></span>` +
    `<span><b>${net.windows.length.toLocaleString()}</b> days, 2010–2022</span>` +
    `<span>Timeline: ${METRIC_LABEL[state.metric]}</span>` +
    `<span>Drag the timeline, or use ← →</span>`;
}

function countEdges(wi) {
  let c = 0;
  for (let p = 0; p < nPairs; p++) {
    const v = rAt(wi, p);
    if (v != null && Math.abs(v) >= state.thr) c++;
  }
  return c;
}

function drawMap(w) {
  const svg = $('#map');
  const box = svg.getBoundingClientRect();
  const W = Math.max(320, box.width), H = Math.max(240, box.height);
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.replaceChildren();

  const sc = Math.min(W / 360, H / 165);
  const cx = W / 2, cy = H / 2;
  const pt = (lon, lat) => [cx + lon * sc, cy - lat * sc];

  const g = el('g');
  for (let lat = -60; lat <= 60; lat += 30) {
    const a = pt(-180, lat), b = pt(180, lat);
    g.append(el('path', { class: 'graticule', d: `M${a[0]},${a[1]}L${b[0]},${b[1]}` }));
  }
  for (const ring of land) {
    let d = '';
    for (let i = 0; i < ring.length; i++) {
      const [x, y] = pt(ring[i][0], ring[i][1]);
      d += (i ? 'L' : 'M') + x.toFixed(1) + ',' + y.toFixed(1);
    }
    g.append(el('path', { class: 'land', d: d + 'Z' }));
  }
  svg.append(g);

  const linked = new Set();
  const edges = el('g');
  for (let p = 0; p < nPairs; p++) {
    const v = rAt(state.i, p);
    if (v == null || Math.abs(v) < state.thr) continue;
    const [i, j] = net.pairs[p];
    linked.add(i); linked.add(j);
    const A = net.stations[i], B = net.stations[j];
    const [x1, y1] = pt(A.lon, A.lat), [x2, y2] = pt(B.lon, B.lat);
    const t = (Math.abs(v) - state.thr) / Math.max(0.01, 1 - state.thr);
    edges.append(el('path', {
      class: 'edge', d: `M${x1},${y1}L${x2},${y2}`,
      'stroke-width': (0.5 + t * 2).toFixed(2),
      'stroke-opacity': (0.12 + t * 0.5).toFixed(2),
    }));
  }
  svg.append(edges);

  const marks = el('g');
  net.stations.forEach((s, i) => {
    const [x, y] = pt(s.lon, s.lat);
    const gg = el('g', { class: 'stn' + (linked.has(i) ? '' : ' off') });
    gg.append(el('circle', { cx: x.toFixed(1), cy: y.toFixed(1), r: 3.6 }));
    gg.append(el('text', { x: (x + 6).toFixed(1), y: (y + 3).toFixed(1) }, s.code));
    gg.append(el('title', {}, `${s.code} — ${s.name}, ${s.country}`));
    marks.append(gg);
  });
  svg.append(marks);
}

function drawTimeline() {
  const cv = $('#tl');
  const cssW = cv.getBoundingClientRect().width;
  const dpr = Math.min(2, devicePixelRatio || 1);
  cv.width = Math.round(cssW * dpr);
  cv.height = Math.round(150 * dpr);
  const ctx = cv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const W = cssW, H = 150, pad = 20;

  const css = getComputedStyle(document.body);
  const cPlate = css.getPropertyValue('--plate').trim();
  const cRule = css.getPropertyValue('--rule-fine').trim();
  const cSig = css.getPropertyValue('--sig').trim();
  const cInk = css.getPropertyValue('--ink-faint').trim();
  const cWarn = css.getPropertyValue('--warn').trim();

  ctx.fillStyle = cPlate; ctx.fillRect(0, 0, W, H);

  const ws = net.windows;
  const vals = ws.map(w => w[state.metric] ?? 0);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const span = (hi - lo) || 1;
  const X = i => (i / (ws.length - 1)) * W;
  const Y = v => H - pad - ((v - lo) / span) * (H - pad - 12);

  // year gridlines
  ctx.strokeStyle = cRule; ctx.lineWidth = 1; ctx.font = '9px "IBM Plex Mono", monospace';
  ctx.fillStyle = cInk;
  let lastYear = null;
  ws.forEach((w, i) => {
    const y = w.t.slice(0, 4);
    if (y !== lastYear) {
      lastYear = y;
      const x = X(i);
      ctx.beginPath(); ctx.moveTo(x, 8); ctx.lineTo(x, H - pad); ctx.stroke();
      ctx.fillText(y, x + 3, H - pad + 12);
    }
  });

  ctx.strokeStyle = cSig; ctx.lineWidth = 1;
  ctx.beginPath();
  ws.forEach((w, i) => {
    const x = X(i), y = Y(vals[i]);
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.stroke();

  if ($('#showStorms').checked) {
    ctx.fillStyle = cWarn;
    for (const s of net.storms) {
      const i = ws.findIndex(w => w.t === s.t);
      if (i < 0) continue;
      ctx.beginPath(); ctx.arc(X(i), Y(vals[i]), 2.6, 0, Math.PI * 2); ctx.fill();
    }
  }

  const x = X(state.i);
  ctx.strokeStyle = cWarn; ctx.lineWidth = 1.2;
  ctx.beginPath(); ctx.moveTo(x, 4); ctx.lineTo(x, H - pad); ctx.stroke();
  ctx.fillStyle = cWarn;
  ctx.fillText(`${ws[state.i].t}  ${(vals[state.i]).toFixed(3)}`, Math.min(W - 120, x + 4), 12);
}

boot().catch(e => {
  $('#readout').innerHTML = `<span>Could not load the data: ${e.message}. Serve this folder over HTTP.</span>`;
});
