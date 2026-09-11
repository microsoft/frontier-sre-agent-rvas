FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY public ./public
COPY src ./src
COPY tsconfig.json ./
RUN npm run build

FROM node:20-alpine AS runtime

ENV NODE_ENV=production \
    PORT=8080

WORKDIR /app

COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --chown=node:node server.js package*.json ./
COPY --from=build --chown=node:node /app/build ./build

USER node
EXPOSE 8080

CMD ["node", "server.js"]
