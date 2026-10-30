# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm ci --strict-ssl=true
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build
RUN chown -R node:node /app
USER node
CMD ["npm","start"]
