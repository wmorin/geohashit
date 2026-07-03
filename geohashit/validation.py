import pygeohash
from flask import request

MIN_PRECISION = 1
MAX_PRECISION = 8
DEFAULT_PRECISION = 5


class ValidationError(Exception):
    pass


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


def get_json_payload():
    if not request.is_json:
        return None

    payload = request.get_json(silent=True)
    if payload is None:
        raise ValidationError('geojson must be valid JSON')
    return payload


def get_geojson_payload():
    form_value = request.form.get('geojson')
    if form_value is not None and form_value != '':
        return form_value

    payload = get_json_payload()
    if payload is None:
        raise ValidationError('geojson is required')

    if isinstance(payload, dict) and 'geojson' in payload:
        geojson = payload['geojson']
        if geojson == '':
            raise ValidationError('geojson is required')
        return geojson

    return payload


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
        raw_value = request.form.get('precision')
    if raw_value is None or raw_value == '':
        payload = request.get_json(silent=True) if request.is_json else None
        if isinstance(payload, dict):
            raw_value = payload.get('precision')

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
