FROM python:3.5

MAINTAINER "Brian Thorne <brian@thorne.link>"
EXPOSE 8000
WORKDIR /var/www

# libmpc-dev is necessary to setup gmpy2
RUN (pip install --upgrade pip setuptools; \
     apt-get update; \
     apt-get --assume-yes install libmpc-dev build-essential libyajl-dev libyajl2 libstdc++6)

ADD requirements.txt /var/www/requirements.txt
ADD AnonymousLinking AnonymousLinking

RUN cd AnonymousLinking && pip install -U -r requirements.txt && pip install -e .
RUN pip install -U -r requirements.txt

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

