FROM node:22-alpine

WORKDIR /app
COPY src /app/src

USER node
EXPOSE 8080
CMD ["node", "--experimental-strip-types", "/app/src/server.ts"]
