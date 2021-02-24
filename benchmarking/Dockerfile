FROM amancevice/pandas:0.25.0

EXPOSE 8000
ADD requirements.txt /app/requirements.txt
WORKDIR /app

RUN python3 -m pip install -U pip && pip3 install --upgrade setuptools && \
    pip3 install --upgrade -r requirements.txt && \
    rm -fr /tmp/* /root/.cache/pip

ENV DOCKERIZE_VERSION v0.6.1
RUN wget https://github.com/jwilder/dockerize/releases/download/$DOCKERIZE_VERSION/dockerize-alpine-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && tar -C /usr/local/bin -xzvf dockerize-alpine-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && rm dockerize-alpine-linux-amd64-$DOCKERIZE_VERSION.tar.gz

RUN python -c "import clkhash; print('clkhash version:', clkhash.__version__)"

RUN mkdir /cache
RUN adduser --disabled-password --gecos '' user && \
    chown user:user /app /var/log /cache
VOLUME /cache
USER user
ADD . /app

CMD python benchmark.py
