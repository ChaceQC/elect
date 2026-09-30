FROM node:22.23.2-bookworm-slim@sha256:48e4b67d85f87bd551df43704e24d252f56cc5f8e9718841aace50f19948f0f9 AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM dependencies AS test
COPY . .
CMD ["npm", "test"]

FROM dependencies AS browser-test
RUN npx playwright install --with-deps chromium
COPY . .
CMD ["npm", "run", "test:e2e"]

FROM test AS build
RUN npm run build

FROM nginx:stable-alpine@sha256:ef8676b33d681f272ba429b27658bdd7e640963279714c96bddf1dc76307f7b6 AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
# 官方 entrypoint 渲染 deploy 挂载的模板，再由 nginx 校验配置/证书。
CMD ["nginx", "-g", "daemon off;"]
