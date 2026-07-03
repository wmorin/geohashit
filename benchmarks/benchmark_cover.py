import argparse
import json
import statistics
import time
from pathlib import Path

from geohashit.cover import geojson_to_geohashes

FIXTURE_DIR = Path(__file__).parent / 'fixtures'
DEFAULT_CASES = (
    ('paris-city', FIXTURE_DIR / 'paris-city.geojson', 6),
    ('france-mainland', FIXTURE_DIR / 'france-mainland.geojson', 6),
)


def load_geojson(path):
    with path.open() as fixture:
        return json.load(fixture)


def benchmark_case(name, path, precision, iterations, warmup):
    payload = load_geojson(path)
    try:
        fixture = str(path.relative_to(Path.cwd()))
    except ValueError:
        fixture = str(path)

    for _ in range(warmup):
        geojson_to_geohashes(payload, precision)

    durations = []
    geohash_count = 0
    for _ in range(iterations):
        start = time.perf_counter()
        geohashes = geojson_to_geohashes(payload, precision)
        durations.append(time.perf_counter() - start)
        geohash_count = len(geohashes)

    return {
        'name': name,
        'fixture': fixture,
        'precision': precision,
        'iterations': iterations,
        'geohashes': geohash_count,
        'min_seconds': min(durations),
        'median_seconds': statistics.median(durations),
        'mean_seconds': statistics.mean(durations),
        'max_seconds': max(durations),
    }


def parse_case(value):
    try:
        name, fixture, precision = value.split(':', maxsplit=2)
        return name, Path(fixture), int(precision)
    except ValueError:
        raise argparse.ArgumentTypeError(
            'cases must use name:path:precision format'
        )


def format_results(results):
    rows = [
        (
            result['name'],
            str(result['precision']),
            str(result['geohashes']),
            '%.4f' % result['median_seconds'],
            '%.4f' % result['mean_seconds'],
            '%.4f' % result['max_seconds'],
        )
        for result in results
    ]
    headers = ('case', 'precision', 'geohashes', 'median_s', 'mean_s', 'max_s')
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]

    lines = [
        '  '.join(header.ljust(widths[index]) for index, header in enumerate(headers)),
        '  '.join('-' * width for width in widths),
    ]
    lines.extend(
        '  '.join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in rows
    )
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Benchmark geohash coverage on real-world polygon fixtures.'
    )
    parser.add_argument('--iterations', type=int, default=3)
    parser.add_argument('--warmup', type=int, default=1)
    parser.add_argument(
        '--case',
        action='append',
        type=parse_case,
        dest='cases',
        help='Additional case in name:path:precision format.',
    )
    parser.add_argument('--json', action='store_true', dest='json_output')
    args = parser.parse_args()

    if args.iterations < 1:
        raise SystemExit('--iterations must be at least 1')
    if args.warmup < 0:
        raise SystemExit('--warmup must be at least 0')

    cases = args.cases or DEFAULT_CASES
    results = [
        benchmark_case(name, path, precision, args.iterations, args.warmup)
        for name, path, precision in cases
    ]

    if args.json_output:
        print(json.dumps({'results': results}, indent=2))
    else:
        print(format_results(results))


if __name__ == '__main__':
    main()
