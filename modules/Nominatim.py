import requests

from geohash import decode as geohash_decode
from modules.City import City
from modules.Country import Country


class Nominatim:
    def __init__(self, url='http://nominatim.openstreetmap.org'):
        self.url = url

    def get_city_from_geohash(self, geohash):
        lat, lon = geohash_decode(geohash)

        return self.get_city_from_point(lat, lon)

    def get_country_from_point(self, lat, lon):
        payload = {
            'format': 'json',
            'accept-language': 'en_us,en,fr',
            'lat': lat,
            'lon': lon,
        }
        r = requests.get(self.url + '/reverse', params=payload)
        content = r.json()
        country_code = content['address']['country_code']
        country_name = content['address']['country']

        return self.get_country_from_name(country_name, country_code)

    def get_city_from_point(self, lat, lon):
        payload = {
            'format': 'json',
            'accept-language': 'en_us,en,fr',
            'lat': lat,
            'lon': lon,
        }
        r = requests.get(self.url + '/reverse', params=payload)
        content = r.json()

        county = ''

        if 'county' in content['address']:
            county = content['address']['county']

        if 'village' in content['address']:
            city_name = content['address']['village']
        elif 'town' in content['address']:
            city_name = content['address']['town']
        else:
            city_name = content['address']['city']

        print '-----------extracted-city-name--------------'
        print city_name

        country_code = content['address']['country_code']

        if county != '':
            return self.get_city_from_name(city_name, country_code, county)
        else:
            return self.get_city_from_name(city_name, country_code)

    def _get_city(self, cities):
        for city in cities:
            if city['geojson']['type'] == 'Point':
                continue

            if city['type'] == 'city':
                return city

            if city['type'] == 'administrative':
                return city

            if city['type'] == 'residential':
                return city

        return cities

    def get_country_from_name(self, country_name, country_code):
        payload = {
            'countrycodes': country_code,
            'country': country_name,
            'format': 'json',
            'limit': 10,
            'polygon_geojson': 1,
        }

        r = requests.get(self.url + '/search', params=payload)
        content = self._get_city(r.json())

        country = Country()
        country.set_place_id(content['place_id'])
        country.set_centroid(content['lat'], content['lon'])
        country.set_geometry({
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": content['geojson']
                }
            ]
        })

        return country

    def get_city_from_name(self, city_name, country_code, county_name=''):
        payload = {
            'city': city_name,
            'countrycodes': country_code,
            'format': 'json',
            'limit': 10,
            'polygon_geojson': 1,
        }

        if county_name != '':
            payload['county'] = county_name

        r = requests.get(self.url + '/search', params=payload)
        content = self._get_city(r.json())

        city = City()
        city.set_place_id(content['place_id'])
        city.set_centroid(content['lat'], content['lon'])
        city.set_geometry({
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": content['geojson']
                }
            ]
        })

        return city
