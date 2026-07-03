from modules.Geohasher import Geohasher
from server import app


def test_server_imports_under_python3():
    assert app.name == 'server'


def test_geohash_to_multipolygon_returns_geojson_mapping():
    geojson = Geohasher().geohash_to_multipolygon(['u09tv'])

    assert geojson['type'] == 'MultiPolygon'
    assert len(geojson['coordinates']) == 1
