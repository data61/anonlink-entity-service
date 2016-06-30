#!/usr/bin/env python3.4
"""
Config shared between the application backend and the celery workers.
"""
import os


class Config(object):
    """
    Hard coded default configuration which can be overwritten with environment variables
    """

    DEBUG = os.environ.get("DEBUG", "false") == "true"

    LOGFILE = os.environ.get("LOGFILE", None)

    DATABASE_SERVER = os.environ.get('DATABASE_SERVER', 'db')
    DATABASE = os.environ.get('DATABASE', 'postgres')
    DATABASE_USER = os.environ.get('DATABASE_USER', 'postgres')
    DATABASE_PASSWORD = os.environ.get('DATABASE_PASSWORD', '')

    BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
    CELERY_RESULT_BACKEND = BROKER_URL#os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')

    ENCRYPTION_CHUNK_SIZE = int(os.environ.get('ENCRYPTION_CHUNK_SIZE', '100'))

    # Matches that have more than this number of entities will use the
    # faster greedy solver
    GREEDY_SIZE = int(os.environ.get('GREEDY_SIZE', '1000'))

    # Number of entities to match per chunk
    GREEDY_CHUNK_SIZE = int(os.environ.get('GREEDY_CHUNK_SIZE', '1000'))

    ENTITY_MATCH_THRESHOLD = float(os.environ.get('ENTITY_MATCH_THRESHOLD', '0.95'))


class ProductionConfig(Config):
    DEBUG = False


class DevelopmentConfig(Config):
    DEBUG = True


