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

    try:
        server = os.getenv('SERVER')
        data_path = os.getenv('DATA_PATH', DEFAULT_DATA_FOLDER)
        results_path = os.getenv('RESULTS_PATH', DEFAULT_RESULTS_PATH)
        experiments_file = os.getenv('EXPERIMENT', 'default-experiments.json')

        schema_path = os.getenv('SCHEMA', './schema/default-linking-schema.json')
        timeout = float(os.getenv('TIMEOUT', DEFAULT_TIMEOUT))

        experiments = load_experiments(experiments_file)

        return {
            'server': server,
            'experiments': experiments,
            'timeout': timeout,
            'schema_path': schema_path,
            'data_path': data_path,
            'data_base_url': "https://s3-ap-southeast-2.amazonaws.com/n1-data/febrl/",
            'results_path': results_path
        }
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
    data_path = config['data_path']
    with open(os.path.join(data_path, f'PII_a_{size_a}.csv'), 'rt') as f:
        dfa = pd.read_csv(f)
        a_ids = dfa['entity_id'].values
    with open(os.path.join(data_path, f'PII_b_{size_b}.csv'), 'rt') as f:
        dfb = pd.read_csv(f)
        b_ids = dfb['entity_id'].values
    mask_a = np.isin(a_ids, b_ids)
    mask_b = np.isin(b_ids, a_ids)
    return a_ids, b_ids, mask_a, mask_b


def score_mapping(mapping, truth_a, truth_b, mask_a, mask_b):
    tp = fp = tn = fn = 0

    for idx in range(len(truth_a)):
        if idx in mapping.keys():
            if mask_a[idx]:
                if truth_a[idx] == truth_b[mapping[idx]]:
                    tp += 1
                else:
                    fp += 1
            else:
                fp += 1
        else:
            if mask_a[idx]:
                fn += 1
            else:
                tn += 1
    return tp, tn, fp, fn


def compose_result(status, tt, experiment, sizes, threshold):
    tp, tn, fp, fn = tt
    result = {'experiment': experiment,
              'threshold': threshold,
              'sizes': {
                  'size_a': sizes[0],
                  'size_b': sizes[1]
              },
              'status': 'completed',
              'match_results': {'tp': tp, 'tn': tn, 'fp': fp, 'fn': fn}
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
        try:
            threshold = experiment['threshold']
            logger.info('running experiment: {}'.format(experiment))
            size_a, size_b = get_exp_sizes(experiment)
            # create project
            credentials = rest_client.project_create(server, config['schema'], 'mapping', "benchy_{}".format(experiment))
            try:
                # upload clks
                upload_binary_clks(config, size_a, size_b, credentials)
                # create run
                run = rest_client.run_create(server, credentials['project_id'], credentials['result_token'],
                                             threshold,
                                             "{}_{}".format(experiment, threshold))
                # wait for result
                run_id = run['run_id']
                logger.info(f'waiting for run {run_id} to finish')
                status = rest_client.wait_for_run(server, credentials['project_id'], run['run_id'],
                                                  credentials['result_token'], timeout=config['timeout'])
                if status['state'] != 'completed':
                    raise RuntimeError('run did not finish!\n{}'.format(status))
                logger.info('experiment successful. Evaluating results now...')
                mapping = rest_client.run_get_result_text(server, credentials['project_id'], run['run_id'],
                                                          credentials['result_token'])
                mapping = json.loads(mapping)['mapping']
                mapping = {int(k): int(v) for k, v in mapping.items()}
                tt = score_mapping(mapping, *load_truth(config, size_a, size_b))
                result = compose_result(status, tt, experiment, (size_a, size_b), threshold)
                results['experiments'].append(result)
                logger.info('cleaning up...')
                delete_resources(config, credentials, run)
            except Exception as e:
                delete_resources(config, credentials, run)
                raise e
        except Exception as e:
            e_trace = format_exc()
            logger.warning("experiment '{}' failed: {}".format(experiment, e_trace))
            results['experiments'].append({'name': experiment, 'status': 'ERROR', 'description': e_trace})
    return results


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


if __name__ == '__main__':
    main()
