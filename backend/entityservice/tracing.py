
import opentracing
from opentracing.propagation import Format
import jaeger_client
from entityservice.settings import Config as config


def initialize_tracer(service_name='anonlink'):
    jaeger_config = jaeger_client.Config(
        config={
            'sampler': {'type': 'const', 'param': 1},
            'local_agent': {
                'reporting_host': config.JAEGER_HOST,
                'reporting_port': 5775,
            }
        },
        service_name=service_name)

    # Note this call also sets opentracing.tracer
    return jaeger_config.initialize_tracer()


def serialize_span(parent_span):
    serialized_span = {}
    opentracing.tracer.inject(parent_span, Format.TEXT_MAP, serialized_span)
    return serialized_span


def deserialize_span_context(serialized_span):
    if serialized_span is not None:
        span_context = opentracing.tracer.extract(Format.TEXT_MAP, serialized_span)
        return span_context
