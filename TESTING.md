# Testing

Geohash'it uses `pytest` for API and geohashing regression tests.

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements.txt
```

## Run

```bash
.venv/bin/python -m pytest
```

The suite covers request validation, GeoJSON conversion, Nominatim request handling,
and Flask route behavior. Tests that touch Nominatim use fake sessions or monkeypatching
so the normal test suite does not call the live OpenStreetMap service.
