#!/bin/sh
set -eu

if [ "${1:-}" = "gunicorn" ]; then
    .venv/bin/python manage.py migrate --noinput
    .venv/bin/python manage.py bootstrap_pipeline
    .venv/bin/python manage.py collectstatic --noinput
fi

command="$1"
shift
exec "/app/.venv/bin/$command" "$@"
