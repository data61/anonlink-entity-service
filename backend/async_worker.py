import os
import time
import math
import json
import random
from datetime import datetime, timedelta

from celery.signals import after_setup_task_logger, after_setup_logger
from celery import Celery, Task, chord, chain
from celery.utils.log import get_task_logger
import psycopg2.extras

import cache
from serialization import deserialize_filters, load_public_key
from database import *
from settings import Config as config

from phe import paillier
import anonlink

celery = Celery('tasks',
                broker=config.BROKER_URL,
                backend=config.CELERY_RESULT_BACKEND
                )

celery.conf.CELERY_TASK_SERIALIZER = 'json'
celery.conf.CELERY_ACCEPT_CONTENT = ['json']
celery.conf.CELERY_RESULT_SERIALIZER = 'json'
celery.conf.CELERY_ANNOTATIONS = config.CELERY_ANNOTATIONS
celery.conf.CELERYD_PREFETCH_MULTIPLIER = 1


@after_setup_logger.connect
@after_setup_task_logger.connect
def init_celery_logger(logger, **kwargs):
    for handler in logger.handlers[:]:
        handler.setFormatter(config.consoleFormat)
        handler.setLevel(logging.INFO)


logger = get_task_logger(__name__)
logger.info("Setting up celery worker")


def convert_mapping_to_list(permutation):
    """Convert the permutation from a dict mapping into a list"""
    l = len(permutation)

    perm_list = []
    for j in range(l):
        perm_list.append(permutation[j])
    return perm_list


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i+n]


def encrypt_vector(values, public_key, base):
    """
    Encrypt an array of booleans.

    Note the exponent will always be 0

    :return list of encrypted ciphertext strings
    """

    # Only use this for testing purposes!
    # Should use the next section of code instead!
    #return [1 if x else 0 for x in values]

    # Using the default encoding Base:
    # return [
    #     str(public_key.encrypt(int(x)).ciphertext())
    #     for x in values]


    class EntityEncodedNumber(paillier.EncodedNumber):
        BASE = base
        LOG2_BASE = math.log(BASE, 2)

    precision = 1e3

    encoded_mask = [EntityEncodedNumber.encode(public_key, x) for x in values]

    encrypted_mask = [public_key.encrypt(enc, precision).ciphertext() for enc in encoded_mask]

    return encrypted_mask


@celery.task()
def calculate_mapping(resource_id):
    logger.debug("Checking we need to calculating mapping")

    db = connect_db()
    is_already_calculated, mapping_db_id, result_type = check_mapping_ready(db, resource_id)
    if is_already_calculated:
        logger.info("Mapping '{}' is already computed. Skipping".format(resource_id))
        return

    logger.debug("Getting dp ids for compute similarity task")
    dp_ids = get_dataprovider_ids(db, resource_id)

    logger.debug("Data providers: {}".format(dp_ids))
    assert len(dp_ids) == 2, "Only support two party comparisons at the moment"

    logger.debug("Setting start time")
    with db.cursor() as cur:
        cur.execute("""UPDATE mappings SET
                      time_started = now()
                    WHERE
                      resource_id = %s
                    """,
                    [resource_id])
    db.commit()

    compute_similarity.delay(resource_id, dp_ids)

    logger.info("Entity similarity computation scheduled")

    return 'Done'


@celery.task()
def compute_similarity(resource_id, dp_ids):
    """

    """

    logger.info("Pulling CLKs from data provider ids: {}, {}".format(dp_ids[0], dp_ids[1]))
    #db = connect_db()

    # Prime the redis cache
    filters1 = cache.get_deserialized_filter(dp_ids[0])
    filters2 = cache.get_deserialized_filter(dp_ids[1])

    lenf1 = len(filters1)
    lenf2 = len(filters2)

    logger.info("Computing similarity for {} x {} entities".format(lenf1, lenf2))
    if max(lenf1, lenf2) < config.GREEDY_SIZE:
        logger.info("Computing similarity using more accurate method")

        #filters1 = deserialize_filters(serialized_filters1)
        #filters2 = deserialize_filters(serialized_filters2)

        similarity = anonlink.entitymatch.calculate_filter_similarity(filters1, filters2)
        logger.debug("Calculating optimal connections for entire network")
        # The method here makes a big difference in running time
        mapping = anonlink.network_flow.map_entities(similarity,
                                                     threshold=config.ENTITY_MATCH_THRESHOLD,
                                                     method='bipartite')
        res = {
            "mapping": mapping,
            "lenf1": lenf1,
            "lenf2": lenf2
        }
        save_and_permute.delay(res, resource_id)

    else:
        logger.info("Computing similarity using greedy method")

        logger.debug("Chunking computation task")

        chunk_size = int(config.GREEDY_CHUNK_SIZE / lenf2)

        serialized_filters1, filter1_popcounts = get_filter(db, dp_ids[0])
        # serialized_filters2, filter2_popcounts = get_filter(db, dp_ids[1])

        filter1_chunks = chunks(serialized_filters1, chunk_size)
        logger.info("Chunking org 1's {} entities into {} computation tasks of size {}".format(
            lenf1, int(lenf1/chunk_size), chunk_size))

        mapping_future = chord(
            (compute_filter_similarity.s(chunk, dp_ids[1], chunk_number, resource_id) for chunk_number, chunk in enumerate(filter1_chunks)),
            aggregate_filter_chunks.s(resource_id, lenf1, lenf2)
        ).apply_async()


