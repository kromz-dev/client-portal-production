# Stage 1: Build static assets
FROM node:20-alpine AS build

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm install

# Build static application
COPY . .
RUN npm run build

# Stage 2: Minimal static server
FROM nginx:alpine AS runner

# Copy SPA nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy build artifacts to nginx default html directory and /app/dist
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=build /app/dist /app/dist

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
