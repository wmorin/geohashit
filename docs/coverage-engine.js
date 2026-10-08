import { difference, intersection, union } from './vendor/polyclip.js';

export const GEOHASH_CHARS = '0123456789bcdefghjkmnpqrstuvwxyz';
export const LIMITS = Object.freeze({ maxCells: 20000, maxVisited: 120000, maxVertices: 3000, maxValidationChecks: 5000000, maxMs: 15000 });
const EARTH_RADIUS_KM = 6371.0088;
const RAD = Math.PI / 180;

function budget(options = {}) {
  const limits = { ...LIMITS, ...options };
  const started = performance.now();
  let visits = 0;
  let checks = 0;
  return {
    limits, started,
    get visits() { return visits; },
    time() {
      if (performance.now() - started > limits.maxMs) throw new Error('Coverage took too long. Lower precision or simplify the polygon.');
    },
    visit() {
      if (++visits > limits.maxVisited) throw new Error('Coverage exceeds the traversal budget. Lower precision or simplify the polygon.');
      this.time();
    },
    check() {
      if (++checks > limits.maxValidationChecks) throw new Error('Polygon topology is too complex. Simplify the polygon before uploading.');
      if (checks % 1024 === 0) this.time();
    },
  };
}

export function geohashBounds(hash) {
  let west = -180, east = 180, south = -90, north = 90;
  let longitude = true;
  for (const character of hash) {
    const value = GEOHASH_CHARS.indexOf(character);
    if (value < 0) throw new Error('Invalid geohash.');
    for (let mask = 16; mask; mask >>= 1) {
      if (longitude) {
        const mid = (west + east) / 2;
        if (value & mask) west = mid; else east = mid;
      } else {
        const mid = (south + north) / 2;
        if (value & mask) south = mid; else north = mid;
      }
      longitude = !longitude;
    }
  }
  return [west, south, east, north];
}

export function cellPolygon(bounds) {
  const [w, s, e, n] = bounds;
  return [[[w, s], [e, s], [e, n], [w, n], [w, s]]];
}

function cross(a, b, c) {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}
function onSegment(p, a, b) {
  return cross(a, b, p) === 0 && p[0] >= Math.min(a[0], b[0]) && p[0] <= Math.max(a[0], b[0]) && p[1] >= Math.min(a[1], b[1]) && p[1] <= Math.max(a[1], b[1]);
}
function segmentsIntersect(a, b, c, d) {
  if (Math.max(a[0], b[0]) < Math.min(c[0], d[0]) || Math.max(c[0], d[0]) < Math.min(a[0], b[0]) || Math.max(a[1], b[1]) < Math.min(c[1], d[1]) || Math.max(c[1], d[1]) < Math.min(a[1], b[1])) return false;
  const abC = cross(a, b, c), abD = cross(a, b, d), cdA = cross(c, d, a), cdB = cross(c, d, b);
  return ((abC > 0 && abD < 0 || abC < 0 && abD > 0) && (cdA > 0 && cdB < 0 || cdA < 0 && cdB > 0)) || onSegment(c, a, b) || onSegment(d, a, b) || onSegment(a, c, d) || onSegment(b, c, d);
}

