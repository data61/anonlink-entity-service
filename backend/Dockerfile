FROM python:3.5

MAINTAINER "Brian Thorne <brian@thorne.link>"
EXPOSE 8000
WORKDIR /var/www
ADD requirements.txt /var/www/requirements.txt
ADD ssh/ /root/.ssh/

# libmpc-dev is necessary to setup gmpy2
RUN (pip install --upgrade pip; \
     apt-get update; \
     apt-get --assume-yes install libmpc-dev)

# Use of a private ssh key which has read-only permission for
# the AnonymousLinking repo.
# Needed to pull the git repo in the container.
RUN (chmod 600 /root/.ssh/*; \
    eval `ssh-agent -s`; \
    ssh-add /root/.ssh/n1-anonlink-deploy-2016; \
    ssh -o StrictHostKeyChecking=no -l git github.csiro.au; \
    pip install -r requirements.txt)

RUN groupadd user && useradd --home-dir /var/www -g user user
RUN chown user:user /var/www; chown user:user /var/log
USER user

ADD . /var/www

# Serve using gunicorn. Ideally this has nginx in front of it!
CMD gunicorn entityservice:app \
    -w 4 \
    -b 0.0.0.0:8000 \
    --timeout 300 \
    --log-level info \
    --access-logfile /var/log/gunicorn-access.log

