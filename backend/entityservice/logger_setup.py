import os
import logging.config
import structlog

import yaml


def setup_logging(
    default_path='logging.yaml',
    default_level='INFO',
    env_key='LOG_CFG'
):
    """
    Setup logging configuration
    """
    path = os.path.dirname(os.path.abspath(__file__)) + '/' + default_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
    else:
        print("YAML file doesn't exist")
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


class StdErrFilter(logging.Filter):
    """
    Filter for the stderr stream
    Doesn't print records below ERROR to stderr to avoid dupes
    """
    def filter(self, record):
        return 0 if record.levelno < logging.ERROR else 1


class StdOutFilter(logging.Filter):
    """
    Filter for the stdout stream
    Doesn't print records above WARNING to stdout to avoid dupes
    """
    def filter(self, record):
        return 1 if record.levelno < logging.ERROR else 0


def _str_to_level(lvl):
    """
    Convenience function to convert a log level string to the numeric rep
    """
    lvl = lvl.strip().lower()
    if lvl == 'warn':
        return logging.WARNING
    elif lvl == 'info':
        return logging.INFO
    elif lvl == 'debug':
        return logging.DEBUG
    elif lvl == 'critical':
        return logging.CRITICAL
    elif lvl == 'error':
        return logging.ERROR
    else:
        return logging.INFO
