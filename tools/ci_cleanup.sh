#!/usr/bin/env bash

set -e
cd $(dirname "$0")

docker-compose -f docker-compose.yml -p entityservicetest down -v

# Raise the exit code of the tests
exit_code=`docker inspect --format='{{.State.ExitCode}}' entityservicetest_tests_1`

docker-compose -f docker-compose.yml -f ci.yml -p entityservicetest down -v

exit "$exit_code"
