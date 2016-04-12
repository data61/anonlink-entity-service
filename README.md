

Install [docker](http://docs.docker.com/installation/) and [docker-compose](http://docs.docker.com/compose/).

Run `./tools/build.sh` (from this directory, not from `tools`). This will create the tagged images used by `docker-compose`.

Then run `docker-compose -f tools/docker-compose.yml up` and visit `http://localhost:8851` in your browser.
