"""
Script to benchmark linkage runs on the entity service.

Configured via environment variables:

- SERVER : the url of the server
- SCHEMA : path to the / a schema file (unused by ES for now, thus can be any json file)
- EXPERIMENT_LIST: list of experiments to run in the form "axb,axc, ..." with a,b,c in ('100k', '1M', '10M')
                    and a <= b. Example: "100Kx100K, 100Kx1M, 1Mx1M"
- TIMEOUT : this timeout defined the time to wait for the result of a run in seconds. Default is 1200 (20min).
"""

import json
import logging
import time
from pprint import pprint
from traceback import format_exc
import pandas as pd
import numpy as np
import arrow
import os
import requests
from clkhash import rest_client

EXP_LOOKUP = {
    '100K': 100000,
    '1M': 1000000,
    '10M': 10000000}

THRESHOLD = 0.85
TIMEOUT = 1200  # in sec
DATA_FOLDER = './data'
logger = logging
logger.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)


def read_env_vars():
    global SERVER, SCHEMA, EXPERIMENT_LIST, TIMEOUT
    try:
        SERVER = os.getenv('SERVER')
        schema_path = os.getenv('SCHEMA', DATA_FOLDER + '/schema.json')
        exp_list = os.getenv('EXPERIMENT_LIST', '')
        TIMEOUT = float(os.getenv('TIMEOUT', TIMEOUT))
        rest_client.server_get_status(SERVER)
        with open(schema_path, 'rt') as f:
            SCHEMA = json.load(f)
        EXPERIMENT_LIST = exp_list.replace(' ', '').upper().split(',')
    except Exception as e:
        raise ValueError(
            'Error loading environment variables!\n'
            ' SERVER: {}, SCHEMA: {}, EXPERIMENT_LIST: {}'.format(SERVER,
                                                                  schema_path,
                                                                  exp_list)) from e


def get_exp_sizes(experiment):
    sizes = experiment.split('X')
    assert len(sizes) == 2
    return EXP_LOOKUP[sizes[0]], EXP_LOOKUP[sizes[1]]


def upload_binary_clks(length_a, length_b, credentials):
    tick = time.perf_counter
    start = tick()

    with open(os.path.join(DATA_FOLDER, "clk_a_{}.bin".format(length_a)), 'rb') as f:
        facs_data = f.read()
    try:
        r = requests.post(
            SERVER + '/api/v1/projects/{}/clks'.format(credentials['project_id']),
            headers={
                'Authorization': credentials['update_tokens'][0],
                'Content-Type': 'application/octet-stream',
                'Hash-Count': str(int(len(facs_data) / 134)),
                'Hash-Size': '128'
            },
            data=facs_data
        )
        logger.debug('upload result: {}'.format(r.json()))
    except Exception as e:
        logger.warning('oh no...\n{}'.format(e))
    logger.info('uploading clks for a took {}'.format(tick() - start))
    start = tick()
    with open(os.path.join(DATA_FOLDER, "clk_b_{}.bin".format(length_b)), 'rb') as f:
        facs_data = f.read()
    try:
        r = requests.post(
            SERVER + '/api/v1/projects/{}/clks'.format(credentials['project_id']),
            headers={
                'Authorization': credentials['update_tokens'][1],
                'Content-Type': 'application/octet-stream',
                'Hash-Count': str(int(len(facs_data) / 134)),
                'Hash-Size': '128'
            },
            data=facs_data
        )
        logger.debug('upload result: {}'.format(r.json()))
    except Exception as e:
        logger.warning('oh no...\n{}'.format(e))
    logger.info('uploading clks for b took {}'.format(tick() - start))


def load_truth(size_a, size_b):
    with open(os.path.join(DATA_FOLDER, f'PII_a_{size_a}.csv'), 'rt') as f:
        dfa = pd.read_csv(f)
        a_ids = dfa['entity_id'].values
    with open(os.path.join(DATA_FOLDER, f'PII_b_{size_b}.csv'), 'rt') as f:
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


def compose_result(status, tt, experiment, sizes):
    tp, tn, fp, fn = tt
    result = {'name': experiment, 'sizes': {'size_a': sizes[0], 'size_b': sizes[1]}, 'status': 'completed',
              'match_results': {'tp': tp, 'tn': tn, 'fp': fp, 'fn': fn}}
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
            rest_client.run_delete(SERVER, credentials['project_id'], run['run_id'], credentials['result_token'])
        rest_client.project_delete(SERVER, credentials['project_id'], credentials['result_token'])
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


def download_data():
    logger.info('Downloading synthetic datasets from S3')
    base = "https://s3-ap-southeast-2.amazonaws.com/n1-data/febrl/"
    download_file_if_not_present(base, DATA_FOLDER, 'schema.json')

    for user in ('a', 'b'):
        for size in ['100K', '1M', '10M']:
            pii_file = f"PII_{user}_{EXP_LOOKUP[size]}.csv"
            clk_file = f"clk_{user}_{EXP_LOOKUP[size]}.bin"
            download_file_if_not_present(base, DATA_FOLDER, pii_file)
            download_file_if_not_present(base, DATA_FOLDER, clk_file)

    logger.info('Downloads complete')


def main():
    try:
        read_env_vars()
        results = {'experiments': []}
        for experiment in EXPERIMENT_LIST:
            try:
                logger.info('running experiment: {}'.format(experiment))
                size_a, size_b = get_exp_sizes(experiment)
                # create project
                credentials = rest_client.project_create(SERVER, SCHEMA, 'mapping', "benchy_{}".format(experiment))
                try:
                    # upload clks
                    upload_binary_clks(size_a, size_b, credentials)
                    # create run
                    run = rest_client.run_create(SERVER, credentials['project_id'], credentials['result_token'],
                                                 THRESHOLD,
                                                 "{}_{}".format(experiment, THRESHOLD))
                    # wait for result
                    run_id = run['run_id']
                    logger.info(f'waiting for run {run_id} to finish')
                    status = rest_client.wait_for_run(SERVER, credentials['project_id'], run['run_id'],
                                                      credentials['result_token'], timeout=TIMEOUT)
                    if status['state'] != 'completed':
                        raise RuntimeError('run did not finish!\n{}'.format(status))
                    logger.info('experiment successful. Evaluating results now...')
                    mapping = rest_client.run_get_result_text(SERVER, credentials['project_id'], run['run_id'],
                                                              credentials['result_token'])
                    mapping = json.loads(mapping)['mapping']
                    mapping = {int(k): int(v) for k, v in mapping.items()}
                    tt = score_mapping(mapping, *load_truth(size_a, size_b))
                    result = compose_result(status, tt, experiment, (size_a, size_b))
                    results['experiments'].append(result)
                    logger.info('cleaning up...')
                    delete_resources(credentials, run)
                except Exception as e:
                    delete_resources(credentials, run)
                    raise e
            except Exception as e:
                e_trace = format_exc()
                logger.warning("experiment '{}' failed: {}".format(experiment, e_trace))
                results['experiments'].append({'name': experiment, 'status': 'ERROR', 'description': e_trace})
    except Exception as e:
        results = {'status': 'ERROR',
                   'description': format_exc()}
        raise e
    pprint(results)


if __name__ == '__main__':
    download_data()
    main()
