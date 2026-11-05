# Étape 1 : construire le site (Vite). Étape 2 : le servir avec nginx.
FROM node:22.23-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# En ligne, le navigateur appelle /api sur la même origine (D49) :
# le nginx ci-dessous aiguille /api/ vers le backend.
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.31-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
