FROM python:3.5

MAINTAINER "Brian Thorne <brian@thorne.link>"
EXPOSE 8000

# libmpc-dev is necessary to setup gmpy2
RUN (pip install --upgrade pip setuptools; \
     apt-get update; \
     apt-get --assume-yes install libmpc-dev build-essential libyajl-dev libyajl2 libstdc++6)

ADD requirements.txt /var/www/requirements.txt

# There are two internal libraries that are installed from Python wheels:
RUN pip install https://magic-ci-atp.it.csiro.au/job/clkhash/job/master/lastSuccessfulBuild/artifact/dist/clkhash-0.7.3-py3-none-any.whl
RUN pip install https://magic-ci-atp.it.csiro.au/job/anonlink/job/master/lastSuccessfulBuild/artifact/dist/anonlink-0.5.0-cp35-cp35m-linux_x86_64.whl

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

