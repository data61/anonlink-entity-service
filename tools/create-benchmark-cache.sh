#!/usr/bin/env bash

docker volume inspect linkage-benchmark-data &> /dev/null
if [ \$? -eq 0 ];
then
  echo "Volume exists"
else
  echo "Creating linkage-benchmark-data volume"
  docker volume create linkage-benchmark-data
fi
