FROM nginx:1.13.12-alpine

MAINTAINER "Brian Thorne <brian.thorne@data61.csiro.au>"

RUN apk add --no-cache curl

# Copy the static site assets:
COPY ./static /usr/share/nginx/html

# Copy the nginx configuration
COPY ./nginx.conf /etc/nginx/nginx.conf

EXPOSE 8851

COPY ./docker-start .
CMD ["./docker-start"]
