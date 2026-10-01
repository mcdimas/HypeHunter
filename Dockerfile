FROM node:24-alpine AS icon-assets

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html styles.css app.js /usr/share/nginx/html/
COPY ui /usr/share/nginx/html/ui
COPY assets/*.png assets/*.svg assets/*.webp assets/*.mp4 /usr/share/nginx/html/assets/
COPY --from=icon-assets /app/node_modules/@phosphor-icons/web/src/regular /usr/share/nginx/html/icons/regular

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1/healthz || exit 1
