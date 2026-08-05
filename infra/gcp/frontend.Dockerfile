# Frontend image for Cloud Run. Unlike the local compose build (which proxies
# /api to the api container), on GCP the SPA calls the API's public URL directly,
# baked in at build time via VITE_API_URL. That makes every request cross-origin,
# so the API must list this service's URL in CORS_ORIGINS — the deploy sets it
# from the _FE_URL substitution. There is no permissive "*" allowlist: the API
# sends credentials, which browsers refuse to combine with a wildcard.

FROM node:22-alpine AS build
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}
# Google Maps JS key for the live driver map. Baked into the bundle at build
# time, so it is public by construction — restrict it by HTTP referrer and give
# it only the Maps JavaScript API. Left unset the app still tracks, showing the
# ETA as text instead of a map.
ARG VITE_GOOGLE_MAPS_API_KEY
ENV VITE_GOOGLE_MAPS_API_KEY=${VITE_GOOGLE_MAPS_API_KEY}
# Stripe *publishable* key (pk_...). Public by construction — it identifies the
# account to Stripe.js and can only create payment methods, never move money, so
# baking it into the bundle is correct. The secret key (sk_...) must never appear
# here; it lives in Secret Manager and is read by the API only. Left unset, the
# checkout hides the card option entirely rather than offering a dead end.
ARG VITE_STRIPE_PUBLISHABLE_KEY
ENV VITE_STRIPE_PUBLISHABLE_KEY=${VITE_STRIPE_PUBLISHABLE_KEY}
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
