from flask import Flask, current_app, jsonify
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from geohashit.cover import (
    GeohashBudgetError,
    geojson_to_geohashes,
    geohashes_to_multipolygon,
)
from geohashit.metadata import API_ENDPOINTS, SERVICE_DESCRIPTION, SERVICE_NAME
from geohashit.nominatim import Nominatim, NominatimError, NominatimLookupError
from geohashit.openapi import OPENAPI_SPEC
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

def create_app(nominatim_factory=None):
    app = Flask('geohashit')
    app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024
    app.config['NOMINATIM_FACTORY'] = nominatim_factory or (lambda: Nominatim())

    register_error_handlers(app)
    register_routes(app)

    return app


def register_error_handlers(app):
    @app.errorhandler(ValidationError)
    def handle_validation_error(error):
        return error_response('validation_error', str(error), 400)

    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_too_large(error):
        return error_response('payload_too_large', 'request body is too large', 413)

    @app.errorhandler(NominatimLookupError)
    def handle_nominatim_lookup_error(error):
        return error_response('place_not_found', str(error), 404)

    @app.errorhandler(NominatimError)
    def handle_nominatim_error(error):
        return error_response('upstream_error', str(error), 502)

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        code = error.name.lower().replace(' ', '_')
        return error_response(code, error.description, error.code)


def register_routes(app):
    @app.route('/', methods=['GET'])
    def service_index():
        return jsonify(
            name=SERVICE_NAME,
            description=SERVICE_DESCRIPTION,
            status='ok',
            endpoints=API_ENDPOINTS,
        )

    @app.route('/health', methods=['GET'])
    def health():
        return jsonify(status='ok')

    @app.route('/openapi.json', methods=['GET'])
    def openapi_json():
        return jsonify(OPENAPI_SPEC)

    @app.route('/multipolygons/geohash', methods=['GET'])
    def geohash_multipolygon():
        geohash = get_geohash_arg('geohash')
        precision = get_precision_arg(default=DEFAULT_PRECISION)

        city = get_nominatim().get_city_from_geohash(geohash)
        geohashes = geohash_geojson(city.geometry, precision)

        return jsonify(geojson=geohashes_to_multipolygon(geohashes))

    @app.route('/multipolygons/point', methods=['GET'])
    def point_multipolygon():
        lat = get_float_arg('lat', -90, 90)
        lon = get_float_arg('lon', -180, 180)
        poly_type = get_choice_arg('type', ('city', 'country'))
        precision = get_precision_arg()
        simplify = get_bool_arg('simplify')

        nominatim = get_nominatim()
        if poly_type == 'city':
            place = nominatim.get_city_from_point(lat, lon)
        else:
            place = nominatim.get_country_from_point(lat, lon)

        geohashes = geohash_geojson(place.geometry, precision)

        return jsonify(geojson=geohashes_to_multipolygon(geohashes, simplify))

    @app.route('/multipolygons/city', methods=['GET'])
    def city_multipolygon():
        city_name = get_required_arg('city_name')
        country_code = get_required_arg('country_code')
        precision = get_precision_arg(default=DEFAULT_PRECISION)

        city = get_nominatim().get_city_from_name(city_name, country_code)
        geohashes = geohash_geojson(city.geometry, precision)

        return jsonify(geojson=geohashes_to_multipolygon(geohashes))

    @app.route('/geohashes/geojson', methods=['POST'])
    def geojson_geohashes():
        json_data = get_geojson_payload()
        precision = get_precision_arg(default=DEFAULT_PRECISION)

        return jsonify(geohashes=geohash_geojson(json_data, precision))

    @app.route('/multipolygons/geojson', methods=['POST'])
    def geojson_multipolygon():
        json_data = get_geojson_payload()
        precision = get_precision_arg(default=DEFAULT_PRECISION)
        geohashes = geohash_geojson(json_data, precision)

        return jsonify(geojson=geohashes_to_multipolygon(geohashes))


def error_response(code, message, status):
    return jsonify(error={'code': code, 'message': message, 'status': status}), status


def get_nominatim():
    return current_app.config['NOMINATIM_FACTORY']()


def geohash_geojson(json_data, precision):
    try:
        return geojson_to_geohashes(json_data, precision)
    except GeohashBudgetError as error:
        raise ValidationError(str(error))
    except ValueError as error:
        raise ValidationError(str(error))


app = create_app()
