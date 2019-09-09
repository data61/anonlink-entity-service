"""
Script to benchmark linkage runs on the entity service.

Configured via environment variables:

- SERVER: (required) the url of the server.
- EXPERIMENT: json file containing a list of experiments to run. Schema of experiments is
  defined in `./schema/experiments.json`.
- DATA_PATH: path to a directory to store test data (useful to cache).
- RESULT_PATH: full filename to write results file.
- SCHEMA: path to the linkage schema file used when creating projects. If not provided it is assumed
  to be in the data directory.
- TIMEOUT : this timeout defined the time to wait for the result of a run in seconds. Default is 1200 (20min).

"""
import boto3
import copy
import json
import logging
import time
from pprint import pprint
from traceback import format_exc
import os

import pandas as pd
import numpy as np
import arrow
import requests
from clkhash import rest_client
import jsonschema


EXP_LOOKUP = {
    '100K': 100000,
    '1M': 1000000,
    '10M': 10000000
}

SIZE_PER_CLK = 128  # As per serialization.py.

logger = logging
logger.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)


def load_experiments(filepath):

    with open(os.path.join('schema', 'experiments.json'), 'rt') as f:
        experiment_schema = json.load(f)

    with open(filepath, 'rt') as f:
        experiments = json.load(f)

    for experiment in experiments:
        if 'repetition' not in experiment:
            experiment['repetition'] = 1

    jsonschema.validate(experiments, experiment_schema)

    return experiments


def read_config():

    # Defaults
    DEFAULT_TIMEOUT = 1200  # in sec
    DEFAULT_DATA_FOLDER = './data'
    DEFAULT_RESULTS_PATH = 'results.json'

    DEFAULT_OBJECT_STORE_BUCKET = 'anonlink-benchmark-result'

    try:
        server = os.getenv('SERVER')
        data_path = os.getenv('DATA_PATH', DEFAULT_DATA_FOLDER)
        results_path = os.getenv('RESULTS_PATH', DEFAULT_RESULTS_PATH)
        experiments_file = os.getenv('EXPERIMENT', 'default-experiments.json')

        schema_path = os.getenv('SCHEMA', './schema/default-linking-schema.json')
        timeout = float(os.getenv('TIMEOUT', DEFAULT_TIMEOUT))

        experiments = load_experiments(experiments_file)

        config = {
            'server': server,
            'experiments': experiments,
            'timeout': timeout,
            'schema_path': schema_path,
            'data_path': data_path,
            'data_base_url': "https://s3-ap-southeast-2.amazonaws.com/n1-data/febrl/",
            'results_path': results_path
        }

        if 'OBJECT_STORE_ACCESS_KEY' in os.environ:
            object_store_server = os.getenv('OBJECT_STORE_SERVER')
            object_store_access_key = os.getenv('OBJECT_STORE_ACCESS_KEY')
            object_store_secret_key = os.getenv('OBJECT_STORE_SECRET_KEY')
            object_store_bucket = os.getenv('OBJECT_STORE_BUCKET', DEFAULT_OBJECT_STORE_BUCKET)
            config.update({
                'push_to_object_store': True,
                'object_store_server': object_store_server,
                'object_store_access_key': object_store_access_key,
                'object_store_secret_key': object_store_secret_key,
                'object_store_bucket': object_store_bucket
            })
        else:
            config['push_to_object_store'] = False

        return config
    except Exception as e:
        raise ValueError(
            'Error loading environment variables!\n'
            'ENV: {}'.format(os.environ)) from e


def get_exp_sizes(experiment):
    sizes = experiment['sizes']
    assert len(sizes) == 2
    return EXP_LOOKUP[sizes[0]], EXP_LOOKUP[sizes[1]]


