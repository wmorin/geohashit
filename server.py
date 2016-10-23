import json

from flask import Flask, request, jsonify
from geohash import bbox
from geohashshape import geohash_shape
from geojson import MultiPolygon
from shapely.geometry import shape

app = Flask(__name__)


def get_geohash_chars():
    return [
        '0', '1', '2', '3', '4', '5', '6', '7',
        '8', '9', 'b', 'c', 'd', 'e', 'f', 'g',
        'h', 'j', 'k', 'm', 'n', 'p', 'q', 'r',
        's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
    ]


def reduce_geohash(geohashes, precision=12):
    if precision == 1:
        return geohashes

    chars = get_geohash_chars()

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

    return reduce_geohash(filtered, precision - 1)


def json_to_geohashes(data):
    for f in data['features']:
        s = shape(f['geometry'])

    precision = 4
    mode = 'center'
    threshold = None
    geohashes = geohash_shape(s, precision, mode, threshold)

    return geohashes


@app.route("/geohash", methods=['POST'])
def geohash():
    # if not request.form['geojson']:
    #     error = 'You have to provide a valid geojson'

    json_data = request.form['geojson']
    data = json.loads(json_data)
    geohashes = json_to_geohashes(data)
    geohashes = reduce_geohash(geohashes)

    return jsonify(geohashes=geohashes)


@app.route("/shape", methods=['POST'])
def shaper():
    # if not request.form['geojson']:
    #     error = 'You have to provide a valid geojson'

    json_data = request.form['geojson']
    data = json.loads(json_data)
    geohashes = json_to_geohashes(data)
    geohashes = reduce_geohash(geohashes)

    polys = []

    for g in geohashes:
        box = bbox(g)
        polys.append([
            (box['w'], box['n']),
            (box['e'], box['n']),
            (box['e'], box['s']),
            (box['w'], box['s']),
            (box['w'], box['n']),
        ])

    multi = MultiPolygon([polys])

    return jsonify(geojson=multi)


@app.route("/simpleshape", methods=['POST'])
def simpleshaper():
    json_data = request.form['geojson']
    data = json.loads(json_data)
    geohashes = json_to_geohashes(data)
    geohashes = reduce_geohash(geohashes)

    polys = []

    for g in geohashes:
        box = bbox(g)
        polys.append([
            (box['w'], box['n']),
            (box['e'], box['n']),
            (box['e'], box['s']),
            (box['w'], box['s']),
            (box['w'], box['n']),
        ])

    multi = MultiPolygon([polys])

    return jsonify(geojson=multi)
