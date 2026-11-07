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

# L'image nginx transforme /etc/nginx/templates/*.template en /etc/nginx/conf.d/* au démarrage
# en remplaçant les variables d'environnement. Le filtre limite ce remplacement à EDGE_* :
# les variables propres à nginx ($host, $remote_addr...) restent intactes.
ENV NGINX_ENVSUBST_FILTER=^EDGE_
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
