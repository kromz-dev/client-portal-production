# Stage 1: Build static assets
FROM node:20.18-alpine AS build

WORKDIR /app

# Install dependencies (npm ci = build reproductible a partir du package-lock.json)
COPY package*.json ./
RUN npm ci

# Build static application
COPY . .
RUN npm run build

# Stage 2: Minimal static server
FROM nginx:1.27-alpine AS runner

# Copy SPA nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy build artifacts to nginx default html directory
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
