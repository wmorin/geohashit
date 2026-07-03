import json

import pytest

from modules.Geohasher import Geohasher, _bbox
from modules.Nominatim import Nominatim, NominatimLookupError, NominatimResponseError
from server import app


def test_server_imports_under_python3():
    assert app.name == 'server'


def test_geohash_to_multipolygon_returns_geojson_mapping():
    geojson = Geohasher().geohash_to_multipolygon(['u09tv'])

    assert geojson['type'] == 'MultiPolygon'
    assert len(geojson['coordinates']) == 1


def test_point_route_rejects_invalid_latitude():
    response = app.test_client().get(
        '/multipolygon_from_point?lat=91&lon=2&type=city&precision=5'
    )

    assert response.status_code == 400
    assert response.get_json() == {'error': 'lat must be at most 90'}


def test_point_route_rejects_invalid_type():
    response = app.test_client().get(
        '/multipolygon_from_point?lat=48&lon=2&type=county&precision=5'
    )

    assert response.status_code == 400
    assert response.get_json() == {'error': 'type must be one of: city, country'}


def test_point_route_rejects_high_precision():
    response = app.test_client().get(
        '/multipolygon_from_point?lat=48&lon=2&type=city&precision=12'
    )

    assert response.status_code == 400
    assert response.get_json() == {'error': 'precision must be between 1 and 8'}


def test_geohash_route_rejects_invalid_geohash():
    response = app.test_client().get(
        '/multipolygon_from_geohash?geohash=!!!!&precision=5'
    )

    assert response.status_code == 400
    assert response.get_json() == {'error': 'geohash must be a valid geohash'}


def test_geojson_route_requires_geojson_form_field():
    response = app.test_client().post('/geohash_from_geojson', data={})

    assert response.status_code == 400
    assert response.get_json() == {'error': 'geojson is required'}


def test_geojson_route_rejects_malformed_json():
    response = app.test_client().post(
        '/geohash_from_geojson?precision=5',
        data={'geojson': '{bad'},
    )

    assert response.status_code == 400
    assert response.get_json() == {'error': 'geojson must be valid JSON'}


def test_geojson_route_rejects_invalid_geometry_type():
    response = app.test_client().post(
        '/geohash_from_geojson?precision=5',
        data={'geojson': '{"type":"Nope"}'},
    )

    assert response.status_code == 400
    assert response.get_json() == {'error': 'geojson contains invalid geometry'}


def geohash_feature(geohash):
    bounds = _bbox(geohash)
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

    def get_geometry(self):
        return self.geometry


class FakeNominatim:
    def __init__(self, geometry):
        self.geometry = geometry

    def get_city_from_name(self, city_name, country_code):
        return FakePlace(self.geometry)

    def get_city_from_point(self, lat, lon):
        return FakePlace(self.geometry)


class MissingPlaceNominatim:
    def get_city_from_name(self, city_name, country_code):
        raise NominatimLookupError('nominatim search did not return a polygon')


def test_feature_collection_geohashes_all_features():
    geohashes = Geohasher.geohash_geojson(feature_collection('u09tv', 'u09ty'), 5)

    assert set(geohashes) == {'u09tv', 'u09ty'}


def test_small_polygon_returns_representative_geohash_at_coarse_precision():
    geohashes = Geohasher.geohash_geojson(geohash_feature('u09tv'), 3)

    assert geohashes == ['u09']


def test_geohash_from_geojson_accepts_json_string():
    response = app.test_client().post(
        '/geohash_from_geojson?precision=5',
        data={'geojson': json.dumps(geohash_feature('u09tv'))},
    )

    assert response.status_code == 200
    assert response.get_json() == {'geohashes': ['u09tv']}


def test_geohash_from_geojson_accepts_point_geometry():
    response = app.test_client().post(
        '/geohash_from_geojson?precision=5',
        data={
            'geojson': json.dumps({
                'type': 'Point',
                'coordinates': [2.3522, 48.8566],
            }),
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {'geohashes': ['u09tv']}


def test_multipolygon_from_city_uses_instance_method(monkeypatch):
    geometry = feature_collection('u09tv')
    monkeypatch.setattr('server.Nominatim', lambda: FakeNominatim(geometry))

    response = app.test_client().get(
        '/multipolygon_from_city?city_name=Paris&country_code=fr&precision=5'
    )

    assert response.status_code == 200
    assert response.get_json()['geojson']['type'] == 'MultiPolygon'


def test_multipolygon_from_point_uses_validated_precision(monkeypatch):
    geometry = feature_collection('u09tv')
    monkeypatch.setattr('server.Nominatim', lambda: FakeNominatim(geometry))

    response = app.test_client().get(
        '/multipolygon_from_point?lat=48.8&lon=2.3&type=city&precision=5'
    )

    assert response.status_code == 200
    assert response.get_json()['geojson']['type'] == 'MultiPolygon'


def test_multipolygon_from_city_returns_json_404_for_missing_place(monkeypatch):
    monkeypatch.setattr('server.Nominatim', lambda: MissingPlaceNominatim())

    response = app.test_client().get(
        '/multipolygon_from_city?city_name=Atlantis&country_code=zz&precision=5'
    )

    assert response.status_code == 404
    assert response.get_json() == {'error': 'nominatim search did not return a polygon'}


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
    Nominatim._cache = {}
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
    Nominatim._cache = {}
    response = FakeResponse({'ok': True})
    session = FakeSession(response)
    nominatim = Nominatim(min_interval=0, session=session)

    nominatim._get_json('/reverse', {'lat': 1, 'lon': 2})
    nominatim._get_json('/reverse', {'lon': 2, 'lat': 1})

    assert len(session.calls) == 1


def test_nominatim_rejects_non_json_response():
    Nominatim._cache = {}
    response = FakeResponse(json_error=ValueError('not json'))
    session = FakeSession(response)
    nominatim = Nominatim(min_interval=0, session=session)

    with pytest.raises(NominatimResponseError) as error:
        nominatim._get_json('/reverse', {'lat': 1, 'lon': 2})

    assert str(error.value) == 'nominatim returned invalid JSON'


def test_nominatim_rejects_search_without_polygon():
    nominatim = Nominatim(min_interval=0)

    with pytest.raises(NominatimLookupError) as error:
        nominatim._get_city([{
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
