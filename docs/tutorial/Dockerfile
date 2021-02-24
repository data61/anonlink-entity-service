FROM python:3.7

MAINTAINER "Brian Thorne <brian.thorne@data61.csiro.au>"
USER root

ENV DOCKERIZE_VERSION v0.6.1
RUN wget https://github.com/jwilder/dockerize/releases/download/$DOCKERIZE_VERSION/dockerize-alpine-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && tar -C /usr/local/bin -xzvf dockerize-alpine-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && rm dockerize-alpine-linux-amd64-$DOCKERIZE_VERSION.tar.gz

RUN python -m pip install --upgrade pip
RUN pip install --upgrade pytest nbval
ADD tutorial-requirements.txt /src/requirements.txt
WORKDIR /src
RUN pip install -U -r requirements.txt
ADD . /src
ENTRYPOINT /bin/sh
