"""
See Issue #42

"""
from prometheus_client import Gauge
from prometheus_client.core import Counter, Histogram


UPLOAD_REQUEST_LATENCY = Histogram('anonlink_upload_request_latency_seconds', 'CLK upload request latency')

STATUS_REQUEST_LATENCY = Histogram('anonlink_status_request_latency_seconds', 'Status Request Latency')
STATUS_REQUEST_COUNT = Counter('anonlink_status_counter_total', 'Number of Status Requests')

COMPARISON_RATE_GAUGE = Gauge('anonlink_comparison_rate', 'Max number of comparisons per second')
PROJECT_COUNT = Gauge('anonlink_mapping_counter_total', 'Number of mappings')

RUN_STATUS_COUNT = Counter(
    'anonlink_run_status_counter',
    'Number of status checks on a run',
    ['run']
)
