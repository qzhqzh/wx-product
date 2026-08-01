#!/bin/sh
set -eu

target="${1:-.env}"
if [ -e "$target" ]; then
    echo "$target already exists; leaving it unchanged."
    exit 0
fi

umask 077
django_secret="$(openssl rand -hex 48)"
minio_secret="$(openssl rand -hex 24)"
postgres_password="$(openssl rand -hex 24)"
admin_password="$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)"

{
    echo "DJANGO_SECRET_KEY=$django_secret"
    echo "DJANGO_DEBUG=1"
    echo "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,web"
    echo "DJANGO_CSRF_TRUSTED_ORIGINS="
    echo "POSTGRES_PASSWORD=$postgres_password"
    echo "AWS_ACCESS_KEY_ID=wx-pipeline"
    echo "AWS_SECRET_ACCESS_KEY=$minio_secret"
    echo "AWS_STORAGE_BUCKET_NAME=wx-pipeline"
    echo "DEFAULT_AI_PROVIDER=local"
    echo "OPENAI_API_KEY="
    echo "OPENAI_TEXT_MODEL=gpt-5.6-terra"
    echo "OPENAI_IMAGE_MODEL=gpt-image-2"
    echo "DJANGO_SUPERUSER_USERNAME=admin"
    echo "DJANGO_SUPERUSER_EMAIL=admin@example.com"
    echo "DJANGO_SUPERUSER_PASSWORD=$admin_password"
    echo "APP_PORT=${APP_PORT:-8080}"
} > "$target"

echo "Created $target with mode 600."
if [ "${INIT_ENV_QUIET:-0}" != "1" ]; then
    echo "Initial admin username: admin"
    echo "Initial admin password: $admin_password"
fi
