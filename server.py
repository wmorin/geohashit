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
def multipolygon_from_point():
    """
    Get multipolygon geohashes of a city from a given point
    """
    lat = float(request.args.get('lat'))
    lon = float(request.args.get('lon'))
    poly_type = request.args.get('type')
    precision = int(request.args.get('precision'))
    simplify = True if str(request.args.get('simplify')) == str(1) else False

    nominatim = Nominatim()

    if poly_type == 'city':
        poly = nominatim.get_city_from_point(lat, lon)
        geohashes = Geohasher.geohash_geojson(poly.get_geometry(), precision)
    elif poly_type == 'country':
        poly = nominatim.get_country_from_point(lat, lon)
        geohashes = Geohasher.geohash_geojson(poly.get_geometry(), precision)

    geohasher = Geohasher()
    multi = geohasher.geohash_to_multipolygon(geohashes, simplify)

    return jsonify(geojson=multi)


@app.route("/multipolygon_country_from_point", methods=['GET'])
def multipolygon_country_from_point():
    """
    Get multipolygon geohashes of a city from a given point
    """
    lat = float(request.args.get('lat'))
    lon = float(request.args.get('lon'))

    nominatim = Nominatim()
    country = nominatim.get_country_from_point(lat, lon)
    geohashes = Geohasher.geohash_geojson(country.get_geometry())

    geohasher = Geohasher()
    multi = geohasher.geohash_to_multipolygon(geohashes)

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
