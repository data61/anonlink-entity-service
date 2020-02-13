import logging.config
from pathlib import Path

import structlog

from entityservice.utils import load_yaml_config
from entityservice.settings import Config as config


def setup_logging(default_path='default_logging.yaml'):
    """
    Setup logging configuration
    """
    if config.LOG_CONFIG_FILENAME is not None:
        path = Path(config.LOG_CONFIG_FILENAME)
    else:
        path = Path(__file__).parent / default_path

    loggingconfig = load_yaml_config(path)
    logging.config.dictConfig(loggingconfig)

    # Configure Structlog wrapper for client use
    setup_structlog()
    logging.debug(f"Loaded logging config from file: {path}")


def setup_structlog():
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            #structlog.processors.TimeStamper(fmt='iso'),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,

            # Uncomment ONE Renderer:
            #structlog.processors.KeyValueRenderer(),
            #structlog.processors.JSONRenderer(),
            structlog.dev.ConsoleRenderer()
        ],
        context_class=structlog.threadlocal.wrap_dict(dict),
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
