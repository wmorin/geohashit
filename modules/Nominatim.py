import os
import threading
import time

import requests

import pygeohash
from modules.City import City
from modules.Country import Country


class NominatimError(Exception):
    pass


class NominatimLookupError(NominatimError):
    pass


class NominatimResponseError(NominatimError):
    pass


class Nominatim:
    _cache = {}
    _last_request_at = 0
    _lock = threading.Lock()

    def __init__(
        self,
        url=None,
        timeout=10,
        user_agent=None,
        min_interval=1,
        session=None,
    ):
        self.url = url or os.environ.get(
            'NOMINATIM_URL',
            'https://nominatim.openstreetmap.org',
        )
        self.timeout = timeout
        self.user_agent = user_agent or os.environ.get(
            'NOMINATIM_USER_AGENT',
            'geohashit/1.0 (https://github.com/wmorin/geohashit)',
        )
        self.min_interval = min_interval
        self.session = session or requests.Session()

    def _rate_limit(self):
        if self.min_interval <= 0:
            return

        with self._lock:
            now = time.monotonic()
            elapsed = now - self.__class__._last_request_at
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.__class__._last_request_at = time.monotonic()

    def _get_json(self, path, payload):
        cache_key = (path, tuple(sorted(payload.items())))
        if cache_key in self.__class__._cache:
            return self.__class__._cache[cache_key]

        self._rate_limit()
        try:
            response = self.session.get(
                self.url + path,
                params=payload,
                headers={'User-Agent': self.user_agent},
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()
        except requests.RequestException as error:
            raise NominatimError('nominatim request failed') from error
        except ValueError as error:
            raise NominatimResponseError('nominatim returned invalid JSON') from error

        self.__class__._cache[cache_key] = content
        return content

    def get_city_from_geohash(self, geohash):
        decoded = pygeohash.decode(geohash)
        lat = decoded.latitude
        lon = decoded.longitude

        return self.get_city_from_point(lat, lon)

    def get_country_from_point(self, lat, lon):
        payload = {
            'format': 'json',
            'accept-language': 'en_us,en,fr',
            'lat': lat,
            'lon': lon,
        }
        content = self._get_json('/reverse', payload)
        address = self._address_from_reverse(content)
        country_code = address['country_code']
        country_name = address['country']

        return self.get_country_from_name(country_name, country_code)

    def get_city_from_point(self, lat, lon):
        payload = {
            'format': 'json',
            'accept-language': 'en_us,en,fr',
            'lat': lat,
            'lon': lon,
        }
        content = self._get_json('/reverse', payload)
        address = self._address_from_reverse(content)
        county = address.get('county', '')
        city_name = self._city_name_from_address(address)
        country_code = address['country_code']

        if county != '':
            return self.get_city_from_name(city_name, country_code, county)
        else:
            return self.get_city_from_name(city_name, country_code)

    def _address_from_reverse(self, content):
        try:
            address = content['address']
            address['country_code']
            address['country']
        except (KeyError, TypeError):
            raise NominatimLookupError('nominatim reverse lookup did not return a place')

        return address

    def _city_name_from_address(self, address):
        for field in ('city', 'town', 'village', 'municipality', 'hamlet'):
            if field in address:
                return address[field]

        raise NominatimLookupError('nominatim reverse lookup did not return a city')

    def _get_city(self, cities):
        if not isinstance(cities, list):
            raise NominatimResponseError('nominatim search returned an unexpected response')

        for city in cities:
            geojson = city.get('geojson', {})
            if geojson.get('type') == 'Point':
                continue

            if city.get('type') == 'city':
                return city

            if city.get('type') == 'administrative':
                return city

            if city.get('type') == 'residential':
                return city

        raise NominatimLookupError('nominatim search did not return a polygon')

    def get_country_from_name(self, country_name, country_code):
        payload = {
            'countrycodes': country_code,
            'country': country_name,
            'format': 'json',
            'limit': 10,
            'polygon_geojson': 1,
        }

        content = self._get_city(self._get_json('/search', payload))

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

        content = self._get_city(self._get_json('/search', payload))

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
