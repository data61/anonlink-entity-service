# To run this Dockerfile, it is required to be in the source `anonlink-entity-service` folder and run `docker build -f frontend/Dockerfile .`
# Otherwise, it cannot access the `docs` folder to build the documentation before serving it.

FROM data61/anonlink-docs-builder:20190625 AS docsbuilder
COPY ./docs /src/docs
COPY ./backend/entityservice/api_def/swagger.yaml /src/docs/_static/swagger.yaml
WORKDIR /src
RUN python -m sphinx /src/docs /build




FROM nginx:1.15.12-alpine

MAINTAINER "Brian Thorne <brian.thorne@data61.csiro.au>"

RUN apk add --no-cache curl

# Copy the static site assets:
COPY --from=docsbuilder /build /usr/share/nginx/html

# Copy the nginx configuration
COPY ./frontend/nginx.conf /etc/nginx/nginx.conf

EXPOSE 8851

COPY ./frontend/docker-start .
CMD ["./docker-start"]
