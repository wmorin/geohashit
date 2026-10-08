import json

import pytest
from geohashit.json_validation import MAX_JSON_DEPTH, validate_json_depth
from shapely.geometry import box, mapping, shape

from geohashit.app import app, create_app
from geohashit.cover import GeohashBudgetError, geohash_bbox, geojson_to_geohashes, geojson_to_shape
from tests.some_test import FakeNominatim, geohash_feature


def corner_polygon():
    bounds = geohash_bbox('u09tv')
    return mapping(box(
        bounds['w'] + 0.001, bounds['s'] + 0.001,
        bounds['w'] + 0.002, bounds['s'] + 0.002,
    ))


@pytest.mark.parametrize('mode, expected', [
    ('inside', []), ('center', []), ('intersect', ['u09tv']),
])
def test_explicit_mode_preserves_small_polygon_semantics(mode, expected):
    assert geojson_to_geohashes(corner_polygon(), 5, mode=mode) == expected
    assert geojson_to_geohashes(corner_polygon(), 5) == ['u09tv']


@pytest.mark.parametrize('source', ['query', 'form', 'envelope'])
def test_api_accepts_explicit_mode_from_all_supported_sources(source):
    kwargs = {}
    endpoint = '/geohashes/geojson'
    if source == 'query':
        endpoint += '?precision=5&mode=inside'
        kwargs['json'] = corner_polygon()
    elif source == 'form':
        kwargs['data'] = {'geojson': json.dumps(corner_polygon()), 'precision': 5, 'mode': 'inside'}
    else:
        kwargs['json'] = {'geojson': corner_polygon(), 'precision': 5, 'mode': 'inside'}
    response = app.test_client().post(endpoint, **kwargs)
    assert response.status_code == 200
    assert response.get_json() == {'geohashes': []}


def test_query_mode_overrides_envelope():
    response = app.test_client().post('/geohashes/geojson?mode=intersect', json={
        'geojson': corner_polygon(), 'precision': 5, 'mode': 'inside',
    })
    assert response.get_json() == {'geohashes': ['u09tv']}


@pytest.mark.parametrize('mode', ['outside', '', [], {}, True, 1, None])
def test_bad_mode_envelopes_return_validation_errors(mode):
    response = app.test_client().post('/geohashes/geojson', json={
        'geojson': corner_polygon(), 'mode': mode,
    })
    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'validation_error'


@pytest.mark.parametrize('precision', [[], {}, True, 1.2, None, '5.5'])
def test_bad_precision_envelopes_return_validation_errors(precision):
    response = app.test_client().post('/geohashes/geojson', json={
        'geojson': corner_polygon(), 'precision': precision,
    })
    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'validation_error'


@pytest.mark.parametrize('endpoint', [
    '/multipolygons/geohash?geohash=u09tv&precision=5',
    '/multipolygons/city?city_name=Paris&country_code=fr&precision=5',
    '/multipolygons/point?lat=48.8&lon=2.3&type=city&precision=5',
])
def test_lookup_endpoints_apply_explicit_mode(endpoint):
    client = create_app(nominatim_factory=lambda: FakeNominatim(corner_polygon())).test_client()
    response = client.get(endpoint + '&mode=inside')
    assert response.status_code == 200
    assert response.get_json()['geojson']['coordinates'] == []


def test_multipolygon_geojson_applies_mode():
    response = app.test_client().post('/multipolygons/geojson?mode=inside', json=corner_polygon())
    assert response.status_code == 200
    assert response.get_json()['geojson']['coordinates'] == []


@pytest.mark.parametrize('geometry', [
    {'type': 'Point', 'coordinates': [181, 0]},
    {'type': 'Point', 'coordinates': [0, -91]},
    {'type': 'Point', 'coordinates': [float('nan'), 0]},
    {'type': 'Point', 'coordinates': [0, float('inf')]},
    {'type': 'Point', 'coordinates': [True, 0]},
    {'type': 'Point', 'coordinates': ['2', 48]},
    {'type': [], 'coordinates': []},
    {'type': 'Polygon', 'coordinates': [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]},
    {'type': 'FeatureCollection', 'features': [None]},
    {'type': 'MultiPolygon', 'coordinates': [[[1]]]},
])
def test_invalid_geometry_never_returns_server_error(geometry):
    response = app.test_client().post('/geohashes/geojson', json=geometry)
    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'validation_error'


@pytest.mark.parametrize('value', ['nan', 'inf', '-inf'])
def test_point_lookup_rejects_nonfinite_latitude_before_upstream(value):
    response = app.test_client().get('/multipolygons/point?lat=%s&lon=2&type=city&precision=5' % value)
    assert response.status_code == 400
    assert response.get_json()['error']['message'] == 'lat must be a finite number'


def test_many_coordinates_are_rejected_before_geometry_processing():
    geometry = {'type': 'MultiPoint', 'coordinates': [[0, 0]] * 10001}
    with pytest.raises(ValueError, match='maximum of 10000 coordinates'):
        geojson_to_geohashes(geometry, 5)


def test_cell_visit_budget_covers_work_even_when_no_cells_emit():
    geometry = {'type': 'LineString', 'coordinates': [[-170, 0.0001], [170, 0.0001]]}
    with pytest.raises(GeohashBudgetError, match='maximum of 100 cell visits'):
        geojson_to_geohashes(geometry, 8, mode='inside', max_cell_visits=100)


def test_hole_excludes_cell_from_center_and_inside_cover():
    outer = shape(geohash_feature('u09tv')['geometry'])
    hole = box(2.351, 48.844, 2.352, 48.845)
    polygon = mapping(outer.difference(hole))
    inside = geojson_to_geohashes(polygon, 6, mode='inside')
    for geohash in inside:
        bounds = geohash_bbox(geohash)
        cell = box(bounds['w'], bounds['s'], bounds['e'], bounds['n'])
        assert shape(polygon).contains(cell)
        assert not hole.intersects(cell)


