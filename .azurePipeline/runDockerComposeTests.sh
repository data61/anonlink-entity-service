#!/bin/bash

SCRIPT_NAME=$(basename "$0")
TAG="latest"
RESULT_FILE="testResults.xml"
TYPE="test"

help() {
  cat <<EOM
Usage: $SCRIPT_NAME [parameters]

Script ran by the Azure Pipeline to start with docker-compose all the services required
by the entity service and the test or benchmark container, copying the results in a chosen file.
The result is an xml file for the type 'test', and a JSON file for the type 'benchmark'.

  -p                       Project name (used by docker-compose with '-p'). REQUIRED.
  -o                       Output file where to store the results. (Note: not used for the 'tutorials' type) [$RESULT_FILE]
  -t                       Docker tag used for the different images. the same tag is used for all of them. [$TAG]
  --type                   Type of tests to run. Either 'test', 'benchmark' or 'tutorials'. [$TYPE]
  
  -h | --help              Print this message

EOM
}



verbose=1

process_args () {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -p) PROJECT_NAME="$2" && shift 2 ;;
      -o) RESULT_FILE="$2" && shift 2 ;;
      -t) TAG="$2" && shift 2 ;;
      --type) TYPE="$2" && shift 2 ;;

      -h|--help) help; exit 0 ;;
      --dry-run) DRY_RUN=1 && shift ;;
      *) echoerr "ERROR: Unknown cmd or flag '$1'" && help && exit 1 ;;
    esac
  done
}

echoerr () {
  echo 1>&2 "$@"
}


#################################

process_args "$@"
[[ -z $PROJECT_NAME ]] && echoerr "ERROR: Missing project name. Use option '-p'" && exit 1
[[ $TYPE != "test" && $TYPE != "benchmark" ]] && echoerr "ERROR: Unrecognized type '$TYPE'. Should be equal to 'test' or 'benchmark'" && exit 1
export TAG=$TAG

commandPrefix="docker-compose -f tools/docker-compose.yml -f tools/ci.yml --project-directory . "
echo "Initialise the database"
$commandPrefix -p $PROJECT_NAME up db_init > /dev/null 2>&1

if [[ $TYPE == "test" ]]; then
  echo "Start all the services and the tests." 
  $commandPrefix -p $PROJECT_NAME up --abort-on-container-exit --exit-code-from tests db minio redis backend worker nginx tests
  exit_code=$?
  echo "Retrive test results." 
  $commandPrefix -p $PROJECT_NAME ps -q tests | xargs -I@ docker cp @:/var/www/testResults.xml $RESULT_FILE
elif [[ $TYPE == "benchmark" ]]; then
  echo "Start all the services and the benchmark." 
  $commandPrefix -p $PROJECT_NAME up --abort-on-container-exit --exit-code-from benchmark db minio redis backend worker nginx benchmark
  exit_code=$?
  echo "Retrive benchmark results." 
  $commandPrefix -p $PROJECT_NAME ps -q benchmark | xargs -I@ docker cp @:/app/results.json $RESULT_FILE
elif [[ $TYPE == "tutorials" ]]; then
  $commandPrefix -p $PROJECT_NAME up --abort-on-container-exit --exit-code-from tutorials db minio redis backend worker nginx tutorials
else
  echo "Unknown type of tests $TYPE"
  exit 1
fi

echo "Cleaning."
$commandPrefix -p $PROJECT_NAME down -v

exit $exit_code


# Local Variables:
# mode: sh
# tab-width: 2
# sh-basic-offset: 2
# sh-indentation: 2
# indent-tabs-mode: nil
# End:
