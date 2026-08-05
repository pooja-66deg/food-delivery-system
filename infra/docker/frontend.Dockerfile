# Multi-stage build for the customer web app.
# Stage 1 builds the Vite app; stage 2 serves the static output via nginx,
# which also reverse-proxies /api to the backend container.

FROM node:22-alpine AS build
# Vite inlines env vars at build time, so anything the bundle needs has to be an
# ARG here — a runtime env var on the nginx stage arrives too late. Both keys are
# public by construction (they ship in the bundle); secret keys never belong here.
ARG VITE_STRIPE_PUBLISHABLE_KEY
ENV VITE_STRIPE_PUBLISHABLE_KEY=${VITE_STRIPE_PUBLISHABLE_KEY}
ARG VITE_GOOGLE_MAPS_API_KEY
ENV VITE_GOOGLE_MAPS_API_KEY=${VITE_GOOGLE_MAPS_API_KEY}
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY infra/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