@celery.task()
def save_and_permute(similarity_result, resource_id):
    logger.debug("Saving and possibly permuting data")
    mapping = similarity_result['mapping']
    db = connect_db()
    _, _, result_type = check_mapping_ready(db, resource_id)

    # Just save the raw "mapping"
    logger.info("Saving the resulting map data to the db")
    with db.cursor() as cur:
        cur.execute("""
            UPDATE mapping_results SET
              result = (%s),
            WHERE
              mapping = %s
            """,
            [psycopg2.extras.Json(mapping), resource_id])
    db.commit()
    logger.info("Mapping saved")

    if result_type in {"permutation", "permutation_unencrypted_mask"}:
        logger.debug("Submitting job to permute mapping")
        permute_mapping_data.apply_async(
            (
                resource_id,
                similarity_result['lenf1'],
                similarity_result['lenf2']
            )
        )

    # Post similarity computation cleanup
    logger.info("Removing clk filters from redis cache")

    dp_ids = get_dataprovider_ids(db, resource_id)
    cache.remove_from_cache(dp_ids[0])
    cache.remove_from_cache(dp_ids[1])
    calculate_comparison_rate.delay()


@celery.task()
def permute_mapping_data(resource_id, len_filters1, len_filters2):
    """
    Task which will create a permutation after a mapping has been completed.

    :param resource_id: The mapping resource
    :param len_filters1:
    :param len_filters2:

    """
    db = connect_db()
    mapping = json.loads(get_mapping_result(db, resource_id))

    logger.info("Creating random permutations")
    logger.info("Entities in dataset A: {}, Entities in dataset B: {}".format(len_filters1, len_filters2))

    """
    Pack all the entities that match in the **same** random locations in both permutations.
    Then fill in all the gaps!

    Dictionaries first, then converted to lists.
    """
    smaller_dataset_size = min(len_filters1, len_filters2)
    logger.info("Smaller dataset size is {}".format(smaller_dataset_size))
    number_in_common = len(mapping)
    a_permutation = {}  # Should be length of filters1
    b_permutation = {}  # length of filters2

    # By default mark all rows as NOT included in the mask
    mask = {i: False for i in range(smaller_dataset_size)}

    # start with all the possible indexes
    remaining_new_indexes = list(range(smaller_dataset_size))
    logger.info("Shuffling indices for matched entities")
    random.shuffle(remaining_new_indexes)
    logger.info("Assigning random indexes for {} matched entities".format(number_in_common))

    for mapping_number, a_index in enumerate(mapping):
        b_index = mapping[a_index]

        # Choose the index in the new mapping (randomly)
        mapping_index = remaining_new_indexes[mapping_number]

        a_permutation[a_index] = mapping_index
        b_permutation[b_index] = mapping_index

        # Mark the row included in the mask
        mask[mapping_index] = True

    remaining_new_indexes = set(remaining_new_indexes[number_in_common:])
    logger.info("Randomly adding all non matched entities")

    # Note the a and b datasets could be of different size.
    # At this point, both still have to use the remaining_new_indexes, and any
    # indexes that go over the number_in_common
    remaining_a_values = list(set(range(smaller_dataset_size, len_filters1)).union(remaining_new_indexes))
    remaining_b_values = list(set(range(smaller_dataset_size, len_filters2)).union(remaining_new_indexes))

    # Shuffle the remaining indices on each
    random.shuffle(remaining_a_values)
    random.shuffle(remaining_b_values)

    # For every element in a's permutation
    for a_index in range(len_filters1):
        # Check if it is not already present
        if a_index not in a_permutation:
            # This index isn't yet mapped

            # choose and remove a random index from the extended list of those that remain
            # note this "could" be the same row (a NOP 1-1 permutation)
            mapping_index = remaining_a_values.pop()

            a_permutation[a_index] = mapping_index

    # For every eventual element in a's permutation
    for b_index in range(len_filters2):
        # Check if it is not already present
        if b_index not in b_permutation:
            # This index isn't yet mapped

            # choose and remove a random index from the extended list of those that remain
            # note this "could" be the same row (a NOP 1-1 permutation)
            mapping_index = remaining_b_values.pop()
            b_permutation[b_index] = mapping_index

    logger.info("Completed new permutations for each party")

    with db.cursor() as cur:
        dp_ids = get_dataprovider_ids(db, resource_id)

        for i, permutation in enumerate([a_permutation, b_permutation]):
            # We convert here because celery and dicts with int keys don't play nice
            perm_list = convert_mapping_to_list(permutation)
            logger.debug("Saving a permutation")

            cur.execute("""INSERT INTO permutations
                        (dp, permutation)
                        VALUES
                        (%s, %s)
                        """,
                        [dp_ids[i], psycopg2.extras.Json(perm_list)]
                        )

        logger.debug("Raw permutation data saved. Now saving raw mask")

        # Convert the mask dict to a list of 0/1 ints
        mask_list = convert_mapping_to_list({
                                                int(key): 1 if value else 0
                                                for key, value in mask.items()})

        logger.debug("Saving the mask")
        json_mask = psycopg2.extras.Json(json.dumps(mask_list))
        cur.execute("""UPDATE permutation_masks SET
                      raw = (%s),
                    WHERE
                      mapping = %s
                    """,
                    [json_mask, resource_id])
        logger.info("Mask saved")
    db.commit()

    post_permutation.apply_async((resource_id,))



