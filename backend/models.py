# models.py - Data classes for organizing application data

class Ambulance:
    def __init__(self, id, driver, latitude, longitude, available):
        self.id = id
        self.driver = driver
        self.latitude = latitude
        self.longitude = longitude
        self.available = available

    def to_dict(self):
        return {
            "id": self.id,
            "driver": self.driver,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "available": self.available
        }


class Hospital:
    def __init__(self, id, name, latitude, longitude, beds):
        self.id = id
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.beds = beds

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "beds": self.beds
        }


class Patient:
    def __init__(self, id, name, latitude, longitude):
        self.id = id
        self.name = name
        self.latitude = latitude
        self.longitude = longitude

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude
        }


class Request:
    def __init__(self, id, patient, ambulance, hospital, status, timestamp):
        self.id = id
        self.patient = patient  # dict
        self.ambulance = ambulance  # ambulance id string
        self.hospital = hospital   # hospital id string
        self.status = status
        self.timestamp = timestamp

    def to_dict(self):
        return {
            "id": self.id,
            "patient": self.patient,
            "ambulance": self.ambulance,
            "hospital": self.hospital,
            "status": self.status,
            "timestamp": self.timestamp
        }
