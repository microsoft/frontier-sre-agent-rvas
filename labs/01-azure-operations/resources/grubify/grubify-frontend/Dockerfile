# Build stage
FROM node:18-alpine AS build
WORKDIR /app

# Copy package files
COPY package*.json ./
RUN npm ci --only=production

# Copy source code
COPY . .

# Build the app (environment variables will be injected at runtime)
RUN npm run build

# Production stage
FROM nginx:alpine

# Install envsubst for environment variable substitution
RUN apk add --no-cache gettext

# Copy built app
COPY --from=build /app/build /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Create startup script
RUN echo '#!/bin/sh' > /docker-entrypoint.d/40-substitute-env.sh && \
    echo 'if [ -n "$REACT_APP_API_BASE_URL" ]; then' >> /docker-entrypoint.d/40-substitute-env.sh && \
    echo '  find /usr/share/nginx/html -name "*.js" -exec sed -i "s|http://localhost:5291/api|$REACT_APP_API_BASE_URL|g" {} \;' >> /docker-entrypoint.d/40-substitute-env.sh && \
    echo 'fi' >> /docker-entrypoint.d/40-substitute-env.sh && \
    chmod +x /docker-entrypoint.d/40-substitute-env.sh

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
