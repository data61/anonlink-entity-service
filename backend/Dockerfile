FROM python:3.6.5-alpine3.6

MAINTAINER "Brian Thorne <brian@thorne.link>"
EXPOSE 8000

# postgresql-dev needed for pg_config
# libffi-dev needed by anonlink
# g++ needed by anonlink/cffi
# gmp-dev, mpfr-dev, mpc1-dev needed by gmpy2
# shadow needed for groupadd and useradd (NB: shadow package only available in alpine >= 3.6)
RUN (pip install --upgrade pip setuptools; \
     apk add --no-cache postgresql-dev libffi-dev g++ gmp-dev mpfr-dev mpc1-dev shadow)

ADD requirements.txt /var/www/requirements.txt

WORKDIR /var/www

RUN pip install -U -r requirements.txt
RUN python -c "import anonlink; print('anonlink version:', anonlink.__version__)"
RUN python -c "import clkhash; print('clkhash version:', clkhash.__version__)"

RUN groupadd user && useradd --home-dir /var/www -g user user
RUN chown user:user /var/www; chown user:user /var/log
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

