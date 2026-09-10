#!/bin/bash
# Vercel static build step: install dependencies and collect Django static
# files into staticfiles/ (served via the /static/ route in vercel.json).
set -e

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

# SECRET_KEY is only needed so settings import cleanly during the build.
SECRET_KEY="${SECRET_KEY:-build-time-placeholder}" python3 manage.py collectstatic --noinput --clear