def test_empty_polygon_stays_empty_in_every_mode():
    for mode in (None, 'center', 'inside', 'intersect'):
        assert geojson_to_geohashes({'type': 'Polygon', 'coordinates': []}, 5, mode=mode) == []


def test_openapi_describes_mode_everywhere_and_envelope_fields():
    spec = app.test_client().get('/openapi.json').get_json()
    for endpoint in ('/geohashes/geojson', '/multipolygons/geojson'):
        assert 'mode' in [parameter['name'] for parameter in spec['paths'][endpoint]['post']['parameters']]
    for schema in ('GeoJSONEnvelope', 'GeoJSONForm'):
        assert 'mode' in spec['components']['schemas'][schema]['properties']


@pytest.mark.parametrize('source', ['form', 'body'])
def test_deeply_nested_json_is_validation_error(source):
    data = '[' * (MAX_JSON_DEPTH + 1) + '0' + ']' * (MAX_JSON_DEPTH + 1)
    kwargs = {'data': {'geojson': data}} if source == 'form' else {
        'data': data, 'content_type': 'application/json',
    }
    response = app.test_client().post('/geohashes/geojson', **kwargs)
    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'validation_error'
    assert response.get_json()['error']['message'] == 'JSON nesting exceeds the maximum depth of 64'


def test_deeply_nested_json_on_get_argument_path_is_validation_error():
    data = '[' * (MAX_JSON_DEPTH + 1) + '0' + ']' * (MAX_JSON_DEPTH + 1)
    response = app.test_client().get(
        '/multipolygons/city?city_name=Paris&country_code=fr',
        data=data, content_type='application/json',
    )
    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'validation_error'
    assert response.get_json()['error']['message'] == 'JSON nesting exceeds the maximum depth of 64'


def test_deeply_nested_json_mode_argument_path_is_validation_error():
    data = '[' * (MAX_JSON_DEPTH + 1) + '0' + ']' * (MAX_JSON_DEPTH + 1)
    response = app.test_client().get(
        '/multipolygons/city?city_name=Paris&country_code=fr&precision=5',
        data=data, content_type='application/json',
    )
    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'validation_error'
    assert response.get_json()['error']['message'] == 'JSON nesting exceeds the maximum depth of 64'


@pytest.mark.parametrize('container', ['array', 'object'])
def test_json_nesting_limit_has_an_explicit_inclusive_boundary(container):
    value = 'literal brackets [] {} and escaped quote " do not count'
    for _ in range(MAX_JSON_DEPTH):
        value = [value] if container == 'array' else {'value': value}
    validate_json_depth(value)
    with pytest.raises(ValueError, match='maximum depth of 64'):
        validate_json_depth([value])


def crossing_strips(count=300):
    # 600 simple rectangles use only 3,000 source positions. Their full union
    # would create almost 90,000 holes and hundreds of thousands of positions.
    polygons = [mapping(box(0, index / 30, 10, index / 30 + 0.005)) for index in range(count)]
    polygons += [mapping(box(index / 30, 0, index / 30 + 0.005, 10)) for index in range(count)]
    return {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {}, 'geometry': polygon} for polygon in polygons
    ]}


def test_crossing_strips_reject_before_unbounded_normalized_expansion(monkeypatch):
    import shapely
    from shapely.geometry.base import BaseGeometry

    original_union = BaseGeometry.union
    output_sizes = []
    def measured_union(self, other, *args, **kwargs):
        result = original_union(self, other, *args, **kwargs)
        output_sizes.append(int(shapely.get_num_coordinates(result)))
        return result
    monkeypatch.setattr(BaseGeometry, 'union', measured_union)
    with pytest.raises(GeohashBudgetError, match='normalized geometry exceeds'):
        geojson_to_shape(crossing_strips())
    assert len(output_sizes) < 320  # Reject after a few crossing vertical strips.
    assert max(output_sizes) < 20000


def test_crossing_strips_api_returns_actionable_validation_error():
    response = app.test_client().post('/geohashes/geojson?mode=inside', json=crossing_strips())
    assert response.status_code == 400
    assert 'normalized geometry exceeds' in response.get_json()['error']['message']


def test_multipolygon_component_budget_precedes_geos_processing(monkeypatch):
    import shapely.geometry
    monkeypatch.setattr(shapely.geometry, 'shape', lambda data: pytest.fail('GEOS should not construct this geometry'))
    geometry = {'type': 'MultiPolygon', 'coordinates': [
        mapping(box(index / 100, 0, index / 100 + 0.001, 0.001))['coordinates']
        for index in range(1001)
    ]}
    with pytest.raises(GeohashBudgetError, match='maximum of 1000 geometry components'):
        geojson_to_shape(geometry)


def test_one_complex_overlay_is_rejected_before_geos_union(monkeypatch):
    from shapely.geometry.base import BaseGeometry
    # Dense but valid collinear edges along rectangles: the conservative bound
    # rejects a single potentially expensive overlay before calling GEOS union.
    ring = [[index / 100, 0] for index in range(100)]
    ring += [[1, index / 100] for index in range(100)]
    ring += [[1 - index / 100, 1] for index in range(100)]
    ring += [[0, 1 - index / 100] for index in range(100)]
    ring.append(ring[0])
    geometry = {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [ring]}},
        {'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [
            [[x + 0.1, y] for x, y in ring],
        ]}},
    ]}
    monkeypatch.setattr(BaseGeometry, 'union', lambda self, other: pytest.fail('GEOS union must not run'))
    with pytest.raises(GeohashBudgetError, match='potential edge pairs'):
        geojson_to_shape(geometry)
