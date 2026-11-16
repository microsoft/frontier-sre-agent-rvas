FROM --platform=$BUILDPLATFORM node:26-alpine AS dependencies

WORKDIR /app

COPY package*.json ./
RUN npm ci --omit=dev

FROM node:26-alpine

WORKDIR /app

COPY --from=dependencies /app/node_modules ./node_modules
COPY . .

ENV NODE_ENV=production
ENV PORT=3095

EXPOSE 3095

USER node

CMD ["node", "server.js"]