// -1 outside, 0 on the boundary, 1 inside. Center mode excludes the boundary.
function inRing(point, ring) {
  let inside = false;
  for (let i = 0; i < ring.length - 1; i++) {
    const a = ring[i], b = ring[i + 1];
    if (onSegment(point, a, b)) return 0;
    if ((a[1] > point[1]) !== (b[1] > point[1]) && point[0] < (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
  }
  return inside ? 1 : -1;
}
export function pointInShape(point, polygons) {
  return polygons.some(polygon => inRing(point, polygon[0]) === 1 && polygon.slice(1).every(hole => inRing(point, hole) === -1));
}

function validateRing(ring, state) {
  if (!Array.isArray(ring) || ring.length < 4) throw new Error('Every polygon ring must contain at least four positions.');
  state.vertices += ring.length;
  if (state.vertices > state.work.limits.maxVertices) throw new Error(`Polygon exceeds ${state.work.limits.maxVertices.toLocaleString('en')} positions. Simplify it before uploading.`);
  const clean = ring.map(position => {
    if (!Array.isArray(position) || position.length < 2 || !Number.isFinite(position[0]) || !Number.isFinite(position[1])) throw new Error('Coordinates must be finite WGS84 longitude/latitude numbers.');
    const [lon, lat] = position;
    if (lon < -180 || lon > 180 || lat < -90 || lat > 90) throw new Error('Coordinates must use WGS84 longitude [-180, 180] and latitude [-90, 90].');
    return [lon, lat];
  });
  if (clean[0][0] !== clean.at(-1)[0] || clean[0][1] !== clean.at(-1)[1]) throw new Error('Polygon rings must be closed: the last position must equal the first.');
  for (let i = 0; i < clean.length - 1; i++) {
    if (Math.abs(clean[i][0] - clean[i + 1][0]) > 180) throw new Error('Antimeridian-crossing polygons are not supported. Split the shape at ±180° first.');
  }
  const deduped = clean.filter((p, i) => i === 0 || p[0] !== clean[i - 1][0] || p[1] !== clean[i - 1][1]);
  if (deduped.length < 4) throw new Error('Polygon rings must contain three distinct vertices.');
  let twiceArea = 0;
  for (let i = 0; i < deduped.length - 1; i++) {
    const a = deduped[i], b = deduped[i + 1];
    twiceArea += (a[0] - deduped[0][0]) * (b[1] - deduped[0][1]) - (b[0] - deduped[0][0]) * (a[1] - deduped[0][1]);
    for (let j = i + 2; j < deduped.length - 1; j++) {
      if (i === 0 && j === deduped.length - 2) continue;
      state.work.check();
      if (segmentsIntersect(a, b, deduped[j], deduped[j + 1])) throw new Error('Polygon rings must not cross or touch themselves. Repair the geometry first.');
    }
    const next = deduped[(i + 2) % (deduped.length - 1)];
    if (cross(a, b, next) === 0 && onSegment(next, a, b)) throw new Error('Polygon rings contain a folded or overlapping edge. Repair the geometry first.');
  }
  if (twiceArea === 0) throw new Error('Polygon rings must have a nonzero area.');
  return deduped;
}
function ringsTouch(a, b, work) {
  for (let i = 0; i < a.length - 1; i++) for (let j = 0; j < b.length - 1; j++) {
    work.check();
    if (segmentsIntersect(a[i], a[i + 1], b[j], b[j + 1])) return true;
  }
  return false;
}

export function normalizeGeoJSON(input, options = {}) {
  const work = options.work ?? budget(options);
  const state = { vertices: 0, work };
  let data = input;
  if (typeof data === 'string') {
    try { data = JSON.parse(data); } catch { throw new Error('Upload must contain valid GeoJSON JSON.'); }
  }
  const geometries = [];
  let entries = 0;
  function collect(value) {
    if (++entries > work.limits.maxVertices) throw new Error('GeoJSON contains too many features. Simplify it before uploading.');
    if (!value || typeof value !== 'object') throw new Error('Input must be a GeoJSON Polygon, MultiPolygon, Feature, or FeatureCollection.');
    if (value.type === 'FeatureCollection') {
      if (!Array.isArray(value.features) || !value.features.length) throw new Error('FeatureCollection must contain at least one polygon feature.');
      for (const feature of value.features) {
        if (feature?.type !== 'Feature') throw new Error('FeatureCollection entries must be GeoJSON Features.');
        collect(feature);
      }
    } else if (value.type === 'Feature') {
      if (!['Polygon', 'MultiPolygon'].includes(value.geometry?.type)) throw new Error('Every Feature must contain a Polygon or MultiPolygon geometry; nested collections are not supported.');
      collect(value.geometry);
    }
    else if (value.type === 'Polygon') geometries.push(value.coordinates);
    else if (value.type === 'MultiPolygon') {
      if (!Array.isArray(value.coordinates)) throw new Error('MultiPolygon coordinates must be an array.');
      if (value.coordinates.length > work.limits.maxVertices / 4) throw new Error('GeoJSON contains too many polygons. Simplify it before uploading.');
      for (const polygon of value.coordinates) geometries.push(polygon);
    } else throw new Error('Only Polygon and MultiPolygon geometries are supported.');
  }
  collect(data);
  if (!geometries.length) throw new Error('Input must contain at least one nonempty polygon.');
  const polygons = geometries.map(polygon => {
    if (!Array.isArray(polygon) || !polygon.length) throw new Error('Every Polygon needs a nonempty exterior ring.');
    const rings = polygon.map(ring => validateRing(ring, state));
    for (let i = 1; i < rings.length; i++) {
      if (inRing(rings[i][0], rings[0]) !== 1 || ringsTouch(rings[i], rings[0], work)) throw new Error('Polygon holes must lie strictly inside their exterior ring.');
      for (let j = 1; j < i; j++) {
        if (ringsTouch(rings[i], rings[j], work) || inRing(rings[i][0], rings[j]) !== -1 || inRing(rings[j][0], rings[i]) !== -1) throw new Error('Polygon holes must not overlap, nest, or touch.');
      }
    }
    return rings;
  });
  work.time();
  // Overlapping features are a union, never double-counted in metrics.
  const normalized = union(...polygons);
  work.time();
  if (!normalized.length) throw new Error('Input polygon has no area.');
  let normalizedVertices = 0;
  for (const polygon of normalized) for (const ring of polygon) {
    normalizedVertices += ring.length;
    if (normalizedVertices > work.limits.maxVertices) throw new Error(`Merged polygon exceeds ${work.limits.maxVertices.toLocaleString('en')} positions. Simplify overlapping features before uploading.`);
  }
  return { type: 'MultiPolygon', coordinates: normalized };
}

// Integrate sin(latitude) along straight longitude/latitude edges. The spherical
// Earth approximation is additive even when clipping subdivides diagonal edges.
// Radius follows Turf's mean Earth radius; this is not an ellipsoidal GIS survey.
function ringAreaKm2(ring) {
  let integral = 0;
  const originLon = ring[0][0];
  for (let i = 0; i < ring.length - 1; i++) {
    const a = ring[i], b = ring[i + 1];
    const phiA = a[1] * RAD, phiB = b[1] * RAD;
    const deltaPhi = phiB - phiA;
    // cos(a)-cos(b) via sine avoids cancellation for small latitude differences.
    const meanSin = Math.abs(deltaPhi) < 1e-10 ? Math.sin((phiA + phiB) / 2) : 2 * Math.sin((phiA + phiB) / 2) * Math.sin(deltaPhi / 2) / deltaPhi;
    // Integration by parts subtracts a constant latitude reference, reducing
    // cancellation for tiny cells far from the equator.
    const reference = Math.sin(ring[0][1] * RAD);
    integral += ((b[0] - originLon) - (a[0] - originLon)) * RAD * (meanSin - reference);
  }
  return Math.abs(integral) * EARTH_RADIUS_KM ** 2;
}
export function sphericalAreaKm2(polygons) {
  return polygons.reduce((sum, polygon) => sum + ringAreaKm2(polygon[0]) - polygon.slice(1).reduce((holes, ring) => holes + ringAreaKm2(ring), 0), 0);
}
function boundsOf(polygons) {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  for (const polygon of polygons) for (const [lon, lat] of polygon[0]) { w = Math.min(w, lon); s = Math.min(s, lat); e = Math.max(e, lon); n = Math.max(n, lat); }
  return [w, s, e, n];
}
function boundsIntersect(a, b) { return a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1]; }
function boundaryTouches(polygons, bounds) {
  const ring = cellPolygon(bounds)[0];
  for (const polygon of polygons) for (const boundary of polygon) for (let i = 0; i < boundary.length - 1; i++) {
    const a = boundary[i], b = boundary[i + 1];
    if (!boundsIntersect([Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])], bounds)) continue;
    if (a[0] >= bounds[0] && a[0] <= bounds[2] && a[1] >= bounds[1] && a[1] <= bounds[3]) return true;
    for (let j = 0; j < 4; j++) if (segmentsIntersect(a, b, ring[j], ring[j + 1])) return true;
  }
  return false;
}

