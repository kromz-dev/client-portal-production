#!/bin/sh
# Point d'entrée du conteneur backend.
# Applique les migrations Alembic puis démarre le serveur d'application.
set -e

echo "Portail Client : application des migrations de base de données..."
alembic upgrade head

# `*` est protégé par des quotes : sans elles, le shell le remplacerait par la
# liste des fichiers du répertoire courant.
exec uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
