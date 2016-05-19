FROM python:3.4

MAINTAINER "Brian Thorne <brian@thorne.link>"
EXPOSE 8000
WORKDIR /var/www
ADD requirements.txt /var/www/requirements.txt
ADD ssh/ /var/www/.ssh/
RUN pip install --upgrade pip
RUN (chmod 600 /var/www/.ssh/*; eval `ssh-agent -s`; ssh-add /var/www/.ssh/n1-anonlink-deploy-2016; ssh -o StrictHostKeyChecking=no -l git github.csiro.au; pip install -r requirements.txt)

ADD . /var/www

# Serve using gunicorn. Ideally this has nginx in front of it!
CMD gunicorn entityservice:app \
    -w 4 \
    -b 0.0.0.0:8000 \
    --timeout 300 \
    --log-level info \
    --access-logfile /var/log/gunicorn-access.log

