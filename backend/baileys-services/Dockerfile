FROM node:24-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json ./
COPY src ./src
RUN npm run build && npm prune --omit=dev

FROM node:24-bookworm-slim
ENV NODE_ENV=production BAILEYS_BIND_HOST=0.0.0.0
WORKDIR /app
RUN install -d -m 0700 -o node -g node /app/sessions
COPY --from=build /app/package.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
USER node
EXPOSE 3001
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD ["node", "-e", "fetch('http://127.0.0.1:3001/health').then(r => { if (!r.ok) process.exitCode = 1; }).catch(() => { process.exitCode = 1; })"]
CMD ["npm", "start"]
