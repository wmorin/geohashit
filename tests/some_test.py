import json
import time

import pytest

from geohashit.cover import (
    GeohashBudgetError,
    geohash_bbox,
    geohashes_to_multipolygon,
    geojson_to_geohashes,
)
from geohashit.nominatim import (
    Nominatim,
    NominatimLookupError,
    NominatimResponseError,
)
from server import app


def assert_error(response, status, code, message):
    assert response.status_code == status
    assert response.is_json
    assert response.get_json() == {
        'error': {
            'code': code,
            'message': message,
            'status': status,
        },
    }


def test_server_imports_under_python3():
    assert app.name == 'geohashit'


def test_service_index_lists_api_endpoints():
    response = app.test_client().get('/')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['name'] == "Geohash'it"
    assert payload['status'] == 'ok'
    assert [endpoint['path'] for endpoint in payload['endpoints']] == [
        '/multipolygons/point',
        '/multipolygons/city',
        '/multipolygons/geohash',
        '/geohashes/geojson',
        '/multipolygons/geojson',
    ]


def test_health_route_returns_json_status():
    response = app.test_client().get('/health')

    assert response.status_code == 200
    assert response.get_json() == {'status': 'ok'}


def test_openapi_route_describes_current_api_contract():
    response = app.test_client().get('/openapi.json')

    assert response.status_code == 200
    spec = response.get_json()
    assert spec['openapi'] == '3.2.0'
    assert spec['info']['title'] == "Geohash'it API"
    assert set(spec['paths']) == {
        '/',
        '/health',
        '/openapi.json',
        '/multipolygons/point',
        '/multipolygons/city',
        '/multipolygons/geohash',
        '/geohashes/geojson',
        '/multipolygons/geojson',
    }
    assert 'get' in spec['paths']['/multipolygons/point']
    assert 'post' in spec['paths']['/geohashes/geojson']
    assert spec['components']['schemas']['Error']['required'] == ['error']
    assert (
        spec['components']['schemas']['Precision']['maximum']
        == 8
    )


def test_unknown_route_returns_json_404():
    response = app.test_client().get('/does-not-exist')

    assert_error(
        response,
        404,
        'not_found',
        (
            'The requested URL was not found on the server. If you entered the URL '
            'manually please check your spelling and try again.'
        ),
    )


def test_wrong_method_returns_json_405():
    response = app.test_client().get('/geohashes/geojson')

    assert_error(
        response,
        405,
        'method_not_allowed',
        'The method is not allowed for the requested URL.',
    )


def test_geohash_to_multipolygon_returns_geojson_mapping():
    geojson = geohashes_to_multipolygon(['u09tv'])

    assert geojson['type'] == 'MultiPolygon'
    assert len(geojson['coordinates']) == 1


def test_point_route_rejects_invalid_latitude():
    response = app.test_client().get(
        '/multipolygons/point?lat=91&lon=2&type=city&precision=5'
    )

    assert_error(response, 400, 'validation_error', 'lat must be at most 90')


def test_point_route_rejects_invalid_type():
    response = app.test_client().get(
        '/multipolygons/point?lat=48&lon=2&type=county&precision=5'
    )

    assert_error(
        response,
        400,
        'validation_error',
        'type must be one of: city, country',
    )


def test_point_route_rejects_high_precision():
    response = app.test_client().get(
        '/multipolygons/point?lat=48&lon=2&type=city&precision=12'
    )

    assert_error(
        response,
        400,
        'validation_error',
        'precision must be between 1 and 8',
    )


def test_geohash_route_rejects_invalid_geohash():
    response = app.test_client().get(
        '/multipolygons/geohash?geohash=!!!!&precision=5'
    )

    assert_error(
        response,
        400,
        'validation_error',
        'geohash must be a valid geohash',
    )


def test_geojson_route_requires_geojson_form_field():
    response = app.test_client().post('/geohashes/geojson', data={})

    assert_error(response, 400, 'validation_error', 'geojson is required')


