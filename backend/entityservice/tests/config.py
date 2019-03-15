import logging
import os

initial_delay = float(os.environ.get("INITIAL_DELAY", "2"))
rate_limit_delay = float(os.environ.get("RATE_LIMIT_DELAY", "0.25"))
LOGLEVEL = getattr(logging, os.environ.get("LOGGING_LEVEL", "INFO"))
LOGFILE = os.environ.get("LOGGING_FILE", "es-test.log")
url = os.environ.get("ENTITY_SERVICE_URL", "http://localhost:8851/api/v1/")

logger = logging.getLogger('n1')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s.%(msecs)03d %(name)020s %(levelname)010s - %(message)s', "%H:%M:%S")
ch = logging.StreamHandler()
ch.setFormatter(formatter)
ch.setLevel(LOGLEVEL)

fh = logging.FileHandler(LOGFILE)
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)

logger.propagate = False
logger.addHandler(ch)
logger.addHandler(fh)

logger.info("Testing Entity Service at URL: {}".format(url))
