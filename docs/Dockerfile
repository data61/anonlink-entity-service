# This Dockerfile does not anything. It only pulls the required dependencies to be able to build the documentation when creating the frontend image.
# If updated, it needs to be pushed manually to dockerhub.
FROM python:3.8

MAINTAINER "Brian Thorne <brian.thorne@data61.csiro.au>"
USER root

RUN (pip install --upgrade pip setuptools; \
     apt-get update; \
     apt-get --assume-yes install \
        libmpc-dev build-essential libyajl-dev libyajl2 libstdc++6 pandoc dvipng texlive-extra-utils)

ADD doc-requirements.txt /src/requirements.txt

WORKDIR /src
RUN pip install -U -r requirements.txt