export function computeCoverage({ geojson, precision = 6, mode = 'center' }, options = {}) {
  if (!Number.isInteger(precision) || precision < 1 || precision > 12) throw new Error('Precision must be an integer from 1 to 12.');
  if (!['center', 'inside', 'intersect'].includes(mode)) throw new Error('Mode must be center, inside, or intersect.');
  const work = budget(options);
  const shape = normalizeGeoJSON(geojson, { work });
  const polygons = shape.coordinates;
  const shapeBounds = boundsOf(polygons);
  const shapeAreaKm2 = sphericalAreaKm2(polygons);
  const geohashes = [], features = [];
  let coveredAreaKm2 = 0, overlapAreaKm2 = 0;
  function emit(hash, bounds, clipped, contained) {
    if (geohashes.length >= work.limits.maxCells) throw new Error(`Coverage exceeds ${work.limits.maxCells.toLocaleString('en')} cells. Lower precision or simplify the polygon.`);
    const coordinates = cellPolygon(bounds);
    const area = sphericalAreaKm2([coordinates]);
    coveredAreaKm2 += area;
    overlapAreaKm2 += contained ? area : sphericalAreaKm2(clipped);
    geohashes.push(hash);
    features.push({ type: 'Feature', properties: { geohash: hash }, geometry: { type: 'Polygon', coordinates } });
  }
  function descend(prefix, local) {
    for (const char of GEOHASH_CHARS) {
      work.visit();
      const hash = prefix + char;
      const bounds = geohashBounds(hash);
      if (!boundsIntersect(bounds, shapeBounds)) continue;
      const rectangle = cellPolygon(bounds);
      const clipped = local.length ? intersection(local, rectangle) : [];
      if (!clipped.length) {
        // Polygon boolean libraries omit line/point intersections. Intersect
        // mode includes those boundary touches, matching Shapely intersects.
        if (mode !== 'intersect' || !boundaryTouches(polygons, bounds)) continue;
        if (hash.length === precision) emit(hash, bounds, [], false);
        else descend(hash, []);
        continue;
      }
      const contained = difference(rectangle, clipped).length === 0;
      if (contained) { emit(hash, bounds, clipped, true); continue; }
      if (hash.length < precision) { descend(hash, clipped); continue; }
      if (mode === 'intersect' || mode === 'center' && pointInShape([(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2], clipped)) emit(hash, bounds, clipped, false);
    }
  }
  descend('', polygons);
  const collection = { type: 'FeatureCollection', features };
  work.time();
  const exportBytes = new TextEncoder().encode(JSON.stringify(collection)).length;
  return {
    geohashes,
    geojson: collection,
    shape,
    metrics: {
      cellCount: geohashes.length, coveredAreaKm2, shapeAreaKm2,
      missedAreaKm2: Math.max(0, shapeAreaKm2 - overlapAreaKm2),
      spillAreaKm2: Math.max(0, coveredAreaKm2 - overlapAreaKm2),
      elapsedMs: performance.now() - work.started, exportBytes,
      visitedCells: work.visits,
      areaModel: 'Approximate spherical area (mean Earth radius; straight longitude/latitude edges)',
    },
  };
}
