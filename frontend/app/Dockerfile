# syntax=docker/dockerfile:1

FROM node:24-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY angular.json tsconfig.json tsconfig.app.json ./
COPY src ./src
COPY public ./public

ARG API_PUBLIC_URL="http://localhost:8000/api/v1"
ARG OPERATIONAL_API_PUBLIC_URL="http://localhost:8001/api/v1"
ARG AGENT_CORE_API_PUBLIC_URL="http://localhost:8002/api/v1"
ARG LANDING_PUBLIC_URL="http://localhost:8080"
ARG SALES_WHATSAPP_NUMBER=""
ENV API_PUBLIC_URL=${API_PUBLIC_URL}
ENV OPERATIONAL_API_PUBLIC_URL=${OPERATIONAL_API_PUBLIC_URL}
ENV AGENT_CORE_API_PUBLIC_URL=${AGENT_CORE_API_PUBLIC_URL}
ENV LANDING_PUBLIC_URL=${LANDING_PUBLIC_URL}
ENV SALES_WHATSAPP_NUMBER=${SALES_WHATSAPP_NUMBER}
RUN node -e "const fs = require('fs'); const path = 'src/environments/environment.ts'; let content = fs.readFileSync(path, 'utf8'); content = content.replace(/apiUrl: '.*?'/, 'apiUrl: ' + JSON.stringify(process.env.API_PUBLIC_URL || 'http://localhost:8000/api/v1')); content = content.replace(/operationalApiUrl: '.*?'/, 'operationalApiUrl: ' + JSON.stringify(process.env.OPERATIONAL_API_PUBLIC_URL || 'http://localhost:8001/api/v1')); content = content.replace(/agentCoreApiUrl: '.*?'/, 'agentCoreApiUrl: ' + JSON.stringify(process.env.AGENT_CORE_API_PUBLIC_URL || 'http://localhost:8002/api/v1')); content = content.replace(/landingUrl: '.*?'/, 'landingUrl: ' + JSON.stringify(process.env.LANDING_PUBLIC_URL || 'http://localhost:8080')); content = content.replace(/salesWhatsAppNumber: '.*?'/, 'salesWhatsAppNumber: ' + JSON.stringify(process.env.SALES_WHATSAPP_NUMBER || '')); fs.writeFileSync(path, content);"

RUN npm run build

FROM nginx:1.27-alpine AS runtime

ENV PORT=80
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist/app/browser /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- "http://127.0.0.1:${PORT}/" >/dev/null || exit 1
