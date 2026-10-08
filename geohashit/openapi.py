from geohashit.metadata import API_VERSION, SERVICE_DESCRIPTION, SERVICE_NAME


def json_response(description, schema):
    return {
        'description': description,
        'content': {
            'application/json': {
                'schema': {'$ref': '#/components/schemas/%s' % schema},
            },
        },
    }


def query_parameter(name, description, schema_type, required):
    return {
        'name': name,
        'in': 'query',
        'required': required,
        'description': description,
        'schema': {'type': schema_type},
    }


def precision_parameter(required):
    return {
        'name': 'precision',
        'in': 'query',
        'required': required,
        'description': 'Geohash precision from 1 to 8. Defaults to 5 when omitted.',
        'schema': {'$ref': '#/components/schemas/Precision'},
    }


def mode_parameter():
    return {
        'name': 'mode',
        'in': 'query',
        'required': False,
        'description': (
            'Coverage rule: center keeps cells whose center is strictly inside the shape; '
            'inside keeps only fully contained cells; intersect keeps cells touching the shape. '
            'Fully contained cells may use shorter geohash prefixes. Explicit modes may return '
            'an empty array. Omitting mode preserves legacy center coverage with a '
            'representative-point fallback for small shapes.'
        ),
        'schema': {'$ref': '#/components/schemas/CoverageMode'},
    }


def boolean_parameter(name, description):
    return {
        'name': name,
        'in': 'query',
        'required': False,
        'description': description,
        'schema': {
            'oneOf': [
                {'type': 'boolean'},
                {'type': 'string', 'enum': ['true', 'false', '1', '0']},
            ],
            'default': False,
        },
    }


def geojson_request_body():
    return {
        'required': True,
        'content': {
            'application/json': {
                'schema': {
                    'oneOf': [
                        {'$ref': '#/components/schemas/GeoJSON'},
                        {'$ref': '#/components/schemas/GeoJSONEnvelope'},
                    ],
                },
            },
            'application/x-www-form-urlencoded': {
                'schema': {'$ref': '#/components/schemas/GeoJSONForm'},
            },
            'multipart/form-data': {
                'schema': {'$ref': '#/components/schemas/GeoJSONForm'},
            },
        },
    }


def geohash_multipolygon_responses(include_not_found=True):
    responses = {
        '200': json_response('GeoJSON multipolygon response.', 'MultipolygonResponse'),
        **common_error_responses(include_not_found=include_not_found),
    }
    return responses


def common_error_responses(include_not_found=True):
    responses = {
        '400': json_response('Invalid request.', 'Error'),
        '413': json_response('Request payload is too large.', 'Error'),
        '502': json_response('Upstream Nominatim failure.', 'Error'),
    }
    if include_not_found:
        responses['404'] = json_response('Place not found.', 'Error')
    return responses


