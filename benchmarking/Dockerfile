FROM amancevice/pandas:0.24.2

EXPOSE 8000
ADD requirements.txt /app/requirements.txt
WORKDIR /app

# postgresql-dev needed for pg_config
# libpq needed by psycopg2

RUN pip3 install --upgrade pip setuptools && \
    pip3 install --upgrade -r requirements.txt && \
    rm -fr /tmp/* /root/.cache/pip

#RUN apk add --no-cache python3 libstdc++ mpc1-dev yajl libpq && \
#    ln -s /usr/bin/python3 /usr/bin/python && \
#    apk add --no-cache --virtual .build-deps g++ python3-dev yajl-dev postgresql-dev libffi-dev && \
#    pip3 install --upgrade pip setuptools && \
#    pip3 install --upgrade -r requirements.txt && \
#    apk del --no-cache .build-deps && \
#    rm -fr /tmp/* /var/cache/apk/* /root/.cache/pip

ENV DOCKERIZE_VERSION v0.6.1
RUN wget https://github.com/jwilder/dockerize/releases/download/$DOCKERIZE_VERSION/dockerize-alpine-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && tar -C /usr/local/bin -xzvf dockerize-alpine-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && rm dockerize-alpine-linux-amd64-$DOCKERIZE_VERSION.tar.gz

RUN python -c "import clkhash; print('clkhash version:', clkhash.__version__)"

RUN adduser user && \
    chown user:user /app /var/log
USER user

ADD . /app

CMD python benchmark.py
