# Frontend image for Cloud Run. Unlike the local compose build (which proxies
# /api to the api container), on GCP the SPA calls the API's public URL directly
# (baked in at build time via VITE_API_URL); the API's permissive CORS allows it.

FROM node:22-alpine AS build
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}
# Google Maps JS key for the live driver map. Baked into the bundle at build
# time, so it is public by construction — restrict it by HTTP referrer and give
# it only the Maps JavaScript API. Left unset the app still tracks, showing the
# ETA as text instead of a map.
ARG VITE_GOOGLE_MAPS_API_KEY
ENV VITE_GOOGLE_MAPS_API_KEY=${VITE_GOOGLE_MAPS_API_KEY}
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
# nginx:alpine substitutes ${PORT} from the environment into the rendered config.
COPY infra/gcp/nginx-spa.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
ENV PORT=8080
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
