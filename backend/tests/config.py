import logging
import os


rate_limit_delay = float(os.environ.get("RATE_LIMIT_DELAY", "0.25"))
LOGLEVEL = getattr(logging, os.environ.get("LOGGING_LEVEL", "INFO"))
url = os.environ.get("ENTITY_SERVICE_URL", "https://es.data61.xyz/api/v1")

logger = logging.getLogger('n1')
logger.setLevel(LOGLEVEL)
formatter = logging.Formatter('%(asctime)s.%(msecs)03d %(levelname)s - %(message)s', "%H:%M:%S")
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.propagate = False
logger.addHandler(ch)

logger.info("Testing Entity Service at URL: {}".format(url))
