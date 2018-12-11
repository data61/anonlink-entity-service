#!/usr/bin/env python3

import io
import json
import os

import binascii
import bitmath
from flask import request
from connexion import ProblemException
from structlog import get_logger

from entityservice.database import connect_db, get_number_parties_uploaded, get_number_parties_ready
from entityservice.database import get_project_column

logger = get_logger()


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


def iterable_to_stream(iterable, buffer_size=io.DEFAULT_BUFFER_SIZE):
    """
    Pass an iterable (e.g. a generator) that yields bytes as a read-only
    input stream.

    The stream implements the buffered I/O API.

    http://stackoverflow.com/questions/6657820/python-convert-an-iterable-to-a-stream
    """
    class IterStream(io.RawIOBase):
        def __init__(self):
            self.leftover = None

        def readable(self):
            return True

        def readinto(self, b):
            try:
                l = len(b)  # We're supposed to return at most this much
                chunk = self.leftover or next(iterable)
                output, self.leftover = chunk[:l], chunk[l:]
                b[:len(output)] = output
                return len(output)
            except StopIteration:
                return 0    # indicate EOF

    return io.BufferedReader(IterStream(), buffer_size=buffer_size)


def chain_streams(streams, buffer_size=io.DEFAULT_BUFFER_SIZE):
    """
    Chain an iterable of streams together into a single buffered stream.

    Usage:
        def generate_open_file_streams():
            for file in filenames:
                yield open(file, 'rb')

        f = chain_streams(generate_open_file_streams())
        f.read()

    """

    class ChainStream(io.RawIOBase):
        def __init__(self):
            self.leftover = b''
            self.stream_iter = iter(streams)
            try:
                self.stream = next(self.stream_iter)
            except StopIteration:
                self.stream = None

        def readable(self):
            return True

        def _read_next_chunk(self, max_length):
            # Return 0 or more bytes from the current stream, first returning all
            # leftover bytes. If the stream is closed returns b''
            if self.leftover:
                return self.leftover
            elif self.stream is not None:
                return self.stream.read(max_length)
            else:
                return b''

        def readinto(self, b):
            buffer_length = len(b)
            chunk = self._read_next_chunk(buffer_length)
            while len(chunk) == 0:
                # move to next stream
                if self.stream is not None:
                    self.stream.close()
                try:
                    self.stream = next(self.stream_iter)
                    chunk = self._read_next_chunk(buffer_length)
                except StopIteration:
                    # No more streams to chain together
                    self.stream = None
                    return 0  # indicate EOF
            output, self.leftover = chunk[:buffer_length], chunk[buffer_length:]
            b[:len(output)] = output
            return len(output)

    return io.BufferedReader(ChainStream(), buffer_size=buffer_size)


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
    logger.info("Counting contributing parties")
    conn = connect_db()
    if check_data_ready:
        parties_contributed = get_number_parties_ready(conn, project_id)
        logger.info("Parties where data is ready: {}".format(parties_contributed))
    else:
        parties_contributed = get_number_parties_uploaded(conn, project_id)
        logger.info("Parties where data is uploaded: {}".format(parties_contributed))
    number_parties = get_project_column(conn, project_id, 'parties')
    logger.info("{}/{} parties have contributed clks".format(parties_contributed, number_parties))
    return parties_contributed == number_parties


def similarity_matrix_from_csv_bytes(data):
    rows = data.decode().splitlines()
    for row in rows:
        index_1, index_2, score = row.split(',')
        # Note we rewrite in a different order because we love making work for ourselves
        yield (int(index_1), float(score), int(index_2))


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