def test_geojson_route_rejects_malformed_json():
    response = app.test_client().post(
        '/geohashes/geojson?precision=5',
        data={'geojson': '{bad'},
    )

    assert_error(response, 400, 'validation_error', 'geojson must be valid JSON')


def test_geojson_route_rejects_invalid_geometry_type():
    response = app.test_client().post(
        '/geohashes/geojson?precision=5',
        data={'geojson': '{"type":"Nope"}'},
    )

    assert_error(
        response,
        400,
        'validation_error',
        'geojson contains invalid geometry',
    )


def geohash_feature(geohash):
    bounds = geohash_bbox(geohash)
    pad = 0.00001
    return {
        'type': 'Feature',
        'properties': {},
        'geometry': {
            'type': 'Polygon',
            'coordinates': [[
                [bounds['w'] - pad, bounds['s'] - pad],
                [bounds['e'] + pad, bounds['s'] - pad],
                [bounds['e'] + pad, bounds['n'] + pad],
                [bounds['w'] - pad, bounds['n'] + pad],
                [bounds['w'] - pad, bounds['s'] - pad],
            ]],
        },
    }


def feature_collection(*geohashes):
    return {
        'type': 'FeatureCollection',
        'features': [geohash_feature(geohash) for geohash in geohashes],
    }


class FakePlace:
    def __init__(self, geometry):
        self.geometry = geometry


class FakeNominatim:
    def __init__(self, geometry):
        self.geometry = geometry

    def get_city_from_name(self, city_name, country_code):
        return FakePlace(self.geometry)

    def get_city_from_point(self, lat, lon):
        return FakePlace(self.geometry)

    def get_country_from_point(self, lat, lon):
        return FakePlace(self.geometry)


class MissingPlaceNominatim:
    def get_city_from_name(self, city_name, country_code):
        raise NominatimLookupError('nominatim search did not return a polygon')


def test_feature_collection_geohashes_all_features():
    geohashes = geojson_to_geohashes(feature_collection('u09tv', 'u09ty'), 5)

    assert set(geohashes) == {'u09tv', 'u09ty'}


def test_geojson_to_geohashes_rejects_over_budget_coverages():
    with pytest.raises(GeohashBudgetError) as error:
        geojson_to_geohashes(
            feature_collection('u09tv', 'u09ty'),
            5,
            max_geohashes=1,
        )

    assert str(error.value) == 'geohash coverage exceeds the maximum of 1 cells'


def test_small_polygon_returns_representative_geohash_at_coarse_precision():
    geohashes = geojson_to_geohashes(geohash_feature('u09tv'), 3)

    assert geohashes == ['u09']


def test_geohash_covering_small_polygon_performance_guard():
    start = time.perf_counter()

    geohashes = geojson_to_geohashes(geohash_feature('u09tv'), 5)

    assert geohashes == ['u09tv']
    assert time.perf_counter() - start < 0.25


def test_geojson_geohashes_accepts_json_string():
    response = app.test_client().post(
        '/geohashes/geojson?precision=5',
        data={'geojson': json.dumps(geohash_feature('u09tv'))},
    )

    assert response.status_code == 200
    assert response.get_json() == {'geohashes': ['u09tv']}


