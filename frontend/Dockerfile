FROM nginx:1.13

MAINTAINER "Brian Thorne <brian.thorne@data61.csiro.au>"

RUN apt-get update \
  && apt-get install --no-install-recommends --no-install-suggests -y \
	curl \
  && rm -rf /var/lib/apt/lists/*

# Copy the static site assets:
COPY ./static /usr/share/nginx/html

# Copy the nginx configuration
COPY ./nginx.conf /etc/nginx/nginx.conf

EXPOSE 8851

COPY ./docker-start .
CMD ["./docker-start"]