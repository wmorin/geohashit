# Testing

Geohash'it uses `pytest` for API and geohashing regression tests. Dependencies
are managed with `uv` and locked in `uv.lock`.

## Setup

```bash
uv sync --dev
```

## Run

```bash
uv run pytest
```

Run lint and package checks with `uv run ruff check .` and `uv build`.

## Browser playground

Node 22+ is used for the browser engine and Playwright tests:

```bash
npm ci
npm test
npx playwright install chromium
npm run test:browser
```

The engine tests cover holes, compact prefixes, boundary touches, empty selections,
area conservation, invalid geometry, and resource limits. When `.venv/bin/python`
exists (created by `uv sync`), they also compare cell IDs directly with the Python
implementation. CI installs both runtimes so the comparison is mandatory there.

Playwright starts a local static server and runs desktop and mobile Chromium
checks for exports, modes, sharing, imports, drawing, and responsive layout.
Set `PLAYGROUND_URL` to an existing site URL to run the same checks against it.
Street tiles are optional and tests do not require them.

The geometry dependency is pinned and vendored for offline use. After updating
its version in `package.json`, run `npm run vendor:engine` and review both the
bundle and `docs/vendor/ENGINE-LICENSES.txt`. CI checks that the bundle reproduces.

The suite covers request validation, GeoJSON conversion, Nominatim request handling,
and Flask route behavior. Tests that touch Nominatim use fake sessions or monkeypatching
so the normal test suite does not call the live OpenStreetMap service.

## Benchmarks

The benchmark runner measures geohash coverage performance against checked-in
GeoJSON fixtures without calling Nominatim:

```bash
uv run python benchmarks/benchmark_cover.py
```
