#!/usr/bin/env bash

# This creates a source release

set -e
cd $(dirname "$0")
export APPVERSION=$(cat ../backend/VERSION)

rm -fr /tmp/n1-es
mkdir /tmp/n1-es

cp -r .. /tmp/n1-es
rm -fr /tmp/n1-es/.git*
rm -fr /tmp/n1-es/.idea
rm -fr /tmp/n1-es/*.iml
rm -fr /tmp/n1-es/.ipynb*
rm -fr /tmp/n1-es/docs/*

# Release should include docs. Current approach is to build them in a top level directory before
# running make-release.sh - e.g. using:
#docker run -v `pwd`/../docs:/src -v /tmp/n1-es/docs:/build quay.io/n1analytics/entity-app:doc-builder

cd /tmp/n1-es
find . | grep -E "(__pycache__|\.pyc)" | xargs rm -fr

zip -q -r /tmp/n1-es-$APPVERSION.zip .

