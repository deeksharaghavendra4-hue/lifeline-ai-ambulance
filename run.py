# run.py - Entry point to start the Ambulance AI application

import sys
import os

ROOT_DIR = os.path.dirname(__file__)
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

try:
    from backend.app import app
except ImportError:
    from app import app

if __name__ == "__main__":
    print("Starting Ambulance AI server at http://localhost:5000")
    print("  Patient Page      : http://localhost:5000/")
    print("  Driver Page       : http://localhost:5000/driver")
    print("  Hospital Dashboard: http://localhost:5000/hospital")
    print("  Health Check      : http://localhost:5000/health")
    app.run(debug=True, port=5000)
