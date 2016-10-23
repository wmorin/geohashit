import json

from flask import Flask, request, jsonify
from modules.Geohasher import Geohasher
from modules.Nominatim import Nominatim

app = Flask(__name__)


@app.route("/multipolygon_from_geohash", methods=['GET'])
def multipolygon_from_geohash():
    geohash = request.args.get('geohash')

    nominatim = Nominatim()
    city = nominatim.get_city_from_geohash(geohash)
    geohashes = Geohasher.geohash_geojson(json.loads(json_data))

    multi = geohasher.geohash_to_multipolygon(geohashes)

    return jsonify(geojson=multi)


@app.route("/multipolygon_from_point", methods=['GET'])
def multipolygon_from_point(city_name, country_code):
    lat = request.args.get('lat')
    lon = request.args.get('lon')

    nominatim = Nominatim()
    city = nominatim.get_city_from_point(geohash_encode(lat, lon, 6))
    geohashes = Geohasher.geohash_geojson(json.loads(json_data))

    multi = geohasher.geohash_to_multipolygon(geohashes)

    return jsonify(geojson=multi)


@app.route("/multipolygon_from_city", methods=['GET'])
def multipolygon_from_city():
    city_name = request.args.get('city_name')
    country_code = request.args.get('country_code')

    nominatim = Nominatim()
    city = nominatim.get_city_from_name(city_name, country_code)
    geohashes = Geohasher.geohash_geojson(json.loads(json_data))

    multi = geohasher.geohash_to_multipolygon(geohashes)

    return jsonify(geojson=multi)

@app.route("/geohash_from_geojson", methods=['POST'])
def geohash_from_geojson():
    json_data = request.form['geojson']
    geohashes = Geohasher.geohash_geojson(json.loads(json_data))

    return jsonify(geohashes=geohashes)


@app.route("/multipolygon_from_geojson", methods=['POST'])
def multipolygon_from_geojson():
    json_data = request.form['geojson']
    geohashes = Geohasher.geohash_geojson(json.loads(json_data))

    multi = geohasher.geohash_to_multipolygon(geohashes)

    return jsonify(geojson=multi)
