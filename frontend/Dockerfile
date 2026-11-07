# Tóm tắt: image frontend EduGen (T-043, bản cơ bản): build bản production bằng Node 20 rồi phục vụ file tĩnh bằng
# nginx ở cổng 80. Địa chỉ Backend gắn lúc build qua VITE_API_URL (mặc định rỗng = đường dẫn tương đối /api/v1, Caddy chuyển tới Backend).
FROM node:20-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_API_URL=
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
