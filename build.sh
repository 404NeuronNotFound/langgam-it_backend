#!/usr/bin/env bash
# build.sh — runs on every Render deploy
# Place this in the ROOT of your repo (same level as manage.py)

set -o errexit   # exit immediately on any error

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input

# Skip migrations during build - will run after database is accessible
# python manage.py migrate