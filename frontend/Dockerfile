FROM node:20-alpine as builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the application (skip TypeScript checking for faster builds)
RUN npm run build:vite

# Production stage
FROM nginx:alpine

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration as template
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Default backend host (will be overridden by docker-compose environment)
ENV BACKEND_HOST=localhost:8000

EXPOSE 80

# Use envsubst to substitute env vars in nginx config at startup
CMD ["/bin/sh", "-c", "envsubst '${BACKEND_HOST}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
