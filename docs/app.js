const $ = (id) => document.getElementById(id);
const presets = {
  paris: { name: 'Paris', file: 'paris.geojson', center: '48.86° N, 2.35° E', note: 'A simplified city boundary from the project’s benchmark fixtures.', precision: 6 },
  france: { name: 'Mainland France', file: 'france.geojson', center: '46.60° N, 1.72° E', note: 'A simplified mainland boundary from the project’s benchmark fixtures.', precision: 4 },
  delivery: { name: 'Delivery zone', file: 'delivery.geojson', center: '48.86° N, 2.35° E', note: 'A synthetic delivery zone with an exclusion area. Notice how cells respect the hole.', precision: 6 },
};
const explanations = {
  center: 'A balanced approximation. Some small gaps and spill beyond the boundary are expected.',
  inside: 'A conservative fit. Cells stay within the shape, leaving gaps along the boundary.',
  intersect: 'A generous fit. No area is missed, but edge cells extend beyond the boundary.',
};
let shape = null;
let result = null;
let worker = null;
let workerTimeout;
let computeTimer;
let requestId = 0;
let shapeRevision = 0;
let codeLanguage = 'python';
let drawing = false;
let drawPoints = [];
let toastTimer;
let requestedHash = '';
let normalizationId = 0;
let importPending = false;
const normalizationTasks = new Map();
const map = L.map('map', { preferCanvas: true, zoomControl: true, attributionControl: true, minZoom: 1, maxZoom: 20, worldCopyJump: false }).setView([48.8566, 2.3522], 11);
map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener">Leaflet</a>');
map.createPane('cellPane');
map.getPane('cellPane').style.zIndex = '410';
map.createPane('shapePane');
map.getPane('shapePane').style.zIndex = '420';
let shapeLayer = L.geoJSON(null, { pane: 'shapePane', interactive: false, style: { color: '#ad7d32', weight: 2, opacity: .95, fillColor: '#d7b77b', fillOpacity: .07 } });
let cellsLayer = L.geoJSON(null, { pane: 'cellPane', interactive: false, style: { color: '#547856', weight: .8, opacity: .7, fillColor: '#6d965f', fillOpacity: .24 } });
const drawLayer = L.layerGroup().addTo(map);
let streetLayer = null;

