from dataclasses import dataclass


@dataclass(frozen=True)
class Place:
    place_id: int
    centroid: dict
    geometry: dict
