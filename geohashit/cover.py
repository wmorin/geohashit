import json
import math

import pygeohash
import shapely
import shapely.errors
from shapely.geometry import MultiPolygon, Point, Polygon, box, mapping
from shapely.ops import unary_union

from geohashit.json_validation import validate_json_depth

GEOHASH_CHARS = (
    '0', '1', '2', '3', '4', '5', '6', '7',
    '8', '9', 'b', 'c', 'd', 'e', 'f', 'g',
    'h', 'j', 'k', 'm', 'n', 'p', 'q', 'r',
    's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
)
MAX_GEOHASHES = 50_000
MAX_CELL_VISITS = 100_000
MAX_COORDINATES = 10_000
MAX_COMPONENTS = 1_000
MAX_UNION_EDGE_PAIRS = 100_000
COVER_MODES = ('center', 'inside', 'intersect')


class GeohashBudgetError(ValueError):
    pass


class GeohashBudget:
    def __init__(self, maximum, max_visits=MAX_CELL_VISITS):
        self.maximum = maximum
        self.count = 0
        self.max_visits = max_visits
        self.visits = 0

    def visit(self):
        self.visits += 1
        if self.visits > self.max_visits:
            raise GeohashBudgetError(
                'geohash coverage exceeds the maximum of %s cell visits; reduce precision'
                % self.max_visits
            )

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
        if budget is not None:
            budget.visit()
        geohash = prefix + char
        bounds = geohash_bbox(geohash)
        cell = box(bounds['w'], bounds['s'], bounds['e'], bounds['n'])
        yield from cover_cell(shape, cell, geohash, precision, level, budget)


def cover_shape(shape, precision=12, mode='center', level=1, prefix='', budget=None):
    return list(iter_cover_shape(shape, precision, mode, level, prefix, budget))


def validate_geojson(data, counter, depth=0):
    """Check bounded, finite WGS84 input before asking GEOS to construct it."""
    if depth > 8 or not isinstance(data, dict):
        raise ValueError('geojson must be a GeoJSON geometry, Feature, or FeatureCollection')
    counter[2] += 1
    if counter[2] > MAX_COORDINATES:
        raise GeohashBudgetError('geojson exceeds the maximum of %s geometry nodes' % MAX_COORDINATES)
    geometry_type = data.get('type')
    if not isinstance(geometry_type, str):
        raise ValueError('geojson contains invalid geometry')
    if geometry_type == 'FeatureCollection':
        features = data.get('features')
        if not isinstance(features, list) or len(features) > MAX_COORDINATES:
            raise ValueError('geojson features must be a bounded array')
        for feature in features:
            if not isinstance(feature, dict) or feature.get('type') != 'Feature':
                raise ValueError('geojson features must contain Features')
            validate_geojson(feature, counter, depth + 1)
    elif geometry_type == 'Feature':
        validate_geojson(data.get('geometry'), counter, depth + 1)
    elif geometry_type == 'GeometryCollection':
        geometries = data.get('geometries')
        if not isinstance(geometries, list) or len(geometries) > MAX_COORDINATES:
            raise ValueError('geojson geometries must be a bounded array')
        for geometry in geometries:
            validate_geojson(geometry, counter, depth + 1)
    else:
        coordinate_depth = {
            'Point': 0, 'MultiPoint': 1, 'LineString': 1,
            'MultiLineString': 2, 'Polygon': 2, 'MultiPolygon': 3,
        }.get(geometry_type)
        if coordinate_depth is None:
            raise ValueError('geojson contains invalid geometry')
        validate_coordinates(data.get('coordinates'), coordinate_depth, counter)
        coordinates = data['coordinates']
        if geometry_type == 'MultiPolygon':
            components = sum(max(1, len(polygon)) for polygon in coordinates)
        elif geometry_type == 'Polygon':
            components = max(1, len(coordinates))
        elif geometry_type.startswith('Multi'):
            components = len(coordinates)
        else:
            components = 1
        counter[1] += components
        if counter[1] > MAX_COMPONENTS:
            raise GeohashBudgetError('geojson exceeds the maximum of %s geometry components' % MAX_COMPONENTS)


