from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from geohashit.cover import geojson_to_geohashes, geohashes_to_multipolygon
from geohashit.nominatim import Nominatim, NominatimError, NominatimLookupError
from geohashit.validation import (
    DEFAULT_PRECISION,
    ValidationError,
    get_bool_arg,
    get_choice_arg,
    get_float_arg,
    get_geohash_arg,
    get_geojson_payload,
    get_precision_arg,
    get_required_arg,
)

API_ENDPOINTS = [
    {
        'path': '/multipolygon_from_point',
        'methods': ['GET'],
        'description': (
            'Resolve a city or country from a point and return geohash polygons.'
        ),
    },
    {
        'path': '/multipolygon_from_city',
        'methods': ['GET'],
        'description': 'Resolve a named city and return geohash polygons.',
    },
    {
        'path': '/multipolygon_from_geohash',
        'methods': ['GET'],
        'description': (
            'Resolve the city containing a geohash and return geohash polygons.'
        ),
    },
    {
        'path': '/geohash_from_geojson',
        'methods': ['POST'],
        'description': 'Return geohashes covering a submitted GeoJSON shape.',
    },
    {
        'path': '/multipolygon_from_geojson',
        'methods': ['POST'],
        'description': 'Return geohash polygons for a submitted GeoJSON shape.',
    },
]


def create_app():
    app = Flask('geohashit')
    app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024

    register_error_handlers(app)
    register_routes(app)

    return app


def register_error_handlers(app):
    @app.errorhandler(ValidationError)
    def handle_validation_error(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_too_large(error):
        return jsonify(error='request body is too large'), 413

    @app.errorhandler(NominatimLookupError)
    def handle_nominatim_lookup_error(error):
        return jsonify(error=str(error)), 404

    @app.errorhandler(NominatimError)
    def handle_nominatim_error(error):
        return jsonify(error=str(error)), 502

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        return jsonify(error=error.description), error.code


def register_routes(app):
    @app.route('/', methods=['GET'])
    def service_index():
        return jsonify(
            name="Geohash'it",
            description='Convert places and GeoJSON shapes into geohash coverage polygons.',
            status='ok',
            endpoints=API_ENDPOINTS,
        )

    @app.route('/health', methods=['GET'])
    def health():
        return jsonify(status='ok')

    @app.route('/multipolygon_from_geohash', methods=['GET'])
    def multipolygon_from_geohash():
        geohash = get_geohash_arg('geohash')
        precision = get_precision_arg(default=DEFAULT_PRECISION)

        city = Nominatim().get_city_from_geohash(geohash)
        geohashes = geohash_geojson(city.geometry, precision)

        return jsonify(geojson=geohashes_to_multipolygon(geohashes))

    @app.route('/multipolygon_from_point', methods=['GET'])
    def multipolygon_from_point():
        lat = get_float_arg('lat', -90, 90)
        lon = get_float_arg('lon', -180, 180)
        poly_type = get_choice_arg('type', ('city', 'country'))
        precision = get_precision_arg()
        simplify = get_bool_arg('simplify')

        nominatim = Nominatim()
        if poly_type == 'city':
            place = nominatim.get_city_from_point(lat, lon)
        else:
            place = nominatim.get_country_from_point(lat, lon)

        geohashes = geohash_geojson(place.geometry, precision)

        return jsonify(geojson=geohashes_to_multipolygon(geohashes, simplify))

    @app.route('/multipolygon_from_city', methods=['GET'])
    def multipolygon_from_city():
        city_name = get_required_arg('city_name')
        country_code = get_required_arg('country_code')
        precision = get_precision_arg(default=DEFAULT_PRECISION)

        city = Nominatim().get_city_from_name(city_name, country_code)
        geohashes = geohash_geojson(city.geometry, precision)

        return jsonify(geojson=geohashes_to_multipolygon(geohashes))

    @app.route('/geohash_from_geojson', methods=['POST'])
    def geohash_from_geojson_route():
        json_data = get_geojson_payload()
        precision = get_precision_arg(default=DEFAULT_PRECISION)

        return jsonify(geohashes=geohash_geojson(json_data, precision))

    @app.route('/multipolygon_from_geojson', methods=['POST'])
    def multipolygon_from_geojson():
        json_data = get_geojson_payload()
        precision = get_precision_arg(default=DEFAULT_PRECISION)
        geohashes = geohash_geojson(json_data, precision)

        return jsonify(geojson=geohashes_to_multipolygon(geohashes))


def geohash_geojson(json_data, precision):
    try:
        return geojson_to_geohashes(json_data, precision)
    except ValueError as error:
        raise ValidationError(str(error))


app = create_app()
