import random

from entityservice.cache import encodings as encoding_cache
from entityservice.async_worker import celery, logger
from entityservice.database import DBConn, get_project_column, insert_mapping_result, get_dataprovider_ids, \
    get_run_result, insert_permutation, insert_permutation_mask
from entityservice.tasks.base_task import TracedTask
from entityservice.tasks import mark_run_complete
from entityservice.tasks.stats import calculate_comparison_rate
from entityservice.utils import convert_mapping_to_list


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id', 'run_id'))
def save_and_permute(similarity_result, project_id, run_id, parent_span):
    log = logger.bind(pid=project_id, run_id=run_id)
    log.debug("Saving and possibly permuting data")
    groups = similarity_result['groups']

    # Note Postgres requires JSON object keys to be strings
    # Celery actually converts the json arguments in the same way

    with DBConn() as db:
        result_type = get_project_column(db, project_id, 'result_type')

        # Save the raw groups
        log.debug("Saving the groups in the DB")
        result_id = insert_mapping_result(db, run_id, groups)
        dp_ids = get_dataprovider_ids(db, project_id)

    log.info("Result saved to db with result id {}".format(result_id))

    if result_type == "permutations":
        log.debug("Submitting job to permute mapping")
        dataset0_size, dataset1_size = similarity_result['datasetSizes']
        permute_mapping_data.apply_async(
            (
                project_id,
                run_id,
                dataset0_size,
                dataset1_size,
                save_and_permute.get_serialized_span()
            )
        )
    else:
        log.debug("Mark job as complete")
        mark_run_complete.delay(run_id, save_and_permute.get_serialized_span())

    # Post similarity computation cleanup
    log.debug("Removing clk filters from redis cache")

    for dp_id in dp_ids:
        encoding_cache.remove_from_cache(dp_id)
    calculate_comparison_rate.delay()


@celery.task(base=TracedTask, ignore_result=True, args_as_tags=('project_id', 'run_id', 'len_filters1', 'len_filters2'))
def permute_mapping_data(project_id, run_id, len_filters1, len_filters2, parent_span):
    """
    Task which will create a permutation after a mapping has been completed.

    :param project_id: The project resource id
    :param run_id: The run id
    :param len_filters1:
    :param len_filters2:

    """
    log = logger.bind(pid=project_id, run_id=run_id)

    with DBConn() as conn:

        groups = get_run_result(conn, run_id)

        log.info("Creating random permutations")
        log.debug("Entities in dataset A: {}, Entities in dataset B: {}".format(len_filters1, len_filters2))

        """
        Pack all the entities that match in the **same** random locations in both permutations.
        Then fill in all the gaps!
    
        Dictionaries first, then converted to lists.
        """
        smaller_dataset_size = min(len_filters1, len_filters2)
        log.debug("Smaller dataset size is {}".format(smaller_dataset_size))
        number_in_common = len(groups)
        a_permutation = {}  # Should be length of filters1
        b_permutation = {}  # length of filters2

        # By default mark all rows as NOT included in the mask
        mask = {i: False for i in range(smaller_dataset_size)}

        # start with all the possible indexes
        remaining_new_indexes = list(range(smaller_dataset_size))
        log.info("Shuffling indices for matched entities")
        random.shuffle(remaining_new_indexes)
        log.info("Assigning random indexes for {} matched entities".format(number_in_common))

        for group_number, group in enumerate(groups):
            # It should not fail because the permutation result is only available for 2 parties, but let's be to safe.
            assert 2 == len(group)
            (_, a_index), (_, b_index) = sorted(group)

            # Choose the index in the new mapping (randomly)
            mapping_index = remaining_new_indexes[group_number]

            a_permutation[a_index] = mapping_index
            b_permutation[b_index] = mapping_index

            # Mark the row included in the mask
            mask[mapping_index] = True

        remaining_new_indexes = set(remaining_new_indexes[number_in_common:])
        log.info("Randomly adding all non matched entities")

        # Note the a and b datasets could be of different size.
        # At this point, both still have to use the remaining_new_indexes, and any
        # indexes that go over the number_in_common
        remaining_a_values = list(set(range(smaller_dataset_size, len_filters1)).union(remaining_new_indexes))
        remaining_b_values = list(set(range(smaller_dataset_size, len_filters2)).union(remaining_new_indexes))

        log.debug("Shuffle the remaining indices")
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

        log.debug("Completed creating new permutations for each party")

        dp_ids = get_dataprovider_ids(conn, project_id)

        for i, permutation in enumerate([a_permutation, b_permutation]):
            # We convert here because celery and dicts with int keys don't play nice

            perm_list = convert_mapping_to_list(permutation)
            log.debug("Saving a permutation")

            insert_permutation(conn, dp_ids[i], run_id, perm_list)

        log.debug("Raw permutation data saved. Now saving raw mask")

        # Convert the mask dict to a list of 0/1 ints
        mask_list = convert_mapping_to_list({
                                                int(key): 1 if value else 0
                                                for key, value in mask.items()})
        log.debug("Saving the mask")
        insert_permutation_mask(conn, project_id, run_id, mask_list)
        log.info("Mask saved")
        log.info("Committing database transaction")

    mark_run_complete.delay(run_id, permute_mapping_data.get_serialized_span())