def validate_coordinates(coordinates, depth, counter):
    if not isinstance(coordinates, (list, tuple)):
        raise ValueError('geojson contains invalid coordinates')
    if depth:
        if len(coordinates) > MAX_COORDINATES:
            raise ValueError('geojson exceeds the maximum of %s coordinates' % MAX_COORDINATES)
        for child in coordinates:
            validate_coordinates(child, depth - 1, counter)
        return
    # GeoJSON allows an empty coordinate array to describe an empty geometry.
    if not coordinates:
        return
    counter[0] += 1
    if counter[0] > MAX_COORDINATES:
        raise ValueError('geojson exceeds the maximum of %s coordinates' % MAX_COORDINATES)
    if len(coordinates) not in (2, 3) or any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not -1e308 <= value <= 1e308 or not math.isfinite(value) for value in coordinates
    ):
        raise ValueError('geojson coordinates must be finite numbers')
    if not -180 <= coordinates[0] <= 180 or not -90 <= coordinates[1] <= 90:
        raise ValueError('geojson coordinates must use longitude [-180, 180] and latitude [-90, 90]')


def geometry_to_shape(data):
    shape = shapely.geometry.shape(data)
    if not shape.is_valid:
        raise ValueError('geojson contains invalid geometry')
    ensure_geometry_budget(shape)
    return shape


def ensure_geometry_budget(shape):
    coordinates = int(shapely.get_num_coordinates(shape))
    if coordinates > MAX_COORDINATES:
        raise GeohashBudgetError(
            'normalized geometry exceeds the maximum of %s coordinates' % MAX_COORDINATES
        )
    def count_components(geometry):
        if geometry.geom_type == 'Polygon':
            return 1 + len(geometry.interiors)
        if hasattr(geometry, 'geoms'):
            return sum(count_components(child) for child in geometry.geoms)
        return 0 if geometry.is_empty else 1
    if count_components(shape) > MAX_COMPONENTS:
        raise GeohashBudgetError(
            'normalized geometry exceeds the maximum of %s geometry components' % MAX_COMPONENTS
        )
    return coordinates


def bounded_union(shapes):
    """Never hand GEOS an entire collection whose overlay may expand quadratically."""
    result = shapely.geometry.GeometryCollection()
    for shape in shapes:
        if shape.is_empty:
            continue
        if result.is_empty:
            result = shape
        else:
            left_bounds, right_bounds = result.bounds, shape.bounds
            overlapping_bounds = (
                left_bounds[0] <= right_bounds[2] and left_bounds[2] >= right_bounds[0]
                and left_bounds[1] <= right_bounds[3] and left_bounds[3] >= right_bounds[1]
            )
            # Check the worst-case overlay size before allocating even one union.
            # Disjoint bounds cannot introduce new edge intersections.
            edge_pairs = int(shapely.get_num_coordinates(result)) * int(shapely.get_num_coordinates(shape))
            if overlapping_bounds and edge_pairs > MAX_UNION_EDGE_PAIRS:
                raise GeohashBudgetError(
                    'geometry union exceeds the maximum of %s potential edge pairs; simplify the shapes'
                    % MAX_UNION_EDGE_PAIRS
                )
            result = result.union(shape)
        ensure_geometry_budget(result)
    return result


def geojson_to_shape(data):
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, RecursionError):
            raise ValueError('geojson must be valid JSON')

    validate_json_depth(data)
    validate_geojson(data, [0, 0, 0])
    try:
        if data['type'] == 'FeatureCollection':
            shapes = (
                geometry_to_shape(feature['geometry'])
                for feature in data['features']
            )
            return bounded_union(shapes)
        if data['type'] == 'Feature':
            return geometry_to_shape(data['geometry'])
        return geometry_to_shape(data)
    except (KeyError, TypeError):
        raise ValueError('geojson must be a GeoJSON geometry, Feature, or FeatureCollection')
    except GeohashBudgetError:
        raise
    except (shapely.errors.ShapelyError, ValueError, IndexError, AttributeError):
        raise ValueError('geojson contains invalid geometry')


def geojson_to_geohashes(data, precision, max_geohashes=MAX_GEOHASHES, mode=None,
                        max_cell_visits=MAX_CELL_VISITS):
    if isinstance(precision, bool) or not isinstance(precision, int) or not 1 <= precision <= 12:
        raise ValueError('precision must be an integer between 1 and 12')
    if mode is not None and mode not in COVER_MODES:
        raise ValueError('mode must be one of: %s' % ', '.join(COVER_MODES))
    shape = geojson_to_shape(data)

    if shape.is_empty:
        return []
    if mode is None and shape.geom_type == 'Point':
        return [pygeohash.encode(shape.y, shape.x, precision=precision)]

    geohashes = cover_shape(
        shape, precision, mode=mode or 'center',
        budget=GeohashBudget(max_geohashes, max_cell_visits),
    )
    if mode is None and not geohashes:
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
