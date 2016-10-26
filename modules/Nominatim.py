import requests

from geohash import decode as geohash_decode
from modules.City import City


class Nominatim:
    def __init__(self, url='http://nominatim.openstreetmap.org'):
        self.url = url

    def get_city_from_geohash(self, geohash):
        lat, lon = geohash_decode(geohash)

        return self.get_city_from_point(lat, lon)

    def get_city_from_point(self, lat, lon):
        payload = {
            'format': 'json',
            'accept-language': 'en_us,en,fr',
            'lat': lat,
            'lon': lon,
        }
        r = requests.get(self.url + '/reverse', params=payload)
        content = r.json()

        if 'village' in content['address']:
            city_name = content['address']['village']
        else:
            city_name = content['address']['city']

        country_code = content['address']['country_code']

        return self.get_city_from_name(city_name, country_code)

    def get_city_from_name(self, city_name, country_code):
        payload = {
            'city': city_name,
            'countrycodes': country_code,
            'format': 'json',
            'limit': 1,
            'polygon_geojson': 1,
        }

        r = requests.get(self.url + '/search', params=payload)
        content = r.json()

        city = City()
        city.set_place_id(content[0]['place_id'])
        city.set_centroid(content[0]['lat'], content[0]['lon'])
        city.set_geometry({
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": content[0]['geojson']
                }
            ]
        })

        return city