def upload_binary_clks(config, length_a, length_b, credentials):
    data_path = config['data_path']
    server = config['server']
    tick = time.perf_counter

    def upload_data(participant, auth_token, clk_length):
        start = tick()

        with open(os.path.join(data_path, "clk_{}_{}_v2.bin".format(participant, clk_length)), 'rb') as f:
            facs_data = f.read()
        assert len(facs_data) % SIZE_PER_CLK == 0
        try:
            r = requests.post(
                server + '/api/v1/projects/{}/clks'.format(credentials['project_id']),
                headers={
                    'Authorization': auth_token,
                    'Content-Type': 'application/octet-stream',
                    'Hash-Count': str(len(facs_data) // SIZE_PER_CLK),
                    'Hash-Size': '128'
                },
                data=facs_data
            )
            logger.debug('upload result: {}'.format(r.json()))
        except Exception as e:
            logger.warning('oh no...\n{}'.format(e))
        logger.info('uploading clks for {} took {:.3f}'.format(participant, tick() - start))

    upload_data('a', credentials['update_tokens'][0], length_a)
    upload_data('b', credentials['update_tokens'][1], length_b)


def load_truth(config, size_a, size_b):
    nb_parties = 2
    groups = {}
    data_path = config['data_path']

    def read_values_from_csv(file, solution_index):
        csv_content = pd.read_csv(file, usecols=['entity_id'])
        for idx, entity_id in csv_content.itertuples():
            if entity_id not in groups:
                groups[entity_id] = [-1] * nb_parties
            groups[entity_id][solution_index] = idx

    with open(os.path.join(data_path, f'PII_a_{size_a}.csv'), 'rt') as f:
        read_values_from_csv(f, 0)

    with open(os.path.join(data_path, f'PII_b_{size_b}.csv'), 'rt') as f:
        read_values_from_csv(f, 1)

    # Now filter all the entities which are non matched, i.e. they are present only in a single dataset
    # We filter them because the group results that the entity service is creating does not include them.
    matched_entities_only = filter(lambda x: len([y for y in groups[x] if y > -1]) > 1, groups)
    # Finally, map this dictionary into a list of tuples, where the tuples are built from the values in the dictionary
    # (We drop the key which has no reason anymore).
    return map(lambda x: tuple(groups[x]), matched_entities_only)


def score_accuracy(groups, truth_groups):

    def group_transform(group):
        """
        Transform a group provided by the entity service into a tuple of size the number of participants. The ith
        element of the tuple is equal to the entity's row in the dataset i. The value is -1 if the entity is not in the
        dataset.

        :param group: List of 2 elements array representing a matched entity where each element (x, y) of the list
         means that the entity is in the dataset x in the row y.
        """
        result = [-1] * 2
        for link in group:
            result[link[0]] = link[1]
        return tuple(result)

    transformed_groups = [group_transform(group) for group in groups]

    # Now everything is in a good form, let's use sets to do an intersection.
    # Current computed values are:
    # - positives: all the groups which have been computed by the entity service and which are in the ground truth
    #       (exact group, not counting parts of groups),
    # - negatives: number of groups in the ground truth which have not been found by the entity service,
    # - false_positives: number of groups which have been found by the entity service but shouldn't have been.
    truth_groups_set = set(truth_groups)
    positives = len(truth_groups_set.intersection(set(transformed_groups)))
    negatives = len(truth_groups_set) - positives
    false_positives = len(transformed_groups) - positives
    return positives, negatives, false_positives


def compose_result(status, tt, experiment, sizes, threshold):
    positives, negatives, false_positives = tt
    sizes_dic = {'size_{}'.format(chr(97 + i)): sizes[i] for i in range(len(sizes))}
    # Compute the accuracy, i.e. number of positives divided by the number of matched entities in the ground
    # truth (positives + negatives)
    accuracy = positives / (positives + negatives)
    result = {'experiment': experiment,
              'threshold': threshold,
              'sizes': {
                  'size_a': sizes[0],
                  'size_b': sizes[1]
              },
              'status': 'completed',
              'groups_results': {'positives': positives, 'negatives': negatives, 'false_positives': false_positives,
                                 'accuracy': accuracy}
              }
    timings = {'started': status['time_started'], 'added:': status['time_added'], 'completed': status['time_completed']}
    start = arrow.get(status['time_started']).datetime
    end = arrow.get(status['time_completed']).datetime
    delta = end - start
    timings['runtime'] = delta.total_seconds()
    result['timings'] = timings
    return result


def delete_resources(config, credentials, run):
    try:
        if run is not None and 'run_id' in run:
            rest_client.run_delete(config['server'], credentials['project_id'], run['run_id'], credentials['result_token'])
        rest_client.project_delete(config['server'], credentials['project_id'], credentials['result_token'])
    except Exception as e:
        logger.warning('Error while deleting resources... {}'.format(e))


def download_file_if_not_present(url_base, local_base, filename):
    local_path = os.path.join(local_base, filename)
    if os.path.exists(local_path):
        logger.debug(f'Skipping already downloaded file: {filename}')
    else:
        logger.info(f'Downloading {filename} to {local_base}')
        response = requests.get(url_base + filename, stream=True)
        assert response.status_code == 200, f"{response.status_code} was not 200"

        with open(local_path, 'wb') as f:
            for chunk in response:
                f.write(chunk)


def download_data(config):
    """
    Download data used in the configured experiments.

    """
    logger.info('Downloading synthetic datasets from S3')
    base = config['data_base_url']
    data_folder = config['data_path']
    os.makedirs(data_folder, exist_ok=True)
    download_file_if_not_present(base, data_folder, 'schema.json')

    sizes = set()
    for experiment in config['experiments']:
        sizes.update(set(experiment['sizes']))
    for user in ('a', 'b'):
        for size in sizes:
            pii_file = f"PII_{user}_{EXP_LOOKUP[size]}.csv"
            clk_file = f"clk_{user}_{EXP_LOOKUP[size]}_v2.bin"
            download_file_if_not_present(base, data_folder, pii_file)
            download_file_if_not_present(base, data_folder, clk_file)

    logger.info('Downloads complete')


def run_experiments(config):
    server = config['server']
    rest_client.server_get_status(server)

    results = {'experiments': []}
    for experiment in config['experiments']:
        repetition = experiment['repetition']
        threshold = experiment['threshold']
        size_a, size_b = get_exp_sizes(experiment)

        for rep in range(repetition):
            current_experiment = copy.deepcopy(experiment)
            current_experiment['rep'] = rep + 1
            logger.info('running experiment: {}'.format(current_experiment))
            if repetition != 1:
                logger.info('\trepetition {} out of {}'.format(rep + 1, repetition))
            result = run_single_experiment(server, config, threshold, size_a, size_b, current_experiment)
            results['experiments'].append(result)

    return results


def run_single_experiment(server, config, threshold, size_a, size_b, experiment):
    result = {}
    credentials = {}
    run = {}
    logger.info("Starting time: {}".format(time.asctime()))
    try:
        credentials = rest_client.project_create(server, config['schema'], 'groups',
                                                 "benchy_{}".format(experiment), parties=2)
        # upload clks
        upload_binary_clks(config, size_a, size_b, credentials)
        # create run
        project_id = credentials['project_id']
        result['project_id'] = project_id
        run = rest_client.run_create(server, project_id, credentials['result_token'],
                                     threshold,
                                     "{}_{}".format(experiment, threshold))
        # wait for result
        run_id = run['run_id']
        result['run_id'] = run_id
        logger.info(f'waiting for run {run_id} from the project {project_id} to finish')
        status = rest_client.wait_for_run(server, project_id, run_id,
                                          credentials['result_token'], timeout=config['timeout'])
        if status['state'] != 'completed':
            raise RuntimeError('run did not finish!\n{}'.format(status))
        logger.info('experiment successful. Evaluating results now...')
        groups = rest_client.run_get_result_text(server, project_id, run_id, credentials['result_token'])
        groups = json.loads(groups)['groups']
        truth_groups = load_truth(config, size_a, size_b)
        tt = score_accuracy(groups, truth_groups)
        result.update(compose_result(status, tt, experiment, (size_a, size_b), threshold))
    except Exception as e:
        e_trace = format_exc()
        logger.warning("experiment '{}' failed: {}".format(experiment, e_trace))
        result.update({'name': experiment, 'status': 'ERROR', 'description': e_trace})
    finally:
        logger.info('cleaning up...')
        delete_resources(config, credentials, run)

    logger.info("Ending time: {}".format(time.asctime()))
    return result


def push_to_object_store(config):
    experiment_file = config['results_path']
    endpoint_url = config['object_store_server']
    object_store_access_key = config['object_store_access_key']
    object_store_secret_key = config['object_store_secret_key']
    object_store_bucket = config['object_store_bucket']
    logger.info('Pushing the results to {}, in the bucket {}'.format('s3' if endpoint_url is None else endpoint_url,
                                                                     object_store_bucket))
    client = boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=object_store_access_key,
        aws_secret_access_key=object_store_secret_key
    )
    result_file_name = "benchmark_results-{}.json".format(time.strftime("%Y%m%d-%H%M%S"))
    client.upload_file(experiment_file, object_store_bucket, result_file_name)


def main():
    config = read_config()
    server_status = rest_client.server_get_status(config['server'])
    version = requests.get(config['server'] + "/api/v1/version").json()
    logger.info(server_status)
    download_data(config)

    with open(config['schema_path'], 'rt') as f:
        schema = json.load(f)
        config['schema'] = schema

    try:
        results = run_experiments(config)
    except Exception as e:
        results = {'status': 'ERROR', 'description': format_exc()}
        raise e
    finally:
        results['server'] = config['server']
        results['version'] = version

        pprint(results)
        with open(config['results_path'], 'wt') as f:
            json.dump(results, f)
        if config['push_to_object_store']:
            push_to_object_store(config)


if __name__ == '__main__':
    main()
