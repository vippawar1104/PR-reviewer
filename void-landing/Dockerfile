FROM nginx:alpine

COPY index.html /usr/share/nginx/html/index.html
COPY downloads/ /usr/share/nginx/html/downloads/
COPY default.conf.template /etc/nginx/templates/default.conf.template

ENV PORT=8080
EXPOSE 8080
