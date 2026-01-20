import os


BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _default_sqlite_uri(filename: str) -> str:
    path = os.path.join(BASE_DIR, filename)
    return f"sqlite:///{path.replace('\\\\', '/')}"


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-please-change-in-production'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_STORAGE = os.environ.get('JSON_STORAGE') or 'json_storage'
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or 'uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload
    REDIS_URL = os.environ.get('REDIS_URL')


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or _default_sqlite_uri('mydb.db')


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or _default_sqlite_uri('mydb.db')



config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
