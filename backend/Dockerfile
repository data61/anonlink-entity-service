FROM python:3.4

MAINTAINER "Brian Thorne <brian@thorne.link>"
EXPOSE 8000
WORKDIR /var/www
ADD requirements.txt /var/www/requirements.txt
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
RUN pip freeze

ADD . /var/www

# Serve using gunicorn. Ideally this has nginx in front of it!
CMD gunicorn entityservice:app \
    -w 4 \
    -b 0.0.0.0:8000 \
    --log-level info \
    --access-logfile /var/log/gunicorn-access.log
