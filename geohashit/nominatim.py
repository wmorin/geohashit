import os
import threading
import time

import pygeohash
import requests

from geohashit.place import Place


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
        return self.get_city_from_point(decoded.latitude, decoded.longitude)

    def get_country_from_point(self, lat, lon):
        content = self._get_json('/reverse', self._reverse_payload(lat, lon))
        address = self._address_from_reverse(content)
        return self.get_country_from_name(address['country'], address['country_code'])

    def get_city_from_point(self, lat, lon):
        content = self._get_json('/reverse', self._reverse_payload(lat, lon))
        address = self._address_from_reverse(content)
        city_name = self._city_name_from_address(address)
        country_code = address['country_code']
        county = address.get('county', '')

        if county:
            return self.get_city_from_name(city_name, country_code, county)
        return self.get_city_from_name(city_name, country_code)

    def get_country_from_name(self, country_name, country_code):
        payload = {
            'countrycodes': country_code,
            'country': country_name,
            'format': 'json',
            'limit': 10,
            'polygon_geojson': 1,
        }
        return self._place_from_search_result(self._get_place(self._get_json('/search', payload)))

    def get_city_from_name(self, city_name, country_code, county_name=''):
        payload = {
            'city': city_name,
            'countrycodes': country_code,
            'format': 'json',
            'limit': 10,
            'polygon_geojson': 1,
        }
        if county_name:
            payload['county'] = county_name

        return self._place_from_search_result(self._get_place(self._get_json('/search', payload)))

    def _reverse_payload(self, lat, lon):
        return {
            'format': 'json',
            'accept-language': 'en_us,en,fr',
            'lat': lat,
            'lon': lon,
        }

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

    def _get_place(self, places):
        if not isinstance(places, list):
            raise NominatimResponseError('nominatim search returned an unexpected response')

        for place in places:
            geojson = place.get('geojson', {})
            if geojson.get('type') == 'Point':
                continue
            if place.get('type') in ('city', 'administrative', 'residential'):
                return place

        raise NominatimLookupError('nominatim search did not return a polygon')

    def _place_from_search_result(self, content):
        return Place(
            place_id=content['place_id'],
            centroid={
                'lat': content['lat'],
                'lon': content['lon'],
            },
            geometry={
                'type': 'FeatureCollection',
                'features': [{
                    'type': 'Feature',
                    'properties': {},
                    'geometry': content['geojson'],
                }],
            },
        )
