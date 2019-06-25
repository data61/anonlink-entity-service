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
The result is an xml file for the type 'tests' and 'tutorials', and a JSON file for the type 'benchmark'.

  -p                       Project name (used by docker-compose with '-p'). REQUIRED.
  -o                       Output file where to store the results. [$RESULT_FILE]
  -t                       Docker tag used for the different images. the same tag is used for all of them. [$TAG]
  --type                   Type of tests to run. Either 'tests', 'benchmark' or 'tutorials'. [$TYPE]
  
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
[[ $TYPE != "tests" && $TYPE != "benchmark" && $TYPE != "tutorials" ]] && echoerr "ERROR: Unrecognized type '$TYPE'. Should be equal to 'tests', 'benchmark' or 'tutorials'" && exit 1
export TAG=$TAG

commandPrefix="docker-compose -f tools/docker-compose.yml -f tools/ci.yml --project-directory . "
echo "Initialise the database"
$commandPrefix -p $PROJECT_NAME up db_init > /dev/null 2>&1

if [[ $TYPE == "tests" ]]; then
  CREATED_RESULT_FILE="/var/www/testResults.xml"
elif [[ $TYPE == "benchmark" ]]; then
  CREATED_RESULT_FILE="/app/results.json"
elif [[ $TYPE == "tutorials" ]]; then
  CREATED_RESULT_FILE="/src/testResults.xml"
else
  echo "Unknown type of tests $TYPE"
  exit 1
fi

echo "Start type $TYPE"
$commandPrefix -p $PROJECT_NAME up --abort-on-container-exit --exit-code-from $TYPE db minio redis backend worker nginx $TYPE
exit_code=$?
echo "Retrieve the $TYPE tests results." 
$commandPrefix -p $PROJECT_NAME ps -q $TYPE | xargs -I@ docker cp @:$CREATED_RESULT_FILE $RESULT_FILE

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
