import base64
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///ai_voting.db")
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    FACE_DATA_KEY = os.environ.get("FACE_DATA_KEY")
    FACE_DISTANCE_THRESHOLD = os.environ.get("FACE_DISTANCE_THRESHOLD", "0.48")
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024
    LOGIN_ATTEMPT_WINDOW_MINUTES = 15
    LOGIN_ATTEMPT_LIMIT = 5


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    FACE_DATA_KEY = base64.urlsafe_b64encode(b"0" * 32).decode("ascii")
