#!/usr/bin/env bash
set -e
cd $(dirname "$0")

git submodule init
git submodule update
