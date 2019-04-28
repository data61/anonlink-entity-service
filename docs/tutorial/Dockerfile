# Note we expect the user to mount the sources to build...
# Usage:
# docker run -it -v <PATH TO PROJECT>:/src -v <OUTPUT HTML PATH>:/build quay.io/n1analytics/entity-app:doc-builder
FROM python:3.7

MAINTAINER "Brian Thorne <brian.thorne@data61.csiro.au>"
USER root

RUN pip install --upgrade pip pytest nbval
ADD tutorial-requirements.txt /src/requirements.txt
WORKDIR /src
RUN pip install -U -r requirements.txt
ADD . /src

CMD pytest --nbval-lax /src
