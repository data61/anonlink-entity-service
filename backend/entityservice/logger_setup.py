import logging.config
import os
from pathlib import Path
import structlog
import yaml


def setup_logging(
    default_path='default_logging.yaml',
    default_level='INFO',
    env_key='LOG_CFG'
):
    """
    Setup logging configuration
    """
    path = os.getenv(env_key, Path('.') / default_path)

    try:
        with open(path, 'rt') as f:
            config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
    except FileNotFoundError:
        print("Logging config YAML file doesn't exist. Falling back to defaults")
        default_level = _str_to_level(default_level)
        logging.basicConfig(level=default_level)

    # Configure Structlog wrapper for client use
    setup_structlog()


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


class ErrorLevelFilter(logging.Filter):
    """
    Filter for the stderr stream
    Doesn't print records below ERROR to stderr to avoid dupes
    """
    def filter(self, record):
        return record.levelno >= logging.ERROR


StdErrFilter = ErrorLevelFilter
StdOutFilter = ErrorLevelFilter


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
