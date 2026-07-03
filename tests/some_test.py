import json

from modules.Geohasher import Geohasher, _bbox
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


def test_geojson_route_requires_geojson_form_field():
    response = app.test_client().post('/geohash_from_geojson', data={})

    assert response.status_code == 400
    assert response.get_json() == {'error': 'geojson is required'}


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


def test_feature_collection_geohashes_all_features():
    geohashes = Geohasher.geohash_geojson(feature_collection('u09tv', 'u09ty'), 5)

    assert set(geohashes) == {'u09tv', 'u09ty'}


def test_geohash_from_geojson_accepts_json_string():
    response = app.test_client().post(
        '/geohash_from_geojson?precision=5',
        data={'geojson': json.dumps(geohash_feature('u09tv'))},
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
