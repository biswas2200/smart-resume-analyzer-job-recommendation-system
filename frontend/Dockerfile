# Static web client: plain HTML/CSS/JS, no build step -- nginx serves src/ as-is.
# nginx.conf is a template the image fills in at start-up:
#   API_BASE_URL  where the pages send API calls (default: the backend's published
#                 port, as in the local Docker Compose stack; "/api" when deployed)
#   BACKEND_URL   where /api/ is proxied to (the backend container)
FROM nginx:1.27-alpine
ENV API_BASE_URL=http://localhost:8080 \
    BACKEND_URL=http://backend:8080
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY src/ /usr/share/nginx/html/
EXPOSE 80
