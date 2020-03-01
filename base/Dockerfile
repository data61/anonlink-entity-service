FROM alpine:3.11.3

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
    python3=3.8.2-r0 \
    libstdc++=9.2.0-r3 \
    mpc1-dev=1.1.0-r1 \
    yajl=2.1.0-r0 \
    libpq=12.2-r0 && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    ln -s /usr/bin/pip3 /usr/bin/pip && \
    apk add --no-cache --virtual .build-deps \
    g++=9.2.0-r3 \
    python3-dev=3.8.2-r0 \
    yajl-dev=2.1.0-r0 \
    postgresql-dev=12.2-r0 \
    libffi-dev=3.2.1-r6 \
    gmp-dev=6.1.2-r1 \
    mpfr-dev=4.0.2-r1 \
    wait4ports=0.2.3-r0 && \
    pip install pip==20.0.2 setuptools==45.2.0 wheel==0.34.2 && \
    pip install --upgrade -r requirements.txt && \
    apk del --no-cache .build-deps && \
    rm -fr /tmp/* /var/cache/apk/* /root/.cache/pip

RUN adduser -D -H -h /var/www user && \
    chown user:user /var/www /var/log
USER user
