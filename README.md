

Install [docker](http://docs.docker.com/installation/) and [docker-compose](http://docs.docker.com/compose/).

Run `./tools/build.sh` (from this directory, not from `tools`). This will create the tagged images used by `docker-compose`.

Then run `docker-compose -f tools/docker-compose.yml up` and visit `http://localhost:8851` in your browser.


You might need to destroy the docker volumes used to store the postgres database if
you change the database schema:

    docker-compose -f tools/docker-compose.yml rm
    rm -fr ./tools/dbdata

During development you can run just the database container with the following:

    docker-compose -f tools/docker-compose.yml run db

# Testing

With docker you should be able to use the same container to test:

    docker run -it \
        -e ENTITY_SERVICE_URL=http://<IPADDRESS>:8851 \
        -e ENTITY_SERVICE_TEST_SIZE=1000 \
        n1analytics/entity-app python test_service.py