OPENAPI_SPEC = {
    'openapi': '3.2.0',
    'info': {
        'title': '%s API' % SERVICE_NAME,
        'version': API_VERSION,
        'description': SERVICE_DESCRIPTION,
    },
    'servers': [{'url': '/'}],
    'tags': [
        {'name': 'service'},
        {'name': 'multipolygons'},
        {'name': 'geohashes'},
    ],
    'paths': {
        '/': {
            'get': {
                'tags': ['service'],
                'summary': 'Service metadata',
                'responses': {
                    '200': json_response('Service metadata', 'ServiceMetadata'),
                },
            },
        },
        '/health': {
            'get': {
                'tags': ['service'],
                'summary': 'Health check',
                'responses': {
                    '200': json_response('Service is healthy', 'Health'),
                },
            },
        },
        '/openapi.json': {
            'get': {
                'tags': ['service'],
                'summary': 'OpenAPI description',
                'responses': {
                    '200': {
                        'description': 'OpenAPI description for this API.',
                        'content': {
                            'application/json': {
                                'schema': {'type': 'object'},
                            },
                        },
                    },
                },
            },
        },
        '/multipolygons/point': {
            'get': {
                'tags': ['multipolygons'],
                'summary': 'Resolve a point to a city or country multipolygon',
                'parameters': [
                    query_parameter('lat', 'Latitude from -90 to 90.', 'number', True),
                    query_parameter('lon', 'Longitude from -180 to 180.', 'number', True),
                    {
                        'name': 'type',
                        'in': 'query',
                        'required': True,
                        'description': 'Place boundary type to resolve.',
                        'schema': {'type': 'string', 'enum': ['city', 'country']},
                    },
                    precision_parameter(required=True),
                    mode_parameter(),
                    boolean_parameter(
                        'simplify',
                        'Return a dissolved geometry instead of one polygon per geohash.',
                    ),
                ],
                'responses': geohash_multipolygon_responses(),
            },
        },
        '/multipolygons/city': {
            'get': {
                'tags': ['multipolygons'],
                'summary': 'Resolve a city name to a geohash multipolygon',
                'parameters': [
                    query_parameter('city_name', 'City name.', 'string', True),
                    query_parameter(
                        'country_code',
                        'Two-letter country code.',
                        'string',
                        True,
                    ),
                    precision_parameter(required=False),
                    mode_parameter(),
                ],
                'responses': geohash_multipolygon_responses(),
            },
        },
        '/multipolygons/geohash': {
            'get': {
                'tags': ['multipolygons'],
                'summary': 'Resolve a geohash to its containing city multipolygon',
                'parameters': [
                    query_parameter('geohash', 'Valid geohash.', 'string', True),
                    precision_parameter(required=False),
                    mode_parameter(),
                ],
                'responses': geohash_multipolygon_responses(),
            },
        },
        '/geohashes/geojson': {
            'post': {
                'tags': ['geohashes'],
                'summary': 'Return geohashes covering submitted GeoJSON',
                'parameters': [precision_parameter(required=False), mode_parameter()],
                'requestBody': geojson_request_body(),
                'responses': {
                    '200': json_response('Geohash coverage.', 'GeohashList'),
                    **common_error_responses(),
                },
            },
        },
        '/multipolygons/geojson': {
            'post': {
                'tags': ['multipolygons'],
                'summary': 'Return geohash cells as a GeoJSON multipolygon',
                'parameters': [precision_parameter(required=False), mode_parameter()],
                'requestBody': geojson_request_body(),
                'responses': geohash_multipolygon_responses(include_not_found=False),
            },
        },
    },
    'components': {
        'schemas': {
            'Endpoint': {
                'type': 'object',
                'required': ['path', 'methods', 'description'],
                'properties': {
                    'path': {'type': 'string'},
                    'methods': {
                        'type': 'array',
                        'items': {'type': 'string'},
                    },
                    'description': {'type': 'string'},
                },
            },
            'ServiceMetadata': {
                'type': 'object',
                'required': ['name', 'description', 'status', 'endpoints'],
                'properties': {
                    'name': {'type': 'string'},
                    'description': {'type': 'string'},
                    'status': {'type': 'string'},
                    'endpoints': {
                        'type': 'array',
                        'items': {'$ref': '#/components/schemas/Endpoint'},
                    },
                },
            },
            'Health': {
                'type': 'object',
                'required': ['status'],
                'properties': {'status': {'type': 'string', 'const': 'ok'}},
            },
            'GeoJSON': {
                'type': 'object',
                'description': (
                    'Valid GeoJSON geometry, feature, or feature collection with finite '
                    'WGS84 longitude/latitude coordinates. Maximum 10,000 source and normalized positions '
                    'and 1,000 geometry components (including polygon holes). Collection unions are '
                    'incremental; potentially complex overlays are rejected before computation. '
                    'Coverage is planar: split antimeridian-crossing shapes before submitting.'
                ),
            },
            'GeoJSONEnvelope': {
                'type': 'object',
                'required': ['geojson'],
                'properties': {
                    'geojson': {'$ref': '#/components/schemas/GeoJSON'},
                    'precision': {'$ref': '#/components/schemas/Precision'},
                    'mode': {'$ref': '#/components/schemas/CoverageMode'},
                },
            },
            'GeoJSONForm': {
                'type': 'object',
                'required': ['geojson'],
                'properties': {
                    'geojson': {
                        'type': 'string',
                        'description': 'GeoJSON encoded as a JSON string.',
                    },
                    'precision': {'$ref': '#/components/schemas/Precision'},
                    'mode': {'$ref': '#/components/schemas/CoverageMode'},
                },
            },
            'GeohashList': {
                'type': 'object',
                'required': ['geohashes'],
                'properties': {
                    'geohashes': {
                        'type': 'array',
                        'items': {'type': 'string'},
                    },
                },
            },
            'MultipolygonResponse': {
                'type': 'object',
                'required': ['geojson'],
                'properties': {
                    'geojson': {'$ref': '#/components/schemas/GeoJSON'},
                },
            },
            'Precision': {
                'type': 'integer',
                'minimum': 1,
                'maximum': 8,
                'default': 5,
            },
            'CoverageMode': {
                'type': 'string',
                'enum': ['center', 'inside', 'intersect'],
                'description': 'Explicit coverage rule. Maximum 50,000 emitted cells and 100,000 cell visits.',
            },
            'Error': {
                'type': 'object',
                'required': ['error'],
                'properties': {
                    'error': {
                        'type': 'object',
                        'required': ['code', 'message', 'status'],
                        'properties': {
                            'code': {'type': 'string'},
                            'message': {'type': 'string'},
                            'status': {'type': 'integer'},
                        },
                    },
                },
            },
        },
    },
}
