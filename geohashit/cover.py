import json

import pygeohash
import shapely
import shapely.errors
from shapely.geometry import MultiPolygon, Point, Polygon, box, mapping
from shapely.ops import unary_union

GEOHASH_CHARS = (
    '0', '1', '2', '3', '4', '5', '6', '7',
    '8', '9', 'b', 'c', 'd', 'e', 'f', 'g',
    'h', 'j', 'k', 'm', 'n', 'p', 'q', 'r',
    's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
)
MAX_GEOHASHES = 50_000
COVER_MODES = ('center', 'inside', 'intersect')


class GeohashBudgetError(ValueError):
    pass


class GeohashBudget:
    def __init__(self, maximum):
        self.maximum = maximum
        self.count = 0

    def add(self, count=1):
        self.count += count
        if self.count > self.maximum:
            raise GeohashBudgetError(
                'geohash coverage exceeds the maximum of %s cells' % self.maximum
            )


def geohash_bbox(geohash):
    bounds = pygeohash.get_bounding_box(geohash)
    return {
        'n': bounds.max_lat,
        's': bounds.min_lat,
        'e': bounds.max_lon,
        'w': bounds.min_lon,
    }


def decode_geohash(geohash):
    decoded = pygeohash.decode(geohash)
    return decoded.latitude, decoded.longitude


def emit_geohash(geohash, budget):
    if budget is not None:
        budget.add()
    yield geohash


def cover_inside(shape, cell, geohash, precision, level, budget):
    if shape.contains(cell):
        yield from emit_geohash(geohash, budget)
        return
    if level < precision and cell.intersects(shape):
        yield from iter_cover_shape(
            shape,
            precision,
            'inside',
            level + 1,
            geohash,
            budget,
        )
        return


def cover_center(shape, cell, geohash, precision, level, budget):
    if shape.contains(cell):
        yield from emit_geohash(geohash, budget)
        return
    if level < precision and cell.intersects(shape):
        yield from iter_cover_shape(
            cell.intersection(shape),
            precision,
            'center',
            level + 1,
            geohash,
            budget,
        )
        return
    if level == precision:
        lat, lon = decode_geohash(geohash)
        if shape.contains(Point(lon, lat)):
            yield from emit_geohash(geohash, budget)


def cover_intersect(shape, cell, geohash, precision, level, budget):
    if shape.contains(cell):
        yield from emit_geohash(geohash, budget)
        return
    if level < precision and cell.intersects(shape):
        yield from iter_cover_shape(
            shape,
            precision,
            'intersect',
            level + 1,
            geohash,
            budget,
        )
        return
    if level == precision and cell.intersects(shape):
        yield from emit_geohash(geohash, budget)


COVER_MODE_HANDLERS = {
    'center': cover_center,
    'inside': cover_inside,
    'intersect': cover_intersect,
}


def iter_cover_shape(shape, precision=12, mode='center', level=1, prefix='', budget=None):
    if mode not in COVER_MODE_HANDLERS:
        raise ValueError('mode must be one of: %s' % ', '.join(COVER_MODES))

    cover_cell = COVER_MODE_HANDLERS[mode]

    for char in GEOHASH_CHARS:
        geohash = prefix + char
        bounds = geohash_bbox(geohash)
        cell = box(bounds['w'], bounds['s'], bounds['e'], bounds['n'])
        yield from cover_cell(shape, cell, geohash, precision, level, budget)


def cover_shape(shape, precision=12, mode='center', level=1, prefix='', budget=None):
    return list(iter_cover_shape(shape, precision, mode, level, prefix, budget))


def geojson_to_shape(data):
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            raise ValueError('geojson must be valid JSON')

    try:
        if data['type'] == 'FeatureCollection':
            shapes = [
                shapely.geometry.shape(feature['geometry'])
                for feature in data['features']
            ]
            return unary_union(shapes)
        if data['type'] == 'Feature':
            return shapely.geometry.shape(data['geometry'])
        return shapely.geometry.shape(data)
    except (KeyError, TypeError):
        raise ValueError('geojson must be a GeoJSON geometry, Feature, or FeatureCollection')
    except shapely.errors.ShapelyError:
        raise ValueError('geojson contains invalid geometry')


def geojson_to_geohashes(data, precision, max_geohashes=MAX_GEOHASHES):
    shape = geojson_to_shape(data)

    if shape.geom_type == 'Point':
        return [pygeohash.encode(shape.y, shape.x, precision=precision)]

    geohashes = cover_shape(shape, precision, budget=GeohashBudget(max_geohashes))
    if not geohashes and not shape.is_empty:
        point = shape.representative_point()
        return [pygeohash.encode(point.y, point.x, precision=precision)]

    return geohashes


def geohashes_to_multipolygon(geohashes, simplify=False):
    polygons = []

    for geohash in geohashes:
        bounds = geohash_bbox(geohash)
        polygons.append(Polygon([
            (bounds['w'], bounds['n']),
            (bounds['e'], bounds['n']),
            (bounds['e'], bounds['s']),
            (bounds['w'], bounds['s']),
        ]))

    if simplify:
        return mapping(unary_union(polygons))
    return mapping(MultiPolygon(polygons))
