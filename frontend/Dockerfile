FROM node:20-alpine AS build

WORKDIR /app

# node:20-alpine bundles npm 10.x, which validates this lockfile more
# strictly than the npm 11.x it was generated with and fails `npm ci`
# with a false "not in sync" error. Match npm major versions instead
# of touching package-lock.json.
RUN npm install -g npm@11

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite inlines env vars into the static bundle at build time, so the
# browser-facing backend URL must be supplied as a build arg here -
# setting VITE_API_URL only at container runtime would have no effect.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 \
    CMD wget -qO- http://127.0.0.1:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
