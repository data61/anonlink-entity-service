import os


initial_delay = float(os.environ.get("INITIAL_DELAY", "2"))
rate_limit_delay = float(os.environ.get("RATE_LIMIT_DELAY", "0.25"))
url = os.environ.get("SERVER", "http://localhost:8851") + "/api/v1/"
