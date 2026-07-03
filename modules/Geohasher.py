import json

import shapely

import pygeohash
from shapely.geometry import MultiPolygon, Point, Polygon, box, mapping
from shapely.ops import unary_union


def _bbox(geohash):
    bounds = pygeohash.get_bounding_box(geohash)
    return {
        'n': bounds.max_lat,
        's': bounds.min_lat,
        'e': bounds.max_lon,
        'w': bounds.min_lon,
    }


def _decode(geohash):
    decoded = pygeohash.decode(geohash)
    return decoded.latitude, decoded.longitude


class Geohasher:
    def _get_geohash_chars(self):
        return [
            '0', '1', '2', '3', '4', '5', '6', '7',
            '8', '9', 'b', 'c', 'd', 'e', 'f', 'g',
            'h', 'j', 'k', 'm', 'n', 'p', 'q', 'r',
            's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
        ]

    def geohash_shape(self, shape, precision=12, mode='center', level=1, prefix=''):
        geohashes = []

        for char in self._get_geohash_chars():
            hash = prefix + char

            p = _bbox(hash)
            box_shape = box(p['w'], p['s'], p['e'], p['n'])

            if mode == 'inside':
                if shape.contains(box_shape):
                    geohashes.extend([hash])
                elif level < precision and box_shape.intersects(shape):
                    geohashes.extend(self.geohash_shape(shape, precision, mode, level + 1, hash))

            elif mode == 'center':
                if shape.contains(box_shape):
                    geohashes.extend([hash])
                elif level < precision and box_shape.intersects(shape):
                    sub_shape = box_shape.intersection(shape)
                    geohashes.extend(self.geohash_shape(sub_shape, precision, mode, level + 1, hash))
                elif level == precision:
                    (lat, lon) = _decode(str(hash))

                    if shape.contains(Point(lon, lat)):
                        geohashes.append(hash)

            elif mode == 'intersect':
                if shape.contains(box_shape):
                    geohashes.extend([hash])
                elif level < precision and box_shape.intersects(shape):
                    geohashes.extend(self.geohash_shape(shape, precision, mode, level + 1, hash))
                elif level == precision and box_shape.intersects(shape):
                    geohashes.append(hash)

        return geohashes

    def geojson_to_geohashes(self, data, precision):
        if isinstance(data, str):
            data = json.loads(data)

        if data['type'] == 'FeatureCollection':
            shapes = [
                shapely.geometry.shape(feature['geometry'])
                for feature in data['features']
            ]
            shape = unary_union(shapes)
        elif data['type'] == 'Feature':
            shape = shapely.geometry.shape(data['geometry'])
        else:
            shape = shapely.geometry.shape(data)

        return self.geohash_shape(shape, precision)

    def geohash_to_multipolygon(self, geohashes, simplify=False):
        polys = []

        for g in geohashes:
            bounds = _bbox(g)

            polys.append(Polygon([
                (bounds['w'], bounds['n']),
                (bounds['e'], bounds['n']),
                (bounds['e'], bounds['s']),
                (bounds['w'], bounds['s']),
            ]))

        if simplify:
            polys = unary_union(polys)
        else:
            polys = MultiPolygon(polys)

        return mapping(polys)

    @staticmethod
    def geohash_geojson(geojson, precision):
        geohasher = Geohasher()

        return geohasher.geojson_to_geohashes(geojson, precision)
