FROM nginx

MAINTAINER "Brian Thorne <brian.thorne@data61.csiro.au>"

#RUN rm /etc/nginx/conf.d/default.conf

# Copy the static site assets:
COPY ./static /usr/share/nginx/html

# Copy the nginx configuration
COPY ./nginx.conf /etc/nginx/nginx.conf

EXPOSE 80