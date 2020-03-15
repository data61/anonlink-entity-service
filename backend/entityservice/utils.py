#!/usr/bin/env python3

import array
import io
import itertools
import json
import os

import binascii
import bitmath
from connexion import ProblemException
from flask import request
from structlog import get_logger
import yaml

from entityservice.errors import InvalidConfiguration
from entityservice.database import DBConn, get_number_parties_uploaded, get_number_parties_ready, get_project_column

logger = get_logger()


def load_yaml_config(filename):
    """
    Load a yaml file as a Python object.

    :param filename: a Path or String object
    :raises InvalidConfiguration if the file isn't found or the yaml isn't valid.
    :return: Python representation of yaml file's contents (usually Dict), or None if empty.
    """
    try:
        with open(filename, 'rt') as f:
            return yaml.safe_load(f)
    except UnicodeDecodeError as e:
        raise InvalidConfiguration(f"YAML file '{filename}' appears corrupt") from e
    except yaml.YAMLError as e:
        raise InvalidConfiguration(f"Parsing YAML config from '{filename}' failed") from e
    except FileNotFoundError as e:
        raise InvalidConfiguration(f"Logging config YAML file '{filename}' doesn't exist.") from e


def fmt_bytes(num_bytes):
    """
    Displays an integer number of bytes in a human friendly form.
    """
    n = bitmath.Byte(num_bytes)
    return n.best_prefix().format('{value:.2f} {unit}')


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i+n]


class IterRawStream(io.RawIOBase):
    """Raw stream that reads from an iterable.

    https://stackoverflow.com/a/20260030 with bugfixes
    """
    def __init__(self, iterable):
        self.leftover = b''
        self.iterable = iterable

    def readable(self):
        return True

    def readinto(self, b):
        l = len(b)  # We're supposed to return at most this much
        chunk = self.leftover
        while not chunk:
            try:
                chunk = next(self.iterable)
            except StopIteration:
                return 0  # Indicate EOF.
        output, self.leftover = chunk[:l], chunk[l:]
        b[:len(output)] = output
        return len(output)


def iterable_to_stream(iterable, buffer_size=io.DEFAULT_BUFFER_SIZE):
    """
    Pass an iterable (e.g. a generator) that yields bytes as a read-only
    input stream.

    The stream implements the buffered I/O API.
    """
    return io.BufferedReader(IterRawStream(iterable), buffer_size=buffer_size)


def safe_fail_request(status_code, message, **kwargs):
    """
    generates an error message in the right format.

    You can pass in additional key/value pairs for the keys 'title', 'instance' and 'type' in order to populate
    the returned problem message.

    :param status_code: the HTTP status code
    :param message: the 'detail' section of the problem
    :param kwargs: additional key/value pairs to populate the problem
    """
    # ensure we read the post data, even though we mightn't need it
    # without this you get occasional nginx errors failed (104:
    # Connection reset by peer) (See issue #195)
    if 'Transfer-Encoding' in request.headers and request.headers['Transfer-Encoding'] == 'chunked':
        chunk_size = 4096
        for _ in request.input_stream.read(chunk_size):
            pass
    else:
        _ = request.get_json()
    raise ProblemException(status=status_code, detail=message, **kwargs)


def get_stream():
    if 'Transfer-Encoding' in request.headers and request.headers['Transfer-Encoding'] == 'chunked':
        stream = request.input_stream
    else:
        stream = request.stream
    return stream


def get_json():
    # Handle chunked Transfer-Encoding...
    if 'Transfer-Encoding' in request.headers and request.headers['Transfer-Encoding'] == 'chunked':
        stream = get_stream()

        def consume_as_string(byte_stream):
            data = []
            while True:
                byte_data = byte_stream.read(4096)
                if byte_data:
                    data.append(byte_data.decode())
                else:
                    break
            return ''.join(data)

        return json.loads(consume_as_string(stream))
    else:
        return request.get_json()


def generate_code(length=24):
    return binascii.hexlify(os.urandom(length)).decode('utf8')


def clks_uploaded_to_project(project_id, check_data_ready=False):
    """ See if the given project has had all parties contribute data.
    """
    log = logger.bind(pid=project_id)
    log.info("Counting contributing parties")
    with DBConn() as conn:
        if check_data_ready:
            parties_contributed = get_number_parties_ready(conn, project_id)
            log.info("Parties where data is ready: {}".format(parties_contributed))
        else:
            parties_contributed = get_number_parties_uploaded(conn, project_id)
            log.info("Parties where data is uploaded: {}".format(parties_contributed))
        number_parties = get_project_column(conn, project_id, 'parties')
    log.info("{}/{} parties have contributed clks".format(parties_contributed, number_parties))
    return parties_contributed == number_parties


def similarity_matrix_from_csv_bytes(data):
    rows = data.decode().splitlines()
    sims = array.array('d')
    rec_is0 = array.array('I')
    rec_is1 = array.array('I')
    for row in rows:
        rec_i0_str, rec_i1_str, sim_str = row.split(',')
        sims.append(float(sim_str))
        rec_is0.append(int(rec_i0_str))
        rec_is1.append(int(rec_i1_str))
    length = len(sims)
    assert length == len(rec_is0)
    assert length == len(rec_is1)
    dset_is0 = array.array('I', itertools.repeat(0, length))
    dset_is1 = array.array('I', itertools.repeat(1, length))

    return sims, (dset_is0, dset_is1), (rec_is0, rec_is1)


def convert_mapping_to_list(permutation):
    """Convert the permutation from a dict mapping into a list

    :param dict permutation:
        Assumes the keys and values of the given dict are numbers in the
        inclusive range from 0 to length. Note the keys should be int.
    :return:
        A list of the values from the passed dict - in the order
        defined by the keys.
    """
    return [permutation[i] for i in range(len(permutation))]


def deduplicate_sorted_iter(iterable):
    """
    Remove duplicates from a sorted iterable.

    :param iterable:
    :return:
    """
    previous = next(iterable)
    yield previous

    for current in iterable:
        if current != previous:
            yield current
        previous = current
