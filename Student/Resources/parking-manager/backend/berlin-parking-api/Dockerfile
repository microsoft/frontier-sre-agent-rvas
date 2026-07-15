FROM node:18-alpine

# Set working directory
WORKDIR /app

# Copy package files
COPY berlin-parking-api/package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy application files
COPY berlin-parking-api/ .

# Copy shared module
COPY shared/ /shared/

# Expose port
EXPOSE 3004

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3004/health', (r) => {process.exit(r.statusCode === 200 ? 0 : 1)})"

# Start the application
CMD ["node", "server.js"]
