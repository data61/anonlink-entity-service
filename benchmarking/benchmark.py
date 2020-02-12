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
import arrow
import boto3
import copy
import json
import jsonschema
import logging
import pandas as pd
import requests
import time
import os

from anonlinkclient.rest_client import RestClient
from pprint import pprint
from traceback import format_exc


EXP_LOOKUP = {
    '10K': 10_000,
    '100K': 100_000,
    '1M': 1_000_000,
    '10M': 10_000_000
}

SIZE_PER_CLK = 128  # As per serialization.py.

logger = logging
logger.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)

rest_client = RestClient(os.getenv('SERVER'))


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
    DEFAULT_DATA_FOLDER = '/tmp/data'
    DEFAULT_RESULTS_PATH = 'results.json'

    DEFAULT_OBJECT_STORE_BUCKET = 'anonlink-benchmark-results'

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
            'data_base_url': "https://public-linkage-data.s3-ap-southeast-2.amazonaws.com/febrl/",
            'results_path': results_path
        }

        if 'OBJECT_STORE_BUCKET' in os.environ:
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
    assert len(sizes) >= 2
    return [EXP_LOOKUP[size] for size in sizes]


def upload_binary_clks(config, sizes, credentials):
    data_path = config['data_path']
    server = config['server']
    tick = time.perf_counter

    def upload_data(participant, auth_token, clk_length):
        start = tick()

        file_name = os.path.join(data_path, "{}Parties".format(len(sizes)),
                                 "clk_{}_{}_v2.bin".format(participant, clk_length))
        with open(file_name, 'rb') as f:
            facs_data = f.read()
        assert len(facs_data) % SIZE_PER_CLK == 0
        try:
            r = requests.post(
                server + '/api/v1/projects/{}/binaryclks'.format(credentials['project_id']),
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

    assert len(sizes) == len(credentials['update_tokens'])
    for participant_id in range(len(sizes)):
        # participant's name starts from the letter `a` to be back portable.
        upload_data(chr(97 + participant_id), credentials['update_tokens'][participant_id], sizes[participant_id])


def load_truth(config, sizes):
    data_path = config['data_path']
    nb_parties = len(sizes)
    groups = {}
    folder = os.path.join(data_path, "{}Parties".format(nb_parties))

    # In this loop, we are creating a dictionary where the key is the entity_id read from the datasets, and the value
    # is an array of size the number of participants for which its value at the index i is the row number of this entity
    # in the dataset i. The value is -1 if not present in the corresponding dataset.
    for i in range(nb_parties):
        file_name = os.path.join(folder, 'PII_{}_{}.csv'.format(chr(97 + i), sizes[i]))
        with open(os.path.join(data_path, file_name), 'rt') as f:
            csv_content = pd.read_csv(f, usecols=['entity_id'])
            for idx, entity_id in csv_content.itertuples():
                if entity_id not in groups:
                    groups[entity_id] = [-1] * nb_parties
                groups[entity_id][i] = idx

    # Now filter all the entities which are non matched, i.e. they are present only in a single dataset
    # We filter them because the group results that the entity service is creating does not include them.
    matched_entities_only = filter(lambda x: len([y for y in groups[x] if y > -1]) > 1, groups)
    # Finally, map this dictionary into a list of tuples, where the tuples are built from the values in the dictionary
    # (We drop the key which has no reason anymore).
    return map(lambda x: tuple(groups[x]), matched_entities_only)


def score_accuracy(groups, truth_groups, nb_parties):

    def group_transform(group):
        """
        Transform a group provided by the entity service into a tuple of size the number of participants. The ith
        element of the tuple is equal to the entity's row in the dataset i. The value is -1 if the entity is not in the
        dataset.

        :param group: List of 2 elements array representing a matched entity where each element (x, y) of the list
         means that the entity is in the dataset x in the row y.
        """
        result = [-1] * nb_parties
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
              'sizes': sizes_dic,
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


def delete_resources(credentials, run):
    try:
        if run is not None and 'run_id' in run:
            rest_client.run_delete(credentials['project_id'], run['run_id'], credentials['result_token'])
        rest_client.project_delete(credentials['project_id'], credentials['result_token'])
    except Exception as e:
        logger.warning('Error while deleting resources... {}'.format(e))


def download_file_if_not_present(url_base, local_base, filename):
    os.makedirs(local_base, exist_ok=True)
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
    On S3, the data is organised in folders for the number of parties (e.g. folder `3Parties` for the data related to
    the 3 party linkage), and then a number a file following the format `PII_{user}_{size_data}.csv`, `clk_{user}_{size_data}_v2.bin`
    and `clk_{user}_{size_data}.json` where $user is a letter starting from `a` indexing the data owner, and `size_data`
    is a integer representing the number of data rows in the dataset (e.g. 10000). Note that the csv usually has a header.

    The data is stored in the folder provided from the configuration, following the same structure as the one on S3.
    """
    logger.info('Downloading synthetic datasets from S3')
    base = config['data_base_url']
    data_folder = config['data_path']
    os.makedirs(data_folder, exist_ok=True)
    download_file_if_not_present(base, data_folder, 'schema.json')

    to_download = {}
    for experiment in config['experiments']:
        nb_parties = len(experiment['sizes'])
        if nb_parties in to_download:
            to_download[nb_parties].update(set(experiment['sizes']))
        else:
            to_download[nb_parties] = set(experiment['sizes'])

    for nb_parties in to_download:
        folder = os.path.join(base, "{}Parties/".format(nb_parties))
        local_data_folder = os.path.join(data_folder, "{}Parties/".format(nb_parties))

        sizes = to_download[nb_parties]
        for user in [chr(x + 97) for x in range(nb_parties)]:
            for size in sizes:
                pii_file = f"PII_{user}_{EXP_LOOKUP[size]}.csv"
                clk_file = f"clk_{user}_{EXP_LOOKUP[size]}_v2.bin"
                download_file_if_not_present(folder, local_data_folder, pii_file)
                download_file_if_not_present(folder, local_data_folder, clk_file)

    logger.info('Downloads complete')


def run_experiments(config):
    """
        Run all the experiments specified in the configuration.
    """
    rest_client.server_get_status()

    results = {'experiments': []}
    for experiment in config['experiments']:
        repetition = experiment['repetition']
        threshold = experiment['threshold']
        sizes = get_exp_sizes(experiment)

        for rep in range(repetition):
            current_experiment = copy.deepcopy(experiment)
            current_experiment['rep'] = rep + 1
            logger.info('running experiment: {}'.format(current_experiment))
            if repetition != 1:
                logger.info('\trepetition {} out of {}'.format(rep + 1, repetition))
            result = run_single_experiment(config, threshold, sizes, current_experiment)
            results['experiments'].append(result)

    return results


def run_single_experiment(config, threshold, sizes, experiment):
    result = {}
    credentials = {}
    run = {}
    logger.info("Starting time: {}".format(time.asctime()))
    nb_parties = len(sizes)
    try:
        credentials = rest_client.project_create(config['schema'], 'groups',
                                                 "benchy_{}".format(experiment), parties=nb_parties)
        # upload clks
        upload_binary_clks(config, sizes, credentials)
        # create run
        project_id = credentials['project_id']
        result['project_id'] = project_id
        run = rest_client.run_create(project_id, credentials['result_token'],
                                     threshold,
                                     "{}_{}".format(experiment, threshold))
        # wait for result
        run_id = run['run_id']
        result['run_id'] = run_id
        logger.info(f'waiting for run {run_id} from the project {project_id} to finish')
        status = rest_client.wait_for_run(project_id, run_id,
                                          credentials['result_token'], timeout=config['timeout'], update_period=5)
        if status['state'] != 'completed':
            raise RuntimeError('run did not finish!\n{}'.format(status))
        logger.info('experiment successful. Evaluating results now...')
        groups = rest_client.run_get_result_text(project_id, run_id, credentials['result_token'])
        groups = json.loads(groups)['groups']
        truth_groups = load_truth(config, sizes)
        tt = score_accuracy(groups, truth_groups, nb_parties)
        result.update(compose_result(status, tt, experiment, sizes, threshold))
    except Exception:
        e_trace = format_exc()
        logger.warning("experiment '{}' failed: {}".format(experiment, e_trace))
        result.update({'name': experiment, 'status': 'ERROR', 'description': e_trace})
    finally:
        logger.info('cleaning up...')
        delete_resources(credentials, run)

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
    logger.info('Results saved in file: {}'.format(result_file_name))


def main():
    config = read_config()
    server_status = rest_client.server_get_status()
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
