FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL

RUN npm run build

FROM node:20-alpine AS production

WORKDIR /app
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

USER appuser

EXPOSE 3000
CMD ["node", "server.js"]