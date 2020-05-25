from flask import g
from structlog import get_logger

logger = get_logger()


def bind_log_and_span(project_id, run_id=None):

    log = logger.bind(pid=project_id)
    parent_span = g.flask_tracer.get_span()
    parent_span.set_tag("project_id", project_id)
    if run_id is not None:
        log = log.bind(rid=run_id)
        parent_span.set_tag("run_id", run_id)
    return log, parent_span


def convert_encoding_upload_to_clknblock(clk_json):
    """Convert from one upload schema to another.

    The source schema specifies both "encodings" and "blocks" independently at the top level,
    the target is the "clknblocks" format.
    """
    result = []
    if "blocks" in clk_json:
        # user has supplied blocking info as a mapping from encoding id to a list of block ids
        # The "encodings" are also supplied indexed by encoding_id
        # target format is ['UG9vcA==', '001', '211'], [...]
        for encoding_id in clk_json['blocks']:
            encoding = clk_json['encodings'][int(encoding_id)]
            result.append(
                [encoding] + clk_json['blocks'][encoding_id]
            )
    else:
        # user has only supplied encodings
        for encoding in clk_json['encodings']:
            result.append([encoding, '1'])

    return {'clknblocks': result}


def convert_clks_to_clknblocks(clk_json):
    return {'clknblocks': [[encoding, '1'] for encoding in clk_json['clks']]}