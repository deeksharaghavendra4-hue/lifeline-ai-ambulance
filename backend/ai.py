# ai.py - AI logic for ambulance dispatch using distance-based calculations

import math


def _haversine(lat1, lon1, lat2, lon2):
    """Calculate straight-line distance in km between two coordinates."""
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def find_best_ambulance(patient_lat, patient_lon, ambulances):
    """Return the nearest available ambulance to the patient."""
    available = [a for a in ambulances if a.get("available")]
    if not available:
        return None
    return min(available, key=lambda a: _haversine(patient_lat, patient_lon, a["latitude"], a["longitude"]))


def calculate_eta(ambulance, patient_lat, patient_lon):
    """Estimate arrival time in minutes assuming average speed of 60 km/h."""
    if not ambulance:
        return None
    distance_km = _haversine(ambulance["latitude"], ambulance["longitude"], patient_lat, patient_lon)
    speed_kmh = 60
    eta_minutes = round((distance_km / speed_kmh) * 60)
    return max(eta_minutes, 1)  # at least 1 minute


def recommend_hospital(patient_lat, patient_lon, hospitals):
    """Return the nearest hospital with available beds."""
    with_beds = [h for h in hospitals if h.get("beds", 0) > 0]
    if not with_beds:
        return None
    return min(with_beds, key=lambda h: _haversine(patient_lat, patient_lon, h["latitude"], h["longitude"]))
