#!/usr/bin/env python3

"""
The script will currently be used in the Azure Pipeline to get back the logs of the pods when a test is failing
allowing developers to document the issue.
"""

import colors
import json
from pathlib import Path
import subprocess
import sys

# The namespace is not configurable as we are expected to run this script only in Azure Dev-Ops which deployed the
# service only in this namespace.
NAMESPACE = "test-azure"


def get_list_pods(_release_name):
    cmd = "kubectl --namespace {} get pods -l release={} -o json".format(NAMESPACE, _release_name)
    r = subprocess.run(cmd.split(" "), capture_output=True)
    items_from_release = json.loads(r.stdout)['items']
    return items_from_release


def get_logs_container(container_info, file, previous=False):
    cmd = "kubectl --namespace {} logs {} {}".format(NAMESPACE, container_info['full_pod_name'], container_info['name'])
    if previous:
        cmd += " --previous"
    output = subprocess.run(cmd.split(" "), capture_output=True)
    # The returned logs contain colored characters. So use ansicolors to strip them out before writing them to file.
    file.write(colors.strip_color(output.stdout.decode("utf-8")))


def info_from_pod(_pod, _directory, _release_name):
    pod_name = _pod.get('metadata').get('name')
    list_containers = _pod.get('status').get('containerStatuses')
    for container in list_containers:
        name_container = container.get('name')
        restart_count = container.get('restartCount')
        image_name = container.get('image')
        prefix_to_remove = "{}-".format(_release_name)
        info = {'full_pod_name': pod_name, 'short_pod_name': pod_name[len(prefix_to_remove):],
                'name': name_container, 'image': image_name, 'restart_count': restart_count}
        
        with open(_directory / 'pod-{}_container-{}.log'.format(info['short_pod_name'], info['name']), 'wt') as f:
            json.dump(info, f, indent=2, sort_keys=True)
            f.write('\n\n')
        with open(_directory / 'pod-{}_container-{}.log'.format(info['short_pod_name'], info['name']), 'at') as f:
            get_logs_container(info, f)
        if restart_count > 0:
            with open(_directory / 'pod-{}_container-{}-previous.log'.format(info['short_pod_name'], info['name']), 'at') as f:
                get_logs_container(info, f, previous=True)


def main():
    """
    Main method of this script. It requires two arguments: a path where to store the logs from the pods, and the release
    name. The release name is used to get the list of pods from the selected release.
    """
    if len(sys.argv) < 3:
        raise ValueError("Missing arguments to select the folder where to store the logs and the release name.")
    if len(sys.argv) > 3:
        raise ValueError("Too many arguments provided to the method. Only folder where to store the"
                         " logs and the release name are required.")
    directory = Path(sys.argv[1])
    release_name = sys.argv[2]
    list_pods = get_list_pods(release_name)
    for pod in list_pods:
        info_from_pod(pod, directory, release_name)


if __name__ == '__main__':
    main()
