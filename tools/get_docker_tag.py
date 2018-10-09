"""
This Python script outputs the tag for the entity service images depending on the git branch.

    $ python get_docker_tag.py <BRANCH> <app|nginx|benchmark>
    tag


Example:
    $ python get_docker_tag.py feature-fix-x nginx
    v1.4.0-feature-fix-x

"""

import sys
import os.path


def get_version(image):
    assert image in {'app', 'nginx', 'benchmark'}
    if image == 'app':
        file_path = os.path.abspath(os.path.join(__file__, os.path.pardir, os.path.pardir, 'backend', 'entityservice', 'VERSION'))
    elif image == 'nginx':
        file_path = os.path.abspath(os.path.join(__file__, os.path.pardir, os.path.pardir, 'frontend', 'VERSION'))
    elif image == 'benchmark':
        file_path = os.path.abspath(os.path.join(__file__, os.path.pardir, os.path.pardir, 'benchmarking', 'VERSION'))
    return open(file_path).read().strip()


if __name__ == '__main__':
    git_branch = sys.argv[1]
    image = sys.argv[2]
    version = get_version(image)
    if git_branch == 'master':
        print(version)
    else:
        print('-'.join([version, git_branch]))