function currentMode() { return document.querySelector('input[name="mode"]:checked').value; }
function message(text, error = false) { $('map-message').textContent = text; $('map-message').hidden = !text; $('map-message').classList.toggle('error', error); }
function toast(text) { clearTimeout(toastTimer); $('toast').textContent = text; $('toast').hidden = false; toastTimer = setTimeout(() => { $('toast').hidden = true; }, 3500); }
function cancelWorker() { clearTimeout(workerTimeout); if (worker) { worker.terminate(); worker = null; } }
function cancelNormalizations() { for (const task of normalizationTasks.values()) task.cancel(); }
function normalizeInWorker(geojson) {
  return new Promise((resolve, reject) => {
    const id = ++normalizationId;
    let validator;
    let timeout;
    const finish = (error, normalized) => {
      clearTimeout(timeout);
      validator?.terminate();
      normalizationTasks.delete(id);
      if (error) reject(error); else resolve(normalized);
    };
    try {
      validator = new Worker('coverage-worker.js', { type: 'module' });
      normalizationTasks.set(id, { cancel: () => finish(new Error('Shape loading cancelled.')) });
      validator.onmessage = ({ data }) => {
        if (data.id !== id) return;
        finish(data.error ? new Error(data.error) : null, data.shape);
      };
      validator.onerror = () => finish(new Error('Shape validation could not run. Reload the page or serve it over HTTP.'));
      timeout = setTimeout(() => finish(new Error('This shape took too long to validate. Simplify it before importing.')), 20000);
      validator.postMessage({ id, geojson, type: 'normalize' });
    } catch { finish(new Error('Shape validation needs a browser with JavaScript workers.')); }
  });
}
function clearResults() {
  result = null;
  cellsLayer.clearLayers();
  ['download-geojson', 'download-ids'].forEach((id) => { $(id).disabled = true; });
  ['metric-count', 'metric-size', 'metric-missed', 'metric-spill'].forEach((id) => { $(id).textContent = '—'; });
  $('metric-time').textContent = 'Waiting for coverage';
  $('metric-missed-percent').textContent = 'Inside shape, outside cells';
  $('metric-spill-percent').textContent = 'Outside shape, inside cells';
  $('metric-footnote').textContent = 'Area estimates use spherical geometry. Compare coverage rules to see the trade-off.';
}
function updateLayers() {
  if ($('show-shape').checked && !drawing && shape) shapeLayer.addTo(map); else map.removeLayer(shapeLayer);
  if ($('show-cells').checked && !drawing && result) cellsLayer.addTo(map); else map.removeLayer(cellsLayer);
}
function fitShape() { const bounds = shapeLayer.getBounds(); if (bounds.isValid()) map.fitBounds(bounds, { padding: [38, 38], maxZoom: 15, animate: false }); }
function number(value, maximumFractionDigits = 2) { return Number(value).toLocaleString('en-US', { maximumFractionDigits }); }
function area(value) { return `${number(value, value > 1000 ? 0 : value < 1 ? 3 : 2)} km²`; }
function bytes(value) { if (value < 1024) return `${number(value, 0)} B`; if (value < 1024 * 1024) return `${number(value / 1024, 1)} KB`; return `${number(value / (1024 * 1024), 2)} MB`; }
function renderResult(data) {
  result = data;
  cellsLayer.addData(data.geojson);
  const m = data.metrics;
  $('metric-count').textContent = number(m.cellCount, 0);
  $('metric-size').textContent = bytes(m.exportBytes);
  $('metric-missed').textContent = area(m.missedAreaKm2);
  $('metric-spill').textContent = area(m.spillAreaKm2);
  $('metric-time').textContent = `Computed in ${number(m.elapsedMs, 0)} ms`;
  $('metric-missed-percent').textContent = `${number(m.shapeAreaKm2 ? m.missedAreaKm2 / m.shapeAreaKm2 * 100 : 0, 2)}% of original area`;
  $('metric-spill-percent').textContent = `${number(m.shapeAreaKm2 ? m.spillAreaKm2 / m.shapeAreaKm2 * 100 : 0, 2)}% of original area`;
  $('metric-footnote').textContent = `Original shape: ${area(m.shapeAreaKm2)} · Covered by cells: ${area(m.coveredAreaKm2)}. Spherical area estimates; maximum precision ${$('precision').value}.`;
  ['download-geojson', 'download-ids'].forEach((id) => { $(id).disabled = false; });
  message(m.cellCount ? '' : 'No cells match this rule at this precision. Try a finer precision or Intersect.');
  updateLayers();
}
function compute() {
  cancelWorker();
  clearResults();
  if (!shape || drawing) return;
  message('Finding the right cells…');
  const id = ++requestId;
  try {
    worker = new Worker('coverage-worker.js', { type: 'module' });
    worker.onmessage = ({ data }) => {
      if (data.id !== id || id !== requestId) return;
      cancelWorker();
      if (data.error) { message(data.error, true); $('metric-time').textContent = 'Try a lower precision'; return; }
      try { renderResult(data.result); } catch { clearResults(); message('This coverage could not be displayed. Try a lower precision.', true); }
    };
    worker.onerror = () => { if (id !== requestId) return; cancelWorker(); clearResults(); message('Coverage could not run. Reload the page or serve it over HTTP.', true); };
    worker.postMessage({ id, geojson: shape, precision: Number($('precision').value), mode: currentMode() });
    workerTimeout = setTimeout(() => { if (id !== requestId) return; cancelWorker(); clearResults(); message('This shape took too long to cover. Try a lower precision or a simpler shape.', true); }, 20000);
  } catch { cancelWorker(); message('Coverage needs a browser with JavaScript workers. Serve this page over HTTP.', true); }
}
function updateHash() {
  const preset = $('preset').value;
  $('share-button').disabled = !presets[preset] || drawing;
  requestedHash = presets[preset] && !drawing ? `#preset=${preset}&precision=${$('precision').value}&mode=${currentMode()}` : '';
  if (location.hash !== requestedHash) history.replaceState(null, '', `${location.pathname}${location.search}${requestedHash}`);
}
function settingsChanged() {
  $('precision-value').value = $('precision').value;
  $('rule-explanation').textContent = explanations[currentMode()];
  cancelWorker();
  requestId += 1;
  clearResults();
  updateCode();
  updateHash();
  clearTimeout(computeTimer);
  if (shape && !drawing) { message('Updating coverage…'); computeTimer = setTimeout(compute, 180); }
}
function setShape(geojson, name, preset = 'custom') {
  const normalized = geojson;
  const nextLayer = L.geoJSON(normalized, { pane: 'shapePane', interactive: false, style: { color: '#ad7d32', weight: 2, opacity: .95, fillColor: '#d7b77b', fillOpacity: .07 } });
  if (!nextLayer.getBounds().isValid()) throw new Error('This shape has no usable polygon coordinates.');
  map.removeLayer(shapeLayer);
  shapeLayer = nextLayer;
  shape = normalized;
  $('preset').value = preset;
  $('map-title').textContent = name;
  $('map-subtitle').textContent = presets[preset]?.center || 'Your own geometry';
  $('shape-note').textContent = presets[preset]?.note || 'Your custom shape. Geometry is processed locally and is never included in shared links.';
  $('download-input').disabled = false;
  $('share-button').disabled = !presets[preset];
  updateLayers();
  fitShape();
  settingsChanged();
}
async function loadPreset(preset, changePrecision = true) {
  if (!presets[preset]) return;
  const revision = ++shapeRevision;
  cancelNormalizations();
  stopDrawing();
  cancelWorker();
  requestId += 1;
  clearTimeout(computeTimer);
  clearResults();
  shape = null;
  shapeLayer.clearLayers();
  $('download-input').disabled = true;
  $('copy-code').disabled = true;
  $('share-button').disabled = true;
  updateCode();
  message('Loading shape…');
  if (changePrecision) $('precision').value = presets[preset].precision;
  try {
    const response = await fetch(`examples/${presets[preset].file}`);
    if (!response.ok) throw new Error('Could not load this example. Try reloading the page.');
    const geojson = await response.json();
    if (revision !== shapeRevision) return;
    const normalized = await normalizeInWorker(geojson);
    if (revision !== shapeRevision) return;
    setShape(normalized, presets[preset].name, preset);
  } catch (error) { if (revision === shapeRevision) { message(error.message, true); updateCode(); } }
}
function updateCode() {
  const precision = Number($('precision').value);
  const mode = currentMode();
  $('copy-code').disabled = !shape;
  if (!shape) { $('code-content').textContent = '# Select a shape to generate an example.'; return; }
  $('code-content').textContent = codeLanguage === 'python'
    ? `import json\nfrom geohashit.cover import geojson_to_geohashes\n\nwith open("shape.geojson") as source:\n    shape = json.load(source)\n\ncells = geojson_to_geohashes(shape, precision=${precision}, mode="${mode}")\nprint(cells)`
    : `# Save the selected input as shape.geojson, then run your local API.\ncurl -X POST \\\n  "http://127.0.0.1:5000/geohashes/geojson?precision=${precision}&mode=${mode}" \\\n  -H "Content-Type: application/json" \\\n  --data-binary @shape.geojson`;
}
function selectCode(language) {
  codeLanguage = language;
  ['python', 'curl'].forEach((name) => { $(`${name}-tab`).setAttribute('aria-selected', name === language); $(`${name}-tab`).tabIndex = name === language ? 0 : -1; });
  $('code-output').setAttribute('aria-labelledby', `${language}-tab`);
  updateCode();
}
function download(data, filename, type) {
  const blob = new Blob([data], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = filename;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function copy(text, success) {
  try { await navigator.clipboard.writeText(text); toast(success); }
  catch { const input = document.createElement('textarea'); input.value = text; input.style.position = 'fixed'; input.style.opacity = '0'; document.body.append(input); input.select(); const copied = document.execCommand('copy'); input.remove(); toast(copied ? success : 'Copy is unavailable. Select and copy the text manually.'); }
}
function renderDraw() {
  drawLayer.clearLayers();
  if (drawPoints.length > 1) L.polyline(drawPoints, { color: '#ad7d32', weight: 2, dashArray: '5 5', interactive: false }).addTo(drawLayer);
  if (drawPoints.length > 2) L.polygon(drawPoints, { color: '#ad7d32', weight: 1, dashArray: '5 5', fillOpacity: .1, interactive: false }).addTo(drawLayer);
  drawPoints.forEach((point) => L.circleMarker(point, { radius: 4, color: '#ad7d32', weight: 2, fillColor: 'white', fillOpacity: 1, interactive: false }).addTo(drawLayer));
  $('draw-finish').disabled = drawPoints.length < 3;
  $('draw-undo').disabled = !drawPoints.length;
  $('draw-help').textContent = `${drawPoints.length} points. Click to add, or pan with arrow keys and press Enter to add the map center. Finish with at least three points.`;
}
function stopDrawing() {
  drawing = false;
  drawPoints = [];
  drawLayer.clearLayers();
  $('draw-controls').hidden = true;
  document.body.classList.remove('drawing');
  map.doubleClickZoom.enable();
  $('draw-button').textContent = '◇ Draw a shape';
  updateLayers();
}
function addDrawPoint(latlng) {
  if (!drawing) return;
  if (drawPoints.length >= 500) { toast('Keep drawn shapes under 500 points.'); return; }
  if (latlng.lat < -85 || latlng.lat > 85 || latlng.lng < -180 || latlng.lng > 180) { toast('Draw between ±85° latitude and ±180° longitude.'); return; }
  drawPoints.push([latlng.lat, latlng.lng]);
  renderDraw();
}
$('preset').addEventListener('change', () => loadPreset($('preset').value));
$('precision').addEventListener('input', settingsChanged);
document.querySelectorAll('input[name="mode"]').forEach((input) => input.addEventListener('change', settingsChanged));
['show-shape', 'show-cells'].forEach((id) => $(id).addEventListener('change', updateLayers));
$('fit-button').addEventListener('click', fitShape);
$('show-basemap').addEventListener('change', () => {
  if ($('show-basemap').checked) {
    if (!streetLayer) {
      streetLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>' });
      streetLayer.on('tileerror', () => toast('Street tiles could not load. Geometry and coverage still work offline.'));
    }
    streetLayer.addTo(map);
  } else if (streetLayer) map.removeLayer(streetLayer);
});
$('download-geojson').addEventListener('click', () => { if (result) download(JSON.stringify(result.geojson), `geohashit-${$('preset').value}-p${$('precision').value}-${currentMode()}.geojson`, 'application/geo+json'); });
$('download-ids').addEventListener('click', () => { if (result) download(`${result.geohashes.join('\n')}${result.geohashes.length ? '\n' : ''}`, `geohashit-p${$('precision').value}-${currentMode()}.txt`, 'text/plain'); });
$('download-input').addEventListener('click', () => { if (shape) download(JSON.stringify(shape, null, 2), 'shape.geojson', 'application/geo+json'); });
$('share-button').addEventListener('click', () => { if (presets[$('preset').value]) copy(location.href, 'Preset link copied.'); });
$('copy-code').addEventListener('click', () => { if (shape) copy($('code-content').textContent, `${codeLanguage === 'python' ? 'Python' : 'curl'} example copied.`); });
['python', 'curl'].forEach((name) => $(`${name}-tab`).addEventListener('click', () => selectCode(name)));
document.querySelector('[role="tablist"]').addEventListener('keydown', (event) => { if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) { event.preventDefault(); const next = ['Home', 'ArrowLeft'].includes(event.key) ? 'python' : 'curl'; selectCode(next); $(`${next}-tab`).focus(); } });
$('import-button').addEventListener('click', () => { $('import-error').textContent = ''; $('import-dialog').showModal(); });
$('geojson-file').addEventListener('change', async () => {
  const file = $('geojson-file').files[0];
  if (!file) return;
  $('import-error').textContent = '';
  if (file.size > 1024 * 1024) { $('geojson-input').value = ''; $('import-error').textContent = 'This file is larger than 1 MB. Simplify it before importing.'; return; }
  try { const text = await file.text(); if ($('geojson-file').files[0] === file) $('geojson-input').value = text; } catch { $('geojson-input').value = ''; $('import-error').textContent = 'This file could not be read. Try pasting its GeoJSON.'; }
});
$('import-apply').addEventListener('click', async () => {
  const revision = ++shapeRevision;
  cancelNormalizations();
  $('import-apply').disabled = true;
  importPending = true;
  $('import-error').textContent = '';
  try {
    const text = $('geojson-input').value;
    if (new TextEncoder().encode(text).length > 1024 * 1024) throw new Error('This input is larger than 1 MB. Simplify it before importing.');
    let parsed;
    try { parsed = JSON.parse(text); } catch { throw new Error('This is not valid JSON. Paste a complete GeoJSON Polygon or MultiPolygon.'); }
    const normalized = await normalizeInWorker(parsed);
    if (revision !== shapeRevision) return;
    stopDrawing();
    setShape(normalized, 'Your shape');
    importPending = false;
    $('import-dialog').close();
    toast('Your shape is ready.');
  } catch (error) { if (revision === shapeRevision) $('import-error').textContent = error.message; }
  finally { importPending = false; $('import-apply').disabled = false; }
});
$('import-dialog').addEventListener('close', () => { if (importPending) { shapeRevision += 1; cancelNormalizations(); } });
$('draw-button').addEventListener('click', () => {
  if (drawing) return;
  cancelWorker(); clearTimeout(computeTimer); requestId += 1; shapeRevision += 1;
  cancelNormalizations();
  drawing = true; drawPoints = []; clearResults();
  $('draw-controls').hidden = false;
  document.body.classList.add('drawing');
  map.doubleClickZoom.disable();
  $('draw-button').textContent = '◇ Drawing…';
  $('share-button').disabled = true;
  updateLayers(); renderDraw(); message('Click the map to draw your boundary.');
  $('map').focus();
});
map.on('click', ({ latlng }) => addDrawPoint(latlng));
$('map').addEventListener('keydown', (event) => { if (drawing && event.key === 'Enter') { event.preventDefault(); addDrawPoint(map.getCenter()); } if (drawing && event.key === 'Escape') $('draw-cancel').click(); });
$('draw-undo').addEventListener('click', () => { drawPoints.pop(); renderDraw(); });
$('draw-cancel').addEventListener('click', () => { shapeRevision += 1; cancelNormalizations(); stopDrawing(); updateHash(); compute(); });
$('draw-finish').addEventListener('click', async () => {
  if (drawPoints.length < 3) return;
  const revision = ++shapeRevision;
  cancelNormalizations();
  $('draw-finish').disabled = true;
  const points = drawPoints.map(([lat, lng]) => [lng, lat]);
  points.push([...points[0]]);
  try { const next = await normalizeInWorker({ type: 'Polygon', coordinates: [points] }); if (revision !== shapeRevision) return; stopDrawing(); setShape(next, 'Drawn shape'); toast('Your drawn shape is ready.'); }
  catch (error) { if (revision === shapeRevision) { message(error.message, true); renderDraw(); } }
});
function readHash() {
  const params = new URLSearchParams(location.hash.slice(1));
  const preset = presets[params.get('preset')] ? params.get('preset') : 'paris';
  const precision = params.get('precision');
  $('precision').value = /^[1-8]$/.test(precision || '') ? precision : presets[preset].precision;
  const mode = Object.hasOwn(explanations, params.get('mode')) ? params.get('mode') : 'center';
  document.querySelector(`input[name="mode"][value="${mode}"]`).checked = true;
  $('precision-value').value = $('precision').value;
  $('rule-explanation').textContent = explanations[mode];
  loadPreset(preset, false);
}
window.addEventListener('hashchange', () => { if (location.hash !== requestedHash) readHash(); });
window.addEventListener('pagehide', () => { cancelWorker(); cancelNormalizations(); });
new ResizeObserver(() => { map.invalidateSize({ animate: false }); if (shape && !drawing) fitShape(); }).observe($('map'));
readHash();
