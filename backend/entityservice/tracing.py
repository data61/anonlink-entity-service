

import jaeger_client
from entityservice.settings import Config as config


def initialize_tracer():
    jaeger_config = jaeger_client.Config(
        config={
            'sampler': {'type': 'const', 'param': 1},
            'local_agent': {
                'reporting_host': config.JAEGER_HOST,
                'reporting_port': 5775,
            }
        },
        service_name='anonlink')
    return jaeger_config.initialize_tracer()
