import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { computeCoverage, geohashBounds, cellPolygon, normalizeGeoJSON, pointInShape, sphericalAreaKm2 } from '../docs/coverage-engine.js';

const polygon = (...rings) => ({ type: 'Polygon', coordinates: rings });
const rect = (w, s, e, n) => cellPolygon([w, s, e, n])[0];
const paris = polygon(rect(2.25, 48.82, 2.4, 48.91));
const hole = polygon(rect(2.25, 48.82, 2.4, 48.91), rect(2.29, 48.84, 2.36, 48.88));
const diagonal = polygon([[2.25, 48.82], [2.4, 48.82], [2.28, 48.91], [2.25, 48.82]]);
const separated = { type: 'MultiPolygon', coordinates: [paris.coordinates, [rect(-0.13, 51.5, -0.11, 51.52)]] };
function near(a, b, relative = 1e-10) { assert.ok(Math.abs(a - b) <= relative * Math.max(1, Math.abs(a), Math.abs(b)), `${a} != ${b}`); }

test('geohash bounds match standard known cells and retain 12-digit precision', () => {
  assert.deepEqual(geohashBounds('s'), [0, 0, 45, 45]);
  assert.deepEqual(geohashBounds('u4pruy'), [10.404052734375, 57.645263671875, 10.4150390625, 57.6507568359375]);
  const [w, s, e, n] = geohashBounds('u4pruydqqvj8');
  assert.ok(e > w && n > s);
  assert.throws(() => geohashBounds('a'), /Invalid geohash/);
});

test('compact coverage emits a fully contained parent and excludes all descendants', () => {
  const bounds = geohashBounds('u09tv');
  const result = computeCoverage({ geojson: polygon(rect(...bounds)), precision: 7, mode: 'inside' });
  assert.deepEqual(result.geohashes, ['u09tv']);
  near(result.metrics.missedAreaKm2, 0);
  near(result.metrics.spillAreaKm2, 0);
  assert.equal(result.geojson.features[0].properties.geohash, 'u09tv');
});

test('intersect includes boundary-only touches, center and inside do not', () => {
  const bounds = geohashBounds('s000');
  const shape = polygon(rect(...bounds));
  assert.deepEqual(computeCoverage({ geojson: shape, precision: 4, mode: 'inside' }).geohashes, ['s000']);
  assert.deepEqual(computeCoverage({ geojson: shape, precision: 4, mode: 'center' }).geohashes, ['s000']);
  const intersect = computeCoverage({ geojson: shape, precision: 4, mode: 'intersect' });
  assert.equal(intersect.geohashes.length, 9);
  near(intersect.metrics.missedAreaKm2, 0);
  assert.ok(intersect.metrics.spillAreaKm2 > 0);
});

test('center excludes a center on a polygon boundary', () => {
  const [w, s, e, n] = geohashBounds('s000');
  const shape = polygon(rect(w, s, (w + e) / 2, n));
  assert.deepEqual(computeCoverage({ geojson: shape, precision: 4, mode: 'center' }).geohashes, []);
});

test('holes are preserved and mode area invariants hold', () => {
  const normalized = normalizeGeoJSON(hole);
  assert.equal(normalized.coordinates[0].length, 2);
  assert.equal(pointInShape([2.32, 48.86], normalized.coordinates), false);
  const results = Object.fromEntries(['center', 'inside', 'intersect'].map(mode => [mode, computeCoverage({ geojson: hole, precision: 6, mode })]));
  near(results.inside.metrics.spillAreaKm2, 0);
  near(results.intersect.metrics.missedAreaKm2, 0);
  assert.ok(results.center.metrics.missedAreaKm2 > 0);
  assert.ok(results.center.metrics.spillAreaKm2 > 0);
  assert.ok(results.inside.metrics.coveredAreaKm2 <= results.center.metrics.coveredAreaKm2);
  assert.ok(results.center.metrics.coveredAreaKm2 <= results.intersect.metrics.coveredAreaKm2);
  for (const { metrics, geojson, geohashes } of Object.values(results)) {
    near(metrics.shapeAreaKm2, metrics.coveredAreaKm2 - metrics.spillAreaKm2 + metrics.missedAreaKm2);
    assert.equal(metrics.cellCount, geojson.features.length);
    assert.equal(metrics.cellCount, geohashes.length);
    assert.equal(metrics.exportBytes, Buffer.byteLength(JSON.stringify(geojson)));
    for (let i = 0; i < geohashes.length; i++) {
      assert.deepEqual(geojson.features[i].geometry.coordinates, cellPolygon(geohashBounds(geohashes[i])));
      assert.ok(!geohashes.some((hash, j) => i !== j && hash.startsWith(geohashes[i])));
    }
  }
});

