from modules.Geohasher import Geohasher
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
