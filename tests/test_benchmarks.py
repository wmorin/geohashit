import json
from pathlib import Path

from benchmarks.benchmark_cover import DEFAULT_CASES, benchmark_case


def test_benchmark_fixtures_are_valid_geojson():
    for name, path, precision in DEFAULT_CASES:
        with path.open() as fixture:
            payload = json.load(fixture)

        assert name
        assert precision > 0
        assert payload['type'] == 'Feature'
        assert payload['geometry']['type'] == 'Polygon'
        assert Path(path).exists()


def test_benchmark_case_reports_timing_fields():
    name, path, precision = DEFAULT_CASES[0]

    result = benchmark_case(name, path, precision, iterations=1, warmup=0)

    assert result['name'] == name
    assert result['precision'] == precision
    assert result['geohashes'] > 0
    assert result['min_seconds'] >= 0
    assert result['median_seconds'] >= 0
    assert result['mean_seconds'] >= 0
    assert result['max_seconds'] >= 0
