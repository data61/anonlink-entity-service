# Usage
# # docker run -it -v <PATH TO DOCS>:/docs -v <OUTPUT HTML PATH>:/build quay.io/n1analytics/entity-app:doc-builder
FROM quay.io/n1analytics/entity-app:latest

MAINTAINER "Brian Thorne <brian.thorne@data61.csiro.au>"
USER root
RUN apt-get update \
  && apt-get install --no-install-recommends --no-install-suggests -y \
	pandoc dvipng texlive-extra-utils \
  && rm -rf /var/lib/apt/lists/*

ADD doc-requirements.txt /src/requirements.txt

WORKDIR /src
RUN pip install -U -r requirements.txt
USER user

# Note we expect the user to mount the sources to build...
#ADD . /src

CMD python -m sphinx /src /build
