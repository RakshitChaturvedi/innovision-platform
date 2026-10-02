# Multi-stage Dockerfile for Dashboard Web UI
FROM node:20-alpine AS build

WORKDIR /app

COPY services/dashboard/package*.json ./
RUN npm ci

COPY services/dashboard/ ./

ARG VITE_AUTH_API_URL=http://localhost:8000
ARG VITE_CAMERA_API_URL=http://localhost:8011
ARG VITE_ALERTS_API_URL=http://localhost:8010
ARG VITE_SOCKET_URL=http://localhost:8010
ARG VITE_INGESTION_API_URL=http://localhost:8020
ARG VITE_UC2_STREAM_URL=http://localhost:8030

ENV VITE_AUTH_API_URL=$VITE_AUTH_API_URL \
    VITE_CAMERA_API_URL=$VITE_CAMERA_API_URL \
    VITE_ALERTS_API_URL=$VITE_ALERTS_API_URL \
    VITE_SOCKET_URL=$VITE_SOCKET_URL \
    VITE_INGESTION_API_URL=$VITE_INGESTION_API_URL \
    VITE_UC2_STREAM_URL=$VITE_UC2_STREAM_URL

RUN npm run build

# Production runner stage using lightweight Node serve
FROM node:20-alpine AS runner
WORKDIR /app
RUN npm install -g serve
COPY --from=build /app/dist ./dist

EXPOSE 3000
CMD ["serve", "-s", "dist", "-l", "3000"]
