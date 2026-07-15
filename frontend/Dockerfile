# syntax=docker/dockerfile:1

# Stage 1: compile the React/TS app to static files. Node is only needed to
# run the build -- it never ships in the final image.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# VITE_WS_URL/VITE_API_URL get baked into the JS bundle at build time (Vite
# has no server-side runtime to read env vars from later), so they're build
# args here, not container env vars -- see infra/k8s for how the real
# deploy passes them in.
ARG VITE_WS_URL
ARG VITE_API_URL
ENV VITE_WS_URL=$VITE_WS_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Stage 2: nginx just serves the static output from Stage 1 -- ~40MB
# final image instead of carrying Node + node_modules into production.
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
