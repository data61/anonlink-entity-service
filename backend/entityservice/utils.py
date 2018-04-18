#!/usr/bin/env python3
import binascii
import io
import json
import os

import bitmath
from flask import request
from flask_restful import abort


def fmt_bytes(num_bytes):
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


def safe_fail_request(status_code, message):
    # ensure we read the post data, even though we mightn't need it
    # without this you get occasional nginx errors failed (104:
    # Connection reset by peer) (See issue #195)
    if 'Transfer-Encoding' in request.headers and request.headers['Transfer-Encoding'] == 'chunked':
        chunk_size = 4096
        for data in request.input_stream.read(chunk_size):
            pass
    else:
        data = request.get_json()
    abort(http_status_code=status_code, message=message)


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