test('spherical area matches an analytic rectangle and is additive along clipped diagonal edges', () => {
  const radius = 6371.0088, radians = Math.PI / 180;
  const area = sphericalAreaKm2([cellPolygon([2, 48, 3, 49])]);
  near(area, radius ** 2 * radians * (Math.sin(49 * radians) - Math.sin(48 * radians)));
  const whole = polygon([[0, 0], [20, 0], [0, 60], [0, 0]]);
  const split = [[[0, 0], [10, 0], [10, 30], [0, 60], [0, 0]], [[10, 0], [20, 0], [10, 30], [10, 0]]];
  near(sphericalAreaKm2(whole.coordinates ? [whole.coordinates] : []), sphericalAreaKm2(split.map(ring => [ring])));
  const highPrecision = sphericalAreaKm2([cellPolygon(geohashBounds('u4pruydqqvj8'))]);
  assert.ok(highPrecision > 0);
});

test('FeatureCollection union prevents double-counting and supports disjoint polygons', () => {
  const repeated = { type: 'FeatureCollection', features: [paris, paris].map(geometry => ({ type: 'Feature', properties: {}, geometry })) };
  const a = computeCoverage({ geojson: repeated, precision: 6, mode: 'center' });
  const b = computeCoverage({ geojson: paris, precision: 6, mode: 'center' });
  assert.deepEqual(a.geohashes, b.geohashes);
  near(a.metrics.shapeAreaKm2, b.metrics.shapeAreaKm2);
  const disjoint = computeCoverage({ geojson: separated, precision: 6, mode: 'intersect' });
  assert.equal(disjoint.shape.coordinates.length, 2);
  near(disjoint.metrics.missedAreaKm2, 0);
});

test('empty selections retain meaningful missed area with valid empty GeoJSON', () => {
  const result = computeCoverage({ geojson: polygon(rect(0.01, 0.01, 0.02, 0.02)), precision: 2, mode: 'center' });
  assert.deepEqual(result.geohashes, []);
  assert.deepEqual(result.geojson, { type: 'FeatureCollection', features: [] });
  assert.equal(result.metrics.coveredAreaKm2, 0);
  near(result.metrics.shapeAreaKm2, result.metrics.missedAreaKm2);
});

test('invalid types, coordinates, topology and antimeridian crossings are rejected', () => {
  const bad = [
    [null, /GeoJSON/],
    ['{broken', /valid GeoJSON/],
    [{ type: 'Point', coordinates: [0, 0] }, /Only Polygon/],
    [polygon([[0, 0], [1, 0], [1, 1], [0, 1]]), /closed/],
    [polygon([[0, 0], [Infinity, 0], [1, 1], [0, 0]]), /finite WGS84/],
    [polygon(rect(0, 0, 181, 1)), /WGS84/],
    [polygon(rect(179, 0, -179, 1)), /Antimeridian/],
    [polygon([[0, 0], [1, 1], [0, 1], [1, 0], [0, 0]]), /cross or touch/],
    [polygon(rect(0, 0, 2, 2), rect(3, 3, 4, 4)), /strictly inside/],
    [polygon(rect(0, 0, 3, 3), rect(1, 1, 2, 2), rect(1.5, 1.5, 2.5, 2.5)), /overlap/],
    [polygon([[0, 0], [1, 0], [2, 0], [0, 0]]), /folded|nonzero/],
  ];
  for (const [shape, pattern] of bad) assert.throws(() => normalizeGeoJSON(shape), pattern);
  assert.throws(() => computeCoverage({ geojson: paris, precision: 0 }), /Precision/);
  assert.throws(() => computeCoverage({ geojson: paris, precision: 6, mode: 'bogus' }), /Mode/);
});