@celery.task()
def paillier_encrypt_mask(resource_id):
    """
    The paillier encrypted mask is saved in the encrypted_permutation_masks table.
    """

    db = connect_db()
    with db.cursor() as cur:
        smaller_dataset_size = get_smaller_dataset_size_for_mapping(db, resource_id)

        mask_list = get_permutation_unencrypted_mask(db, resource_id)

        logger.info("Encrypting mask data")

        pk, cntx = get_paillier(db, resource_id)
        base = cntx['base']

        # Subtasks will encrypt the mask in chunks
        logger.info("Chunking mask")
        encrypted_chunks = chunks(mask_list, config.ENCRYPTION_CHUNK_SIZE)
        # calling .apply_async will create a dedicated task so that the
        # individual tasks are applied in a worker instead
        encrypted_mask_future = chord(
            (encrypt_mask.s(chunk, pk, base) for chunk in encrypted_chunks),
            persist_encrypted_mask.s(dataset_size=smaller_dataset_size,
                           paillier_context=cntx,
                           resource_id=resource_id)
        ).apply_async()


@celery.task()
def post_permutation(resource_id):
    """
    Task to carry out any follow up after the permutation + mask is saved.
    """

    # If the resource has an encrypted mask type, here we should
    # trigger the encryption of the mask

    db = connect_db()
    _, _, result_type = check_mapping_ready(db, resource_id)

    if result_type == "permutation":
        logger.info("Need to encrypt the mask")
        paillier_encrypt_mask.apply_async((resource_id,))

    elif result_type == "permutation_unencrypted_mask":
        logger.info("No need to encrypt the mask")
        mark_mapping_complete.apply_async((resource_id,))


@celery.task()
def mark_mapping_complete(resource_id):
    logger.debug("Marking job complete")
    db = connect_db()
    with db.cursor() as cur:
        cur.execute("""
            UPDATE mappings SET
              ready = TRUE,
              time_completed = now()
            WHERE
              resource_id = %s
            """,
            [resource_id])
    db.commit()



