ARG VERSION=4b497c1a0b2a6cc3ea848338a67c3a129050d32d9c532373e3301be898920b55
FROM data61/anonlink-base:${VERSION}

WORKDIR /var/www
ADD . /var/www

RUN python -c "import anonlink; print('anonlink version:', anonlink.__version__)" && \
    python -c "import clkhash; print('clkhash version:', clkhash.__version__)"

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