test('all workload budgets fail explicitly instead of returning partial output', () => {
  assert.throws(() => computeCoverage({ geojson: paris, precision: 6 }, { maxCells: 1 }), /exceeds.*cells/);
  assert.throws(() => computeCoverage({ geojson: paris, precision: 6 }, { maxVisited: 1 }), /traversal budget/);
  assert.throws(() => computeCoverage({ geojson: paris, precision: 6 }, { maxMs: -1 }), /too long/);
  assert.throws(() => computeCoverage({ geojson: paris, precision: 6 }, { maxVertices: 4 }), /positions/);
  assert.throws(() => computeCoverage({ geojson: paris, precision: 6 }, { maxValidationChecks: 0 }), /topology is too complex/);
});

test('overlapping features cannot expand normalized geometry beyond the display budget', () => {
  // 1,000 bounded input positions would otherwise produce almost 50,000
  // positions after union, then synchronously freeze the main-thread renderer.
  const coordinates = [];
  for (let i = 0; i < 100; i++) {
    coordinates.push(cellPolygon([0, i / 10, 10, i / 10 + 0.04]));
    coordinates.push(cellPolygon([i / 10, 0, i / 10 + 0.04, 10]));
  }
  assert.throws(() => normalizeGeoJSON({ type: 'MultiPolygon', coordinates }), /Merged polygon exceeds.*positions/);
});

test('malformed nested geometry and excessive feature counts fail before recursive expansion', () => {
  let nested = paris;
  for (let i = 0; i < 10000; i++) nested = { type: 'Feature', geometry: nested };
  assert.throws(() => normalizeGeoJSON(nested), /nested collections/);
  const nestedCollection = { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: paris }] } }] };
  assert.throws(() => normalizeGeoJSON(nestedCollection), /nested collections/);
  const features = Array.from({ length: 3001 }, () => ({ type: 'Feature', geometry: paris }));
  assert.throws(() => normalizeGeoJSON({ type: 'FeatureCollection', features }), /too many features/);
  assert.throws(() => normalizeGeoJSON({ type: 'MultiPolygon', coordinates: Array(751).fill(paris.coordinates) }), /too many polygons/);
});

test('worker correlates successful and failing replies by request ID', async () => {
  const replies = [];
  globalThis.self = { postMessage: reply => replies.push(reply) };
  try {
    await import('../docs/coverage-worker.js');
    self.onmessage({ data: { id: 17, geojson: paris, precision: 5, mode: 'center' } });
    self.onmessage({ data: { id: 18, geojson: { type: 'Point', coordinates: [0, 0] }, precision: 5 } });
    self.onmessage({ data: { id: 19, type: 'normalize', geojson: hole } });
    self.onmessage({ data: { id: 20, type: 'normalize', geojson: { type: 'Feature', geometry: { type: 'FeatureCollection', features: [] } } } });
    assert.equal(replies[0].id, 17);
    assert.ok(replies[0].result.metrics.cellCount > 0);
    assert.equal(replies[1].id, 18);
    assert.match(replies[1].error, /Only Polygon/);
    assert.equal(replies[2].id, 19);
    assert.equal(replies[2].shape.type, 'MultiPolygon');
    assert.equal(replies[2].shape.coordinates[0].length, 2);
    assert.equal(replies[3].id, 20);
    assert.match(replies[3].error, /nested collections/);
  } finally { delete globalThis.self; }
});

const interpreter = new URL('../.venv/bin/python', import.meta.url);
test('browser IDs match Python/Shapely for holes, multipolygons, diagonal and cell-aligned polygons', { skip: !existsSync(interpreter) }, () => {
  const fixtures = [paris, hole, diagonal, separated, polygon(rect(...geohashBounds('s000'))), polygon(rect(...geohashBounds('u09tv')))];
  const cases = fixtures.flatMap(geojson => ['center', 'inside', 'intersect'].map(mode => ({ geojson, mode, precision: 6 })));
  const code = 'import json,sys; from geohashit.cover import cover_shape,geojson_to_shape; data=json.loads(sys.argv[1]); print(json.dumps([cover_shape(geojson_to_shape(x["geojson"]),x["precision"],x["mode"]) for x in data]))';
  const process = spawnSync(interpreter.pathname, ['-c', code, JSON.stringify(cases)], { cwd: new URL('..', import.meta.url), encoding: 'utf8', timeout: 20000 });
  assert.equal(process.status, 0, process.stderr);
  const expected = JSON.parse(process.stdout);
  for (let i = 0; i < cases.length; i++) assert.deepEqual(computeCoverage(cases[i]).geohashes, expected[i], `fixture ${i}, ${cases[i].mode}`);
});
