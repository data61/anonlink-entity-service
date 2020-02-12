
import functools

import jaeger_client
import opentracing
from opentracing.propagation import Format
from opentracing_instrumentation import get_current_span, span_in_context

from entityservice.settings import Config as config
from entityservice.utils import load_yaml_config

DEFAULT_TRACER_CONFIG = {'sampler': {'type': 'const', 'param': 1}}


def get_tracer_config(service_name):
    if config.TRACING_CONFIG_FILENAME is not None:
        tracing_config = load_yaml_config(config.TRACING_CONFIG_FILENAME)
    else:
        tracing_config = DEFAULT_TRACER_CONFIG
    return jaeger_client.Config(config=tracing_config, service_name=service_name)


def initialize_tracer(service_name='api'):
    jaeger_config = get_tracer_config(service_name)
    # Note this call also sets opentracing.tracer
    return jaeger_config.initialize_tracer()


def create_tracer(service_name='worker'):
    jaeger_config = get_tracer_config(service_name)
    return jaeger_config.new_tracer()


def serialize_span(parent_span):
    serialized_span = {}
    opentracing.tracer.inject(parent_span, Format.TEXT_MAP, serialized_span)
    return serialized_span


def serialize_current_span():
    """ get the current span and serialize it."""
    return serialize_span(get_current_span())


def deserialize_span_context(serialized_span):
    if serialized_span is not None:
        span_context = opentracing.tracer.extract(Format.TEXT_MAP, serialized_span)
        return span_context


def trace(_func=None, *, span_name=None, args_as_tags=None, parent_span_arg='parent_span'):
    """
    decorator to encapsulate a function in a span for tracing.

    :param span_name: the operation name to set in the span. If None, then the function name is used
    :param args_as_tags: a list of arguments of the function to be added as tags to the span.
    :param parent_span_arg: a reference to the parent span. This can either be, a Span, SpanContext, serialized span
                            context, or None. If None, then the current active span is used as parent
    """
    def trace_decorator(func):
        with opentracing.tracer.start_span('in deco'):
            pass

        @functools.wraps(func)
        def tracing_wrapper(*args, **kwargs):
            op_name = func.__name__ if span_name is None else span_name
            args_dict = dict(zip(func.__code__.co_varnames, args))
            args_dict.update(kwargs)
            parent = args_dict.get(parent_span_arg, None)
            try:
                parent = deserialize_span_context(parent)

            except:
                pass
            if parent is None:
                parent = get_current_span()
            with opentracing.tracer.start_span(op_name, child_of=parent) as span:
                #add tags
                try:
                    for arg in args_as_tags:
                        span.set_tag(arg, args_dict.get(arg, None))
                except TypeError:
                    pass
                with span_in_context(span):
                    value = func(*args, **kwargs)
            return value
        return tracing_wrapper

    if _func is None:
        return trace_decorator
    else:
        return trace_decorator(_func)
