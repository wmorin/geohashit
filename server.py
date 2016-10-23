import json

from flask import Flask, request, jsonify
from modules.Geohasher import Geohasher
from modules.Nominatim import Nominatim

app = Flask(__name__)

def geohash_geojson(data):
    geohasher = Geohasher()
    geohashes = geohasher.json_to_geohashes(data)

    return geohashes


@app.route("/geohash", methods=['POST'])
def geohash():
    json_data = request.form['geojson']
    geohashes = geohash_geojson(json.loads(json_data))

    return jsonify(geohashes=geohashes)


@app.route("/geojson", methods=['POST'])
def shaper():
    json_data = request.form['geojson']
    geohashes = geohash_geojson(json.loads(json_data))

    multi = geohasher.geohash_to_multipolygon(geohashes)

    return jsonify(geojson=multi)