@celery.task()
def compute_filter_similarity(f1, dp2_id, chunk_number, resource_id):
    logger.info("Computing similarity for a chunk of filters")

    logger.debug("Checking that the resource exists (in case of job being canceled)")
    db = connect_db()
    if not check_mapping_exists(db, resource_id):
        logger.warning("Skipping as resource not found.")
        return None

    t0 = time.time()
    logger.debug("Deserializing chunked filters")
    filters2 = cache.get_deserialized_filter(dp2_id)
    t1 = time.time()
    chunk = deserialize_filters(f1)
    t2 = time.time()
    logger.debug("Calculating filter similarity")
    chunk_results = anonlink.entitymatch.calculate_filter_similarity(chunk, filters2,
                                                                     threshold=config.ENTITY_MATCH_THRESHOLD,
                                                                     k=5)
    t3 = time.time()

    logger.info("Timings: Prep: {:.4f} + {:.4f}, Solve: {:.4f}, Total: {:.4f}".format(t1-t0, t2-t1, t3-t2, t3-t0))
    # Update the number of comparisons completed
    save_current_progress(len(filters2) * len(chunk), resource_id)

    partial_sparse_result = []
    # offset chunk's A index by chunk_size * chunk_number
    chunk_size = len(chunk)
    offset = chunk_size * chunk_number
    logger.debug("Offset by {}".format(offset))
    for (ia, score, ib) in chunk_results:
        partial_sparse_result.append((ia + offset, score, ib))

    return partial_sparse_result


def save_current_progress(comparisons, resource_id):
    logger.info("Progress. Compared {} CLKS".format(comparisons))
    cache.update_progress(comparisons, resource_id)


@celery.task()
def aggregate_filter_chunks(sparse_result_groups, resource_id, lenf1, lenf2):
    sparse_matrix = []

    for partial_sparse_result in sparse_result_groups:
        sparse_matrix.extend(partial_sparse_result)

    logger.debug("Calculating the optimal mapping from similarity matrix")
    mapping = anonlink.entitymatch.greedy_solver(sparse_matrix)

    logger.info("Entity mapping has been computed")

    res = {
        "mapping": mapping,
        "lenf1": lenf1,
        "lenf2": lenf2
    }
    save_and_permute.delay(res, resource_id)


@celery.task()
def persist_encrypted_mask(encrypted_mask_chunks, dataset_size, paillier_context, resource_id):
    encrypted_mask = [mask for chunk in encrypted_mask_chunks for mask in chunk]

    db = connect_db()
    with db.cursor() as cur:
        logger.info("Serializing encrypted permutation data")
        result_to_save = psycopg2.extras.Json(json.dumps(
            {"rows": dataset_size, "mask": encrypted_mask, "paillier_context": paillier_context}))

        logger.info("Inserting encrypted permutation data to db")
        cur.execute("""UPDATE mappings SET
                    result = (%s),
                    ready = TRUE,
                    time_completed = now()
                    WHERE
                    resource_id = %s
                    """,
                    [result_to_save, resource_id])
    logger.debug("Committing encrypted permutation data to db")
    db.commit()
    logger.info("Encrypted mask has been saved")
    mark_mapping_complete.apply_async((resource_id,))


@celery.task()
def encrypt_mask(values, pk, base):
    logger.info("Encrypting a mask chunk")
    public_key = load_public_key(pk)
    return encrypt_vector(values, public_key, base)


@celery.task()
def calculate_comparison_rate():
    dbinstance = connect_db()
    logger.info("Calculating comparison rate")
    elapsed_mapping_time_query = """
        select resource_id, (time_completed - time_started) as elapsed
        from mappings
        WHERE
          mappings.ready=TRUE
      """

    total_comparisons = 0
    total_time = timedelta(0)
    for mapping in query_db(dbinstance, elapsed_mapping_time_query):

        comparisons = get_total_comparisons_for_mapping(dbinstance, mapping['resource_id'])
        #logger.debug("{} comparisons in {} seconds".format(comparisons, mapping['elapsed'].total_seconds()))
        if comparisons != 'NA':
            total_comparisons += comparisons
        else:
            logger.debug("Skipping mapping as it hasn't completed")
        total_time += mapping['elapsed']

    if total_time.total_seconds() > 0:
        rate = total_comparisons/total_time.total_seconds()
        logger.info("Total comparisons: {}".format(total_comparisons))
        logger.info("Total time:        {}".format(total_time.total_seconds()))
        logger.info("Comparison rate:   {}".format(rate))

        with dbinstance.cursor() as cur:
            insert_comparison_rate(cur, rate)

        dbinstance.commit()
    else:
        logger.warning("Can't compute comparison rate yet")