def test_geojson_geohashes_accepts_point_geometry():
    response = app.test_client().post(
        '/geohashes/geojson?precision=5',
        data={
            'geojson': json.dumps({
                'type': 'Point',
                'coordinates': [2.3522, 48.8566],
            }),
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {'geohashes': ['u09tv']}


def test_geojson_geohashes_accepts_json_body():
    response = app.test_client().post(
        '/geohashes/geojson?precision=5',
        json={
            'type': 'Point',
            'coordinates': [2.3522, 48.8566],
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {'geohashes': ['u09tv']}


def test_geojson_geohashes_accepts_json_envelope_with_precision():
    response = app.test_client().post(
        '/geohashes/geojson',
        json={
            'geojson': {
                'type': 'Point',
                'coordinates': [2.3522, 48.8566],
            },
            'precision': 3,
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {'geohashes': ['u09']}


def test_geojson_geohashes_accepts_form_precision():
    response = app.test_client().post(
        '/geohashes/geojson',
        data={
            'geojson': json.dumps({
                'type': 'Point',
                'coordinates': [2.3522, 48.8566],
            }),
            'precision': 3,
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {'geohashes': ['u09']}


def test_geojson_route_returns_validation_error_for_over_budget_coverages(monkeypatch):
    def over_budget(json_data, precision):
        raise GeohashBudgetError('geohash coverage exceeds the maximum of 50000 cells')

    monkeypatch.setattr('geohashit.app.geojson_to_geohashes', over_budget)

    response = app.test_client().post(
        '/geohashes/geojson?precision=5',
        data={'geojson': json.dumps(geohash_feature('u09tv'))},
    )

    assert_error(
        response,
        400,
        'validation_error',
        'geohash coverage exceeds the maximum of 50000 cells',
    )


def test_city_multipolygon_uses_instance_method(monkeypatch):
    geometry = feature_collection('u09tv')
    monkeypatch.setattr('geohashit.app.Nominatim', lambda: FakeNominatim(geometry))

    response = app.test_client().get(
        '/multipolygons/city?city_name=Paris&country_code=fr&precision=5'
    )

    assert response.status_code == 200
    assert response.get_json()['geojson']['type'] == 'MultiPolygon'


def test_point_multipolygon_uses_validated_precision(monkeypatch):
    geometry = feature_collection('u09tv')
    monkeypatch.setattr('geohashit.app.Nominatim', lambda: FakeNominatim(geometry))

    response = app.test_client().get(
        '/multipolygons/point?lat=48.8&lon=2.3&type=city&precision=5'
    )

    assert response.status_code == 200
    assert response.get_json()['geojson']['type'] == 'MultiPolygon'


def test_point_multipolygon_handles_country_type(monkeypatch):
    geometry = feature_collection('u09tv')
    monkeypatch.setattr('geohashit.app.Nominatim', lambda: FakeNominatim(geometry))

    response = app.test_client().get(
        '/multipolygons/point?lat=48.8&lon=2.3&type=country&precision=5'
    )

    assert response.status_code == 200
    assert response.get_json()['geojson']['type'] == 'MultiPolygon'


def test_removed_country_point_route_returns_json_404():
    response = app.test_client().get(
        '/multipolygon_country_from_point?lat=48.8&lon=2.3&precision=5'
    )

    assert_error(
        response,
        404,
        'not_found',
        (
            'The requested URL was not found on the server. If you entered the URL '
            'manually please check your spelling and try again.'
        ),
    )


def test_city_multipolygon_returns_json_404_for_missing_place(monkeypatch):
    monkeypatch.setattr('geohashit.app.Nominatim', lambda: MissingPlaceNominatim())

    response = app.test_client().get(
        '/multipolygons/city?city_name=Atlantis&country_code=zz&precision=5'
    )

    assert_error(
        response,
        404,
        'place_not_found',
        'nominatim search did not return a polygon',
    )


class FakeResponse:
    def __init__(self, payload=None, json_error=None):
        self.payload = payload
        self.json_error = json_error
        self.raise_for_status_called = False

    def raise_for_status(self):
        self.raise_for_status_called = True

    def json(self):
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, params, headers, timeout):
        self.calls.append({
            'url': url,
            'params': params,
            'headers': headers,
            'timeout': timeout,
        })
        return self.response


def test_nominatim_defaults_to_https():
    assert Nominatim().url == 'https://nominatim.openstreetmap.org'


def test_nominatim_sets_user_agent_timeout_and_checks_status():
    Nominatim.clear_cache()
    response = FakeResponse({'ok': True})
    session = FakeSession(response)
    nominatim = Nominatim(
        timeout=3,
        user_agent='test-agent',
        min_interval=0,
        session=session,
    )

    assert nominatim._get_json('/reverse', {'lat': 1, 'lon': 2}) == {'ok': True}

    assert session.calls == [{
        'url': 'https://nominatim.openstreetmap.org/reverse',
        'params': {'lat': 1, 'lon': 2},
        'headers': {'User-Agent': 'test-agent'},
        'timeout': 3,
    }]
    assert response.raise_for_status_called is True


def test_nominatim_caches_identical_requests():
    Nominatim.clear_cache()
    response = FakeResponse({'ok': True})
    session = FakeSession(response)
    nominatim = Nominatim(min_interval=0, session=session)

    nominatim._get_json('/reverse', {'lat': 1, 'lon': 2})
    nominatim._get_json('/reverse', {'lon': 2, 'lat': 1})

    assert len(session.calls) == 1


def test_nominatim_cache_evicts_oldest_request():
    Nominatim.clear_cache()
    response = FakeResponse({'ok': True})
    session = FakeSession(response)
    nominatim = Nominatim(min_interval=0, session=session, cache_max_size=2)

    nominatim._get_json('/reverse', {'lat': 1})
    nominatim._get_json('/reverse', {'lat': 2})
    nominatim._get_json('/reverse', {'lat': 3})
    nominatim._get_json('/reverse', {'lat': 1})

    assert len(session.calls) == 4
    assert len(Nominatim._cache) == 2


def test_nominatim_cache_is_scoped_by_base_url():
    Nominatim.clear_cache()
    first_session = FakeSession(FakeResponse({'name': 'first'}))
    second_session = FakeSession(FakeResponse({'name': 'second'}))
    first = Nominatim(
        url='https://first.example.com',
        min_interval=0,
        session=first_session,
    )
    second = Nominatim(
        url='https://second.example.com',
        min_interval=0,
        session=second_session,
    )

    assert first._get_json('/reverse', {'lat': 1}) == {'name': 'first'}
    assert second._get_json('/reverse', {'lat': 1}) == {'name': 'second'}

    assert len(first_session.calls) == 1
    assert len(second_session.calls) == 1


def test_nominatim_cache_can_be_disabled():
    Nominatim.clear_cache()
    response = FakeResponse({'ok': True})
    session = FakeSession(response)
    nominatim = Nominatim(
        min_interval=0,
        session=session,
        cache_max_size=0,
    )

    nominatim._get_json('/reverse', {'lat': 1})
    nominatim._get_json('/reverse', {'lat': 1})

    assert len(session.calls) == 2
    assert len(Nominatim._cache) == 0


def test_nominatim_rejects_non_json_response():
    Nominatim.clear_cache()
    response = FakeResponse(json_error=ValueError('not json'))
    session = FakeSession(response)
    nominatim = Nominatim(min_interval=0, session=session)

    with pytest.raises(NominatimResponseError) as error:
        nominatim._get_json('/reverse', {'lat': 1, 'lon': 2})

    assert str(error.value) == 'nominatim returned invalid JSON'


def test_nominatim_rejects_search_without_polygon():
    nominatim = Nominatim(min_interval=0)

    with pytest.raises(NominatimLookupError) as error:
        nominatim._get_place([{
            'type': 'city',
            'geojson': {'type': 'Point'},
        }])

    assert str(error.value) == 'nominatim search did not return a polygon'


def test_nominatim_rejects_reverse_without_city():
    nominatim = Nominatim(min_interval=0)

    with pytest.raises(NominatimLookupError) as error:
        nominatim._city_name_from_address({
            'country': 'France',
            'country_code': 'fr',
        })

    assert str(error.value) == 'nominatim reverse lookup did not return a city'
