"""
WSGI entry point for production deployment with Gunicorn.
Usage: gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
"""

import os
import sys

ROOT_DIR = os.path.dirname(__file__)
BACKEND_DIR = os.path.join(ROOT_DIR, 'backend')

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

try:
    from backend.app import app
except ImportError:
    from app import app

if __name__ == "__main__":
    app.run()
