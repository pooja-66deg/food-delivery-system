# API gateway image for Cloud Run.
#
# nginx in front of the seven services. The upstreams are Cloud Run URLs that do
# not exist until the services have been deployed once, so the config is a
# template substituted at container start rather than baked in.
#
# nginx:1.27-alpine already ships an entrypoint that runs envsubst over
# /etc/nginx/templates/*.template — that is why the file lands there and why
# there is no custom entrypoint to maintain.
FROM nginx:1.27-alpine

# Only the variables we mean. Left to itself envsubst would also replace nginx's
# own runtime variables — $host, $remote_addr, $upstream — with the empty string,
# and the config would be silently wrong rather than failing to parse.
ENV NGINX_ENVSUBST_FILTER="^(PORT|USERS_URL|RESTAURANTS_URL|ORDERS_URL|PAYMENTS_URL|DELIVERY_URL|NOTIFICATIONS_URL|ADMIN_URL)$"

# Cloud Run tells the container which port to listen on, and it is not 80.
ENV PORT=8080

COPY infra/nginx/nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 8080
