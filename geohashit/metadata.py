API_VERSION = '0.1.2'
SERVICE_NAME = "Geohash'it"
SERVICE_DESCRIPTION = (
    'Convert places and GeoJSON shapes into geohash coverage polygons.'
)

API_ENDPOINTS = [
    {
        'path': '/multipolygons/point',
        'methods': ['GET'],
        'description': (
            'Resolve a city or country from a point and return geohash polygons.'
        ),
    },
    {
        'path': '/multipolygons/city',
        'methods': ['GET'],
        'description': 'Resolve a named city and return geohash polygons.',
    },
    {
        'path': '/multipolygons/geohash',
        'methods': ['GET'],
        'description': (
            'Resolve the city containing a geohash and return geohash polygons.'
        ),
    },
    {
        'path': '/geohashes/geojson',
        'methods': ['POST'],
        'description': 'Return geohashes covering a submitted GeoJSON shape.',
    },
    {
        'path': '/multipolygons/geojson',
        'methods': ['POST'],
        'description': 'Return geohash polygons for a submitted GeoJSON shape.',
    },
]
