from flask import Flask, jsonify, request
import pygeohash
from werkzeug.exceptions import RequestEntityTooLarge

from modules.Geohasher import Geohasher
from modules.Nominatim import Nominatim, NominatimError, NominatimLookupError

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024

MIN_PRECISION = 1
MAX_PRECISION = 8
DEFAULT_PRECISION = 5


class ValidationError(Exception):
    pass


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


def get_required_arg(name):
    value = request.args.get(name)
    if value is None or value == '':
        raise ValidationError('%s is required' % name)
    return value


def get_geohash_arg(name):
    value = get_required_arg(name)
    try:
        pygeohash.decode(value)
    except ValueError:
        raise ValidationError('%s must be a valid geohash' % name)
    return value


def get_required_form_field(name):
    value = request.form.get(name)
    if value is None or value == '':
        raise ValidationError('%s is required' % name)
    return value


def get_float_arg(name, minimum=None, maximum=None):
    value = get_required_arg(name)
    try:
        parsed = float(value)
    except ValueError:
        raise ValidationError('%s must be a number' % name)

    if minimum is not None and parsed < minimum:
        raise ValidationError('%s must be at least %s' % (name, minimum))
    if maximum is not None and parsed > maximum:
        raise ValidationError('%s must be at most %s' % (name, maximum))

    return parsed


def get_precision_arg(default=None):
    raw_value = request.args.get('precision')
    if raw_value is None or raw_value == '':
        if default is not None:
            return default
        raise ValidationError('precision is required')

    try:
        precision = int(raw_value)
    except ValueError:
        raise ValidationError('precision must be an integer')

    if precision < MIN_PRECISION or precision > MAX_PRECISION:
        raise ValidationError(
            'precision must be between %s and %s' % (MIN_PRECISION, MAX_PRECISION)
        )

    return precision


def get_choice_arg(name, choices):
    value = get_required_arg(name)
    if value not in choices:
        raise ValidationError('%s must be one of: %s' % (name, ', '.join(choices)))
    return value


def get_bool_arg(name, default=False):
    value = request.args.get(name)
    if value is None or value == '':
        return default
    if value in ('1', 'true', 'True'):
        return True
    if value in ('0', 'false', 'False'):
        return False
    raise ValidationError('%s must be a boolean' % name)


def geohash_geojson(json_data, precision):
    try:
        return Geohasher.geohash_geojson(json_data, precision)
    except ValueError as error:
        raise ValidationError(str(error))


@app.route("/multipolygon_from_geohash", methods=['GET'])
def multipolygon_from_geohash():
    """
    Get multipolygon geohashes of a city from a given geohash
    """
    geohash = get_geohash_arg('geohash')

    nominatim = Nominatim()
    city = nominatim.get_city_from_geohash(geohash)
    precision = get_precision_arg(default=DEFAULT_PRECISION)
    geohashes = geohash_geojson(city.get_geometry(), precision)

    geohasher = Geohasher()
    multi = geohasher.geohash_to_multipolygon(geohashes)

    return jsonify(geojson=multi)


@app.route("/multipolygon_from_point", methods=['GET'])
def multipolygon_from_point():
    """
    Get multipolygon geohashes of a city from a given point
    """
    lat = get_float_arg('lat', -90, 90)
    lon = get_float_arg('lon', -180, 180)
    poly_type = get_choice_arg('type', ('city', 'country'))
    precision = get_precision_arg()
    simplify = get_bool_arg('simplify')

    nominatim = Nominatim()

    if poly_type == 'city':
        poly = nominatim.get_city_from_point(lat, lon)
        geohashes = geohash_geojson(poly.get_geometry(), precision)
    elif poly_type == 'country':
        poly = nominatim.get_country_from_point(lat, lon)
        geohashes = geohash_geojson(poly.get_geometry(), precision)

    geohasher = Geohasher()
    multi = geohasher.geohash_to_multipolygon(geohashes, simplify)

    return jsonify(geojson=multi)


@app.route("/multipolygon_country_from_point", methods=['GET'])
def multipolygon_country_from_point():
    """
    Get multipolygon geohashes of a city from a given point
    """
    lat = get_float_arg('lat', -90, 90)
    lon = get_float_arg('lon', -180, 180)

    nominatim = Nominatim()
    country = nominatim.get_country_from_point(lat, lon)
    precision = get_precision_arg(default=DEFAULT_PRECISION)
    geohashes = geohash_geojson(country.get_geometry(), precision)

    geohasher = Geohasher()
    multi = geohasher.geohash_to_multipolygon(geohashes)

    return jsonify(geojson=multi)

@app.route("/multipolygon_from_city", methods=['GET'])
def multipolygon_from_city():
    """
    Get multipolygon geohashes of a city from a given city and country
    """
    city_name = get_required_arg('city_name')
    country_code = get_required_arg('country_code')

    nominatim = Nominatim()
    city = nominatim.get_city_from_name(city_name, country_code)
    precision = get_precision_arg(default=DEFAULT_PRECISION)
    geohashes = geohash_geojson(city.get_geometry(), precision)

    geohasher = Geohasher()
    multi = geohasher.geohash_to_multipolygon(geohashes)

    return jsonify(geojson=multi)


@app.route("/geohash_from_geojson", methods=['POST'])
def geohash_from_geojson():
    """
    Get geohashes that form a city from a given geohash
    """
    json_data = get_required_form_field('geojson')
    precision = get_precision_arg(default=DEFAULT_PRECISION)
    geohashes = geohash_geojson(json_data, precision)

    return jsonify(geohashes=geohashes)


@app.route("/multipolygon_from_geojson", methods=['POST'])
def multipolygon_from_geojson():
    """
    Get geohashes that form the given geojson
    """
    json_data = get_required_form_field('geojson')
    precision = get_precision_arg(default=DEFAULT_PRECISION)
    geohashes = geohash_geojson(json_data, precision)

    geohasher = Geohasher()
    multi = geohasher.geohash_to_multipolygon(geohashes)

    return jsonify(geojson=multi)
