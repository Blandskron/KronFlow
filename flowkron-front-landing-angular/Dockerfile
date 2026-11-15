# syntax=docker/dockerfile:1

FROM node:24-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY angular.json tsconfig.json tsconfig.app.json ./
COPY src ./src
COPY public ./public

ARG APP_PUBLIC_URL="http://localhost:8081"
ARG CONTACT_API_BASE_URL="http://localhost:8000"
ARG SALES_WHATSAPP_NUMBER=""
ENV APP_PUBLIC_URL=${APP_PUBLIC_URL}
ENV CONTACT_API_BASE_URL=${CONTACT_API_BASE_URL}
ENV SALES_WHATSAPP_NUMBER=${SALES_WHATSAPP_NUMBER}
RUN node -e "const fs = require('fs'); const path = 'src/environments/environment.ts'; let content = fs.readFileSync(path, 'utf8'); content = content.replace(/appUrl: '.*?'/, 'appUrl: ' + JSON.stringify(process.env.APP_PUBLIC_URL || 'http://localhost:8081')); content = content.replace(/contactApiBaseUrl: '.*?'/, 'contactApiBaseUrl: ' + JSON.stringify(process.env.CONTACT_API_BASE_URL || 'http://localhost:8000')); content = content.replace(/salesWhatsAppNumber: '.*?'/, 'salesWhatsAppNumber: ' + JSON.stringify(process.env.SALES_WHATSAPP_NUMBER || '')); fs.writeFileSync(path, content);"

RUN npm run build

FROM nginx:1.27-alpine AS runtime

ENV PORT=80
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist/flowkron-front-landing-angular/browser /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- "http://127.0.0.1:${PORT}/" >/dev/null || exit 1
