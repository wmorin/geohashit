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

The suite covers request validation, GeoJSON conversion, Nominatim request handling,
and Flask route behavior. Tests that touch Nominatim use fake sessions or monkeypatching
so the normal test suite does not call the live OpenStreetMap service.

## Benchmarks

The benchmark runner measures geohash coverage performance against checked-in
GeoJSON fixtures without calling Nominatim:

```bash
uv run python benchmarks/benchmark_cover.py
```
