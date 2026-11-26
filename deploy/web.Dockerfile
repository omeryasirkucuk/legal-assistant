FROM node:24-bookworm-slim AS build
WORKDIR /app/apps/web
ENV NEXT_TELEMETRY_DISABLED=1
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web/ ./
COPY locales /app/locales
ENV NEXT_PUBLIC_API_URL=/api
RUN npm run build && npm prune --omit=dev

FROM node:24-bookworm-slim
WORKDIR /app/apps/web
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build --chown=node:node /app/apps/web/ ./
USER node
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0"]
