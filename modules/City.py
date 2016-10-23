class City:
    def set_place_id(self, id):
        self.place_id = id

    def set_centroid(self, lat, lon):
        self.centroid = {
            'lat': lat,
            'lon': lon,
        }

    def set_geometry(self, geometry):
        self.geometry = geometry

    def get_geometry(self):
        return self.geometry
