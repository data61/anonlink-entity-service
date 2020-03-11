import base64
import datetime
import itertools
import math
import os
import random
import struct
import time
import tempfile
from contextlib import contextmanager
from enum import IntEnum

from bitarray import bitarray
import iso8601



@contextmanager
def temp_file_containing(data):
    with tempfile.NamedTemporaryFile('wb') as fp:
        fp.write(data)
        fp.seek(0)
        yield fp


def serialize_bytes(hash_bytes):
    """ Serialize bloomfilter bytes

    """
    return base64.b64encode(hash_bytes).decode()


def serialize_filters(filters):
    """Serialize filters as clients are required to."""
    return [
        serialize_bytes(f) for f in filters
    ]


def generate_bytes(length):
    return random.getrandbits(length * 8).to_bytes(length, 'big')


def generate_clks(count, size):
    """Generate random clks of given size.

    :param count: The number of clks to generate
    :param size: The number of bytes per generated clk.
    """
    res = []
    for i in range(count):
        hash_bytes = generate_bytes(size)
        res.append(hash_bytes)
    return res


def generate_clks_with_id(count, size):
    return zip(range(count), generate_clks(count, size))


def generate_json_serialized_clks(count, size=128):
    clks = generate_clks(count, size)
    return [serialize_bytes(hash_bytes) for hash_bytes in clks]


def nonempty_powerset(iterable):
    "nonempty_powerset([1,2,3]) --> (1,) (2,) (3,) (1,2) (1,3) (2,3) (1,2,3)"
    # Inspired by:
    # https://docs.python.org/3/library/itertools.html#itertools-recipes
    s = tuple(iterable)
    return itertools.chain.from_iterable(
        itertools.combinations(s, r) for r in range(1, len(s)+1))


def generate_overlapping_clk_data(
    dataset_sizes, overlap=0.9, encoding_size=128, seed=666):
    """Generate random datsets with fixed overlap.

    Postcondition:
    for all some_datasets in nonempty_powerset(datasets),
    len(set.intersection(*some_datasets)) 
        == floor(min(map(len, some_datasets))
           * overlap ** (len(some_datasets) - 1))
    (in case of two datasets A and V this reduces to:
     len(A & B) = floor(min(len(A), len(B)) * overlap)

    For some sets of parameters (particularly when dataset_sizes is
    long), meeting this postcondition is impossible. In that case, we
    raise ValueError.
    """
    i = 0
    datasets_n = len(dataset_sizes)
    dataset_record_is = tuple(set() for _ in dataset_sizes)
    for overlapping_n in range(datasets_n, 0, -1):
        for overlapping_datasets in itertools.combinations(
                range(datasets_n), overlapping_n):
            records_n = int(overlap ** (len(overlapping_datasets) - 1)
                            * min(map(dataset_sizes.__getitem__,
                                      overlapping_datasets)))
            current_records_n = len(set.intersection(
                *map(dataset_record_is.__getitem__, overlapping_datasets)))
            if records_n < current_records_n:
                raise ValueError(
                    'parameters make meeting postcondition impossible')
            for j in overlapping_datasets:
                dataset_record_is[j].update(
                    range(i, i + records_n - current_records_n))
            i += records_n - current_records_n

    # Sanity check
    if __debug__:
        for dataset, dataset_size in zip(dataset_record_is, dataset_sizes):
            assert len(dataset) == dataset_size
        for datasets_with_size in nonempty_powerset(
                zip(dataset_record_is, dataset_sizes)):
            some_datasets, sizes = zip(*datasets_with_size)
            intersection = set.intersection(*some_datasets)
            aim_size = int(min(sizes)
                           * overlap ** (len(datasets_with_size) - 1))
            assert len(intersection) == aim_size

    records = generate_json_serialized_clks(i, size=encoding_size)
    datasets = tuple(list(map(records.__getitem__, record_is))
                     for record_is in dataset_record_is)
    
    rng = random.Random(seed)
    for dataset in datasets:
        rng.shuffle(dataset)

    return datasets





def _check_new_project_response_fields(new_project_data):
    assert 'project_id' in new_project_data
    assert 'update_tokens' in new_project_data
    assert 'result_token' in new_project_data
    assert len(new_project_data['update_tokens']) == 2


class State(IntEnum):
    created = -1
    queued = 0
    running = 1
    completed = 2

    @staticmethod
    def from_string(state):
        if state == 'created':
            return State.created
        elif state == 'queued':
            return State.queued
        elif state == 'running':
            return State.running
        elif state == 'completed':
            return State.completed


def get_expected_number_parties(project_params):
    return project_params.get('number_parties', 2)


def binary_upload_format(encoding_size):
    bit_packing_fmt = f"!{encoding_size}s"
    bit_packing_struct = struct.Struct(bit_packing_fmt)
    return bit_packing_struct


def binary_pack_for_upload(filters, encoding_size):
    bit_packing_struct = binary_upload_format(encoding_size)
    for hash_bytes in filters:
        yield bit_packing_struct.pack(hash_bytes)
