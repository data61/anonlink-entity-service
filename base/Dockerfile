FROM alpine:3.12.0

ENV DOCKERIZE_VERSION v0.6.1
RUN wget https://github.com/jwilder/dockerize/releases/download/$DOCKERIZE_VERSION/dockerize-alpine-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && tar -C /usr/local/bin -xzvf dockerize-alpine-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && rm dockerize-alpine-linux-amd64-$DOCKERIZE_VERSION.tar.gz

# Search for current versions at
# https://pkgs.alpinelinux.org/packages?name=libpq&branch=v3.11&arch=x86_64
# postgresql-dev needed for pg_config
# c compiler, python-dev, libpq, libpq-dev needed by psycopg2 (https://www.psycopg.org/docs/install.html)
# libffi-dev needed by anonlink
# g++ needed by anonlink/cffi
# yajl, yajl-dev needed by ijson
# gmp-dev, mpfr-dev, mpc1-dev needed by gmpy2
WORKDIR /var/www
ADD requirements.txt /var/www/requirements.txt
RUN apk add --no-cache \
    python3=3.8.3-r0 \
    py3-pip=20.1.1-r0 \
    libstdc++=9.3.0-r2 \
    mpc1-dev=1.1.0-r1 \
    yajl=2.1.0-r1 \
    libpq=12.3-r2 && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    apk add --no-cache --virtual .build-deps \
    g++=9.3.0-r2 \
    python3-dev=3.8.3-r0 \
    yajl-dev=2.1.0-r1 \
    postgresql-dev=12.3-r2 \
    libffi-dev=3.3-r2 \
    gmp-dev=6.2.0-r0 \
    mpfr-dev=4.0.2-r4 \
    wait4ports=0.3.1-r0 && \
    pip install pip setuptools wheel && \
    pip install --upgrade -r requirements.txt && \
    apk del --no-cache .build-deps && \
    rm -fr /tmp/* /var/cache/apk/* /root/.cache/pip

RUN adduser -D -H -h /var/www user && \
    chown user:user /var/www /var/log
USER user
