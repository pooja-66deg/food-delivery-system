"""This service's auth, built from its own signing secret.

One instance, constructed at import time, so the router's guards are ordinary
dependencies. Nothing here talks to the users service — see shared/identity.py.
"""

from app.config import settings
from shared.identity import JWTAuth

auth = JWTAuth(settings.jwt_secret_key, settings.jwt_algorithm)
