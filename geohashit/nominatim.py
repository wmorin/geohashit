from collections import OrderedDict
import os
import threading
import time

import pygeohash
import requests

from geohashit.place import Place

_CACHE_MISS = object()


class NominatimError(Exception):
    pass


class NominatimLookupError(NominatimError):
    pass


class NominatimResponseError(NominatimError):
    pass


class NominatimCache:
    def __init__(self, entries, lock):
        self.entries = entries
        self.lock = lock

    def clear(self):
        with self.lock:
            self.entries.clear()

    def get(self, cache_key, max_size, ttl):
        if max_size <= 0 or ttl <= 0:
            return _CACHE_MISS

        with self.lock:
            cached = self.entries.get(cache_key)
            if cached is None:
                return _CACHE_MISS

            created_at, content = cached
            if time.monotonic() - created_at > ttl:
                del self.entries[cache_key]
                return _CACHE_MISS

            self.entries.move_to_end(cache_key)
            return content

    def set(self, cache_key, content, max_size, ttl):
        if max_size <= 0 or ttl <= 0:
            return

        with self.lock:
            self.entries[cache_key] = (time.monotonic(), content)
            self.entries.move_to_end(cache_key)
            while len(self.entries) > max_size:
                self.entries.popitem(last=False)


class NominatimRateLimiter:
    def __init__(self, lock):
        self.lock = lock
        self.last_request_at = 0

    def wait(self, min_interval):
        if min_interval <= 0:
            return

        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_request_at
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            self.last_request_at = time.monotonic()


class Nominatim:
    _cache = OrderedDict()
    _cache_max_size = 512
    _cache_ttl = 60 * 60
    _lock = threading.Lock()
    _cache_store = NominatimCache(_cache, _lock)
    _rate_limiter = NominatimRateLimiter(_lock)

    def __init__(
        self,
        url=None,
        timeout=10,
        user_agent=None,
        min_interval=1,
        cache_max_size=None,
        cache_ttl=None,
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
        self.cache_max_size = (
            self.__class__._cache_max_size
            if cache_max_size is None
            else cache_max_size
        )
        self.cache_ttl = self.__class__._cache_ttl if cache_ttl is None else cache_ttl
        self.session = session or requests.Session()

    @classmethod
    def clear_cache(cls):
        cls._cache_store.clear()

    def _rate_limit(self):
        self.__class__._rate_limiter.wait(self.min_interval)

    def _get_json(self, path, payload):
        cache_key = (self.url, path, tuple(sorted(payload.items())))
        cached = self._cache_get(cache_key)
        if cached is not _CACHE_MISS:
            return cached

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

        self._cache_set(cache_key, content)
        return content

    def _cache_get(self, cache_key):
        return self.__class__._cache_store.get(
            cache_key,
            self.cache_max_size,
            self.cache_ttl,
        )

    def _cache_set(self, cache_key, content):
        self.__class__._cache_store.set(
            cache_key,
            content,
            self.cache_max_size,
            self.cache_ttl,
        )

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
