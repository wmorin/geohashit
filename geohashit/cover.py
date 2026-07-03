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


def cover_shape(shape, precision=12, mode='center', level=1, prefix=''):
    geohashes = []

    for char in GEOHASH_CHARS:
        geohash = prefix + char
        bounds = geohash_bbox(geohash)
        cell = box(bounds['w'], bounds['s'], bounds['e'], bounds['n'])

        if mode == 'inside':
            if shape.contains(cell):
                geohashes.append(geohash)
            elif level < precision and cell.intersects(shape):
                geohashes.extend(cover_shape(shape, precision, mode, level + 1, geohash))

        elif mode == 'center':
            if shape.contains(cell):
                geohashes.append(geohash)
            elif level < precision and cell.intersects(shape):
                geohashes.extend(
                    cover_shape(cell.intersection(shape), precision, mode, level + 1, geohash)
                )
            elif level == precision:
                lat, lon = decode_geohash(geohash)
                if shape.contains(Point(lon, lat)):
                    geohashes.append(geohash)

        elif mode == 'intersect':
            if shape.contains(cell):
                geohashes.append(geohash)
            elif level < precision and cell.intersects(shape):
                geohashes.extend(cover_shape(shape, precision, mode, level + 1, geohash))
            elif level == precision and cell.intersects(shape):
                geohashes.append(geohash)

    return geohashes


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


def geojson_to_geohashes(data, precision):
    shape = geojson_to_shape(data)

    if shape.geom_type == 'Point':
        return [pygeohash.encode(shape.y, shape.x, precision=precision)]

    geohashes = cover_shape(shape, precision)
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
