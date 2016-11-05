from flask import Flask, request, jsonify
from geohash import encode as geohash_encode
from modules.Geohasher import Geohasher
from modules.Nominatim import Nominatim

app = Flask(__name__)


@app.route("/multipolygon_from_geohash", methods=['GET'])
def multipolygon_from_geohash():
    """
    Get multipolygon geohashes of a city from a given geohash
    """
    geohash = request.args.get('geohash')

    nominatim = Nominatim()
    city = nominatim.get_city_from_geohash(geohash)
    geohashes = Geohasher.geohash_geojson(city.get_geometry())

    geohasher = Geohasher()
    multi = geohasher.geohash_to_multipolygon(geohashes)

    return jsonify(geojson=multi)


@app.route("/multipolygon_from_point", methods=['GET'])
def multipolygon_from_point(city_name, country_code):
    """
    Get multipolygon geohashes of a city from a given point
    """
    lat = request.args.get('lat')
    lon = request.args.get('lon')

    nominatim = Nominatim()
    city = nominatim.get_city_from_point(geohash_encode(lat, lon, 6))
    geohashes = Geohasher.geohash_geojson(city.get_geometry())

    geohasher = Geohasher()
    multi = Geohasher.geohash_to_multipolygon(geohashes)

    return jsonify(geojson=multi)


@app.route("/multipolygon_from_city", methods=['GET'])
def multipolygon_from_city():
    """
    Get multipolygon geohashes of a city from a given city and country
    """
    city_name = request.args.get('city_name')
    country_code = request.args.get('country_code')

    nominatim = Nominatim()
    city = nominatim.get_city_from_name(city_name, country_code)
    geohashes = Geohasher.geohash_geojson(city.get_geometry())

    multi = Geohasher.geohash_to_multipolygon(geohashes)

    return jsonify(geojson=multi)


@app.route("/geohash_from_geojson", methods=['POST'])
def geohash_from_geojson():
    """
    Get geohashes that form a city from a given geohash
    """
    json_data = request.form['geojson']
    geohashes = Geohasher.geohash_geojson(json_data)

    return jsonify(geohashes=geohashes)


@app.route("/multipolygon_from_geojson", methods=['POST'])
def multipolygon_from_geojson():
    """
    Get geohashes that form the given geojson
    """
    json_data = request.form['geojson']
    geohashes = Geohasher.geohash_geojson(json_data)

    multi = Geohasher.geohash_to_multipolygon(geohashes)

    return jsonify(geojson=multi)
