# ─── Stage 1: build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /build

# Install deps first for better layer caching
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY . .

# Build-time API URL — baked into the static bundle by Vite
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

# ─── Stage 2: runtime (static file server) ───────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# Remove default Nginx site, replace with SPA-aware config
RUN rm /etc/nginx/conf.d/default.conf
COPY deploy/nginx/dashboard.conf /etc/nginx/conf.d/default.conf

COPY --from=builder /build/dist /usr/share/nginx/html

RUN addgroup -S civic && adduser -S civic -G civic \
    && chown -R civic:civic /usr/share/nginx/html /var/cache/nginx /var/run \
    && touch /var/run/nginx.pid \
    && chown civic:civic /var/run/nginx.pid

USER civic

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:80/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
