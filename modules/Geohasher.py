import shapely

from geohash import bbox, decode
from geojson import MultiPolygon
from shapely.geometry import box, Point, Polygon, mapping
from shapely.ops import cascaded_union


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

            p = bbox(hash)
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
                    geohashes.extend(self.geohash_shape(shape, precision, mode, level + 1, hash))
                elif level == precision:
                    (lat, lon) = decode(str(hash))

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

    def json_to_geohashes(self, data, precision):
        for f in data['features']:
            s = shapely.geometry.shape(f['geometry'])

        return self.geohash_shape(s, precision)

    def geohash_to_multipolygon(self, geohashes, simplify=False):
        polys = []

        for g in geohashes:
            box = bbox(g)

            polys.append(Polygon([
                (box['w'], box['n']),
                (box['e'], box['n']),
                (box['e'], box['s']),
                (box['w'], box['s']),
            ]))

        if simplify:
            polys = cascaded_union(polys)
        else:
            polys = MultiPolygon(polys)

        return mapping(polys)

    @staticmethod
    def geohash_geojson(geojson, precision):
        geohasher = Geohasher()

        return geohasher.json_to_geohashes(geojson, precision)
