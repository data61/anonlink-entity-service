import logging.config
import os
from pathlib import Path
import structlog
import yaml

from entityservice.errors import InvalidConfiguration


def setup_logging(
    default_path='default_logging.yaml',
    env_key='LOG_CFG'
):
    """
    Setup logging configuration
    """
    path = os.getenv(env_key, Path(__file__).parent / default_path)
    try:
        with open(path, 'rt') as f:
            config = yaml.safe_load(f)
        logging.config.dictConfig(config)
    except yaml.YAMLError as e:
        raise InvalidConfiguration("Parsing YAML logging config failed") from e
    except FileNotFoundError as e:
        raise InvalidConfiguration(f"Logging config YAML file '{path}' doesn't exist.") from e

    # Configure Structlog wrapper for client use
    setup_structlog()
    logging.info("Loaded logging config from file")


def setup_structlog():
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt='iso'),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,

            # Uncomment ONE Renderer:
            #structlog.processors.KeyValueRenderer(),
            #structlog.processors.JSONRenderer(),
            structlog.dev.ConsoleRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


class StdErrFilter(logging.Filter):
    """
    Filter for the stderr stream
    Doesn't print records below ERROR to stderr to avoid dupes
    """
    def filter(self, record):
        return record.levelno >= logging.ERROR


class StdOutFilter(logging.Filter):
    """
    Filter for the stdout stream
    Doesn't print records at ERROR or above to stdout to avoid dupes
    """
    def filter(self, record):
        return record.levelno < logging.ERROR


def _str_to_level(lvl):
    """
    Convenience function to convert a log level string to the numeric rep
    """
    lvl = lvl.strip().lower()
    logging_levels = {
        'warning': logging.WARNING,
        'info': logging.INFO,
        'debug': logging.DEBUG,
        'critical': logging.CRITICAL,
        'error': logging.ERROR
    }

    if lvl in logging_levels:
        return logging_levels[lvl]
    else:
        raise ValueError(f"Unexpected logging level '{lvl}'")
