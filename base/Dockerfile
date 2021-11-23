FROM alpine:3.14.3

ENV DOCKERIZE_VERSION v0.6.1
RUN wget https://github.com/jwilder/dockerize/releases/download/$DOCKERIZE_VERSION/dockerize-alpine-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && tar -C /usr/local/bin -xzvf dockerize-alpine-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && rm dockerize-alpine-linux-amd64-$DOCKERIZE_VERSION.tar.gz

# postgresql-dev needed for pg_config
# c compiler, python-dev, libpq, libpq-dev needed by psycopg2 (https://www.psycopg.org/docs/install.html)
# libffi-dev needed by anonlink
# g++ needed by anonlink/cffi
# yajl, yajl-dev needed by ijson
# gmp-dev, mpfr-dev, mpc1-dev needed by gmpy2
# openssl-dev, cargo needed by cryptography (https://cryptography.io/en/latest/installation.html#alpine)
WORKDIR /var/www
ADD requirements.txt /var/www/requirements.txt
RUN apk add --no-cache \
    python3 \
    py3-pip\
    libstdc++ \
    mpc1-dev \
    yajl \
    libpq \
    openssl-dev \
    cargo && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    apk add --no-cache --virtual .build-deps \
    g++ \
    python3-dev \
    yajl-dev \
    postgresql-dev \
    libffi-dev \
    gmp-dev \
    mpfr-dev \
    wait4ports \
    git && \
    pip install setuptools wheel && \
    python -m pip install --upgrade pip && \
    pip install --upgrade -r requirements.txt && \
    apk del --no-cache .build-deps && \
    rm -fr /tmp/* /var/cache/apk/* /root/.cache/pip

RUN adduser -D -H -h /var/www user && \
    chown user:user /var/www /var/log
USER user
