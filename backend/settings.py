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

    LOGFILE = os.environ.get("LOGFILE", 'entity-service.log')

    DATABASE_SERVER = os.environ.get('DATABASE_SERVER', 'db')
    DATABASE = os.environ.get('DATABASE', 'postgres')
    DATABASE_USER = os.environ.get('DATABASE_USER', 'postgres')
    DATABASE_PASSWORD = os.environ.get('DATABASE_PASSWORD', '')

    BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')


class ProductionConfig(Config):
    DEBUG = False


class DevelopmentConfig(Config):
    DEBUG = True


