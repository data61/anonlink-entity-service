FROM alpine:3.7

EXPOSE 8000
ADD requirements.txt /app/requirements.txt
WORKDIR /app

# postgresql-dev needed for pg_config
# libpq needed by psycopg2

RUN apk add --no-cache python3 libstdc++ mpc1-dev yajl libpq && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    apk add --no-cache --virtual .build-deps g++ python3-dev yajl-dev postgresql-dev libffi-dev && \
    pip3 install --upgrade pip setuptools && \
    pip3 install --upgrade -r requirements.txt && \
    apk del --no-cache .build-deps && \
    rm -fr /tmp/* /var/cache/apk/* /root/.cache/pip

RUN python -c "import clkhash; print('clkhash version:', clkhash.__version__)"

RUN adduser -D -H -h /app user && \
    chown user:user /app /var/log
USER user

ADD benchmark.py /app

CMD python benchmark.py
