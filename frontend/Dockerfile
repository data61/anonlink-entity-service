# To run this Dockerfile, it is required to be in the source `anonlink-entity-service` folder and run `docker build -f frontend/Dockerfile .`
# Otherwise, it cannot access the `docs` folder to build the documentation before serving it.

FROM data61/anonlink-docs-builder:20210823 AS docsbuilder
COPY ./docs /src/docs
COPY ./backend/entityservice/api_def/openapi.yaml /src/docs/_static/openapi.yaml
WORKDIR /src
RUN python -m sphinx /src/docs /build


FROM nginx:1.21.1-alpine

RUN apk add --no-cache curl

# Copy the static site assets:
COPY --from=docsbuilder /build /usr/share/nginx/html

# Copy the nginx configuration
COPY ./frontend/nginx.conf /etc/nginx/nginx.conf

EXPOSE 8851

COPY ./frontend/docker-start .
CMD ["./docker-start"]
