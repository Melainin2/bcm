FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 5173
# --host expose le serveur Vite hors du conteneur.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
