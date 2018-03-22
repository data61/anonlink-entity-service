"""
See Issue #42

Version 1 could just collect metrics via the REST api:
- mapping_count
- mapping_ready_count
- mapping_rate gauge

"""

import sys
import time
import requests

from prometheus_client import start_http_server
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, Summary, REGISTRY, Histogram


UPLOAD_REQUEST_LATENCY = Histogram('es_upload_request_latency_seconds', 'CLK upload request latency')

STATUS_REQUEST_LATENCY = Histogram('es_status_request_latency_seconds', 'Status Request Latency')
STATUS_REQUEST_COUNT = CounterMetricFamily('es_status_counter_total', 'Number of Status Requests')

MAPPING_RATE_GAUGE = GaugeMetricFamily('es_mapping_rate', 'Max number of comparisons per second')
MAPPING_COUNT = CounterMetricFamily('es_mapping_counter_total', 'Number of mappings')
READY_MAPPING_COUNT = CounterMetricFamily('es_mapping_counter_ready', 'Number of ready mappings')


class EntityServiceRestAPICollector(object):
    """
    This is a metrics collector that uses the REST API.

    """

    def __init__(self, target):
        self.target = target

    def collect(self):
        rate_gauge = GaugeMetricFamily('mapping_rate', 'Max number of comparisons per second')
        mappings_gauge = CounterMetricFamily('mapping_counter_total', 'Number of mappings')
        ready_mappings_counter = CounterMetricFamily('ready_mapping_counter', 'Number of ready mappings')

        # Request the information we need from the api
        status = requests.get(self.target + '/status').json()
        num_mappings = status['number_mappings']
        rate = status['rate']

        rate_gauge.add_metric(['rate'], rate)
        mappings_gauge.add_metric(['count'], num_mappings)

        yield rate_gauge
        yield mappings_gauge

        # More detailed mapping info
        mappings = requests.get(self.target + '/mappings').json()['mappings']
        ready_mappings_counter.add_metric(['ready'], sum(1 for m in mappings if m['ready']))
        yield ready_mappings_counter


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: metrics_exporter.py ES_API_ADDRESS LOCAL_SERVER_PORT\n")
        sys.exit(1)

    time.sleep(10)

    REGISTRY.register(EntityServiceRestAPICollector(sys.argv[1]))

    start_http_server(int(sys.argv[2]))

    while True:
        time.sleep(5)
