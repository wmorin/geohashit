import { computeCoverage, normalizeGeoJSON } from './coverage-engine.js';

self.onmessage = ({ data }) => {
  const { id, geojson, precision, mode, type } = data ?? {};
  try {
    if (type === 'normalize') {
      self.postMessage({ id, shape: normalizeGeoJSON(geojson) });
      return;
    }
    const result = computeCoverage({ geojson, precision, mode });
    self.postMessage({ id, result });
  } catch (error) {
    self.postMessage({ id, error: error instanceof Error ? error.message : 'Coverage failed. Check the polygon and try a lower precision.' });
  }
};
