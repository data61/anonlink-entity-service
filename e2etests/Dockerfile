ARG VERSION=latest
FROM data61/anonlink-base:${VERSION}

WORKDIR /var/www
ADD . /var/www/e2etests

RUN python -c "import anonlink; print('anonlink version:', anonlink.__version__)" && \
    python -c "import clkhash; print('clkhash version:', clkhash.__version__)"

ENV SERVER http://nginx:8851
ENV INITIAL_DELAY 20
CMD python -m pytest -n 2 e2etests/tests --junitxml=testResults.xml -x
