FROM python:3.6.5-alpine3.6

EXPOSE 8000
ADD requirements.txt /var/www/requirements.txt
WORKDIR /var/www

# postgresql-dev needed for pg_config
# libpq needed by psycopg2
# libffi-dev needed by anonlink
# g++ needed by anonlink/cffi
# yajl, yajl-dev needed by ijson
# gmp-dev, mpfr-dev, mpc1-dev needed by gmpy2

#RUN apk add --no-cache postgresql-dev shadow libffi-dev libstdc++ mpc1-dev yajl-dev yajl
RUN apk add --no-cache libstdc++ mpc1-dev yajl libpq && \
    apk add --no-cache --virtual .build-deps g++ yajl-dev postgresql-dev libffi-dev gmp-dev mpfr-dev && \
    pip install --upgrade pip setuptools && \
    pip install --upgrade -r requirements.txt && \
    apk del --no-cache .build-deps && \
    rm -fr /tmp/* /var/cache/apk/* /root/.cache/pip

RUN python -c "import anonlink; print('anonlink version:', anonlink.__version__)" && \
    python -c "import clkhash; print('clkhash version:', clkhash.__version__)"

RUN adduser -D -H -h /var/www user && \
    chown user:user /var/www /var/log
USER user

ADD . /var/www

# Serve using gunicorn. Ideally this has nginx in front of it!
CMD gunicorn entityservice:app \
    -n entityservice-web \
    -w 4 \
    -b 0.0.0.0:8000 \
    --timeout 600 \
    --keep-alive 300 \
    --graceful-timeout 120 \
    --log-level info \
    --access-logfile /var/log/gunicorn-access.log

