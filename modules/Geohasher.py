from geohash import bbox as geohash_bbox
from geohash import decode as geohash_decode
from geohash import encode as geohash_encode
from geohashshape import geohash_shape
from geojson import MultiPolygon
from shapely.geometry import shape

class Geohasher:
    def _get_geohash_chars(self):
        return [
            '0', '1', '2', '3', '4', '5', '6', '7',
            '8', '9', 'b', 'c', 'd', 'e', 'f', 'g',
            'h', 'j', 'k', 'm', 'n', 'p', 'q', 'r',
            's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
        ]


    def reduce_geohash(self, geohashes, precision=12):
        if precision == 1:
            return geohashes

        chars = self._get_geohash_chars()

        filtered = []
        excluded = []

        for geohash in geohashes:
            if len(geohash) < precision:
                filtered.append(geohash)
                continue

            if geohash in excluded:
                continue

            base = geohash[:-1]
            keep = False

            for char in chars:
                if (base + char) not in geohashes:
                    keep = True

            if keep is True:
                filtered.append(geohash)
                continue

            filtered.append(base)

            for char in chars:
                excluded.append(base + char)

        return self.reduce_geohash(filtered, precision - 1)

    def json_to_geohashes(self, data, simplify=True):
        for f in data['features']:
            s = shape(f['geometry'])

        precision = 6
        mode = 'center'
        threshold = None
        geohashes = geohash_shape(s, precision, mode, threshold)

        if simplify is True:
            return self.reduce_geohash(geohashes)

        return geohashes


    def geohash_to_multipolygon(self, geohashes):
        polys = []

        for g in geohashes:
            box = geohash_bbox(g)
            polys.append([
                (box['w'], box['n']),
                (box['e'], box['n']),
                (box['e'], box['s']),
                (box['w'], box['s']),
                (box['w'], box['n']),
            ])

        return MultiPolygon([polys])
