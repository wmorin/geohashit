import geohash
from shapely.geometry import box, Point


def neighbor(geo_hash, direction):
    """
    Find neighbor of a geohash string in certain direction.
    :param geo_hash: geohash string
    :type geo_hash: str
    :param direction: Direction is a two-element array, i.e. [1,0] means north, [1,1] means northeast
    :type direction: list
    :return: geohash string
    :rtype: str
    """
    decode_result = geohash.decode_exactly(geo_hash)
    neighbor_lat = decode_result[0] + direction[0] * decode_result[2] * 2
    neighbor_lon = decode_result[1] + direction[1] * decode_result[3] * 2
    return geohash.encode(neighbor_lat, neighbor_lon, len(geo_hash))


def geohash_shape(shape, precision, mode='intersect', threshold=None):
    """
    Find list of geohashes to cover the shape
    :param shape: shape to cover
    :type shape: BaseGeometry
    :param precision: geohash precision
    :type precision: int
    :param mode: 'intersect' - all geohashes intersect the shape
                               use 'threashold' option to specify a percentage of least coverage
                 'inside' - all geohashes inside the shape
                 'center' - all geohashes whose center is inside the shape
    :type mode: str
    :param threshold: percentage of least coverage
    :type threshold: float
    :return: list of geohashes
    :rtype: list
    """
    (min_lon, min_lat, max_lon, max_lat) = shape.bounds

    hash_south_west = geohash.encode(min_lat, min_lon, precision)
    hash_north_east = geohash.encode(max_lat, max_lon, precision)

    box_south_west = geohash.decode_exactly(hash_south_west)
    box_north_east = geohash.decode_exactly(hash_north_east)

    per_lat = box_south_west[2] * 2
    per_lon = box_south_west[3] * 2

    lat_step = int(round((box_north_east[0] - box_south_west[0]) / per_lat))
    lon_step = int(round((box_north_east[1] - box_south_west[1]) / per_lon))

    hash_list = []

    for lat in xrange(0, lat_step + 1):
        for lon in xrange(0, lon_step + 1):
            next_hash = neighbor(hash_south_west, [lat, lon])
            if mode == 'center':
                (lat_center, lon_center) = geohash.decode(next_hash)
                if shape.contains(Point(lon_center, lat_center)):
                    hash_list.append(next_hash)
            else:
                next_bbox = geohash.bbox(next_hash)
                next_bbox_geom = box(next_bbox['w'], next_bbox['s'], next_bbox['e'], next_bbox['n'])

                if mode == 'inside':
                    if shape.contains(next_bbox_geom):
                        hash_list.append(next_hash)
                elif mode == 'intersect':
                    if shape.intersects(next_bbox_geom):
                        if threshold is None:
                            hash_list.append(next_hash)
                        else:
                            intersected_area = shape.intersection(next_bbox_geom).area
                            if (intersected_area / next_bbox_geom.area) >= threshold:
                                hash_list.append(next_hash)

    return hash_list
