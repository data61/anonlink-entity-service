#!/usr/bin/env bash
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

sphinx-build -b html ../docs /tmp/n1-es/docs

cd /tmp/n1-es
find . | grep -E "(__pycache__|\.pyc)" | xargs rm -fr

zip -r /tmp/n1-es-$APPVERSION.zip .
tar cf /tmp/n1-es-$APPVERSION.tar.lzma --lzma .
