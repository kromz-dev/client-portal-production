"""Configuration centralisée de l'application (lecture des variables d'environnement).

Toute la configuration transite par la classe `Settings` ci-dessous. Les valeurs
sont lues depuis l'environnement de manière insensible à la casse
(par ex. `SECRET_KEY` alimente le champ `secret_key`).
"""

import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("portail_client.config")

# Valeurs de repli réservées au développement (jamais utilisées en production).
_DEV_SECRET_KEY = "insecure-dev-secret-key-change-in-production-32bytes-min"
_DEV_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/portail_client"


class Settings(BaseSettings):
    """Paramètres applicatifs chargés depuis l'environnement."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    secret_key: str = ""
    database_url: str = ""
    environment: str = "development"
    cors_origins: str = ""
    access_token_expire_minutes: int = 1440
    max_upload_bytes: int = 10485760
    upload_dir: str = "/uploads"
    app_version: str = "1.0.0"

    @model_validator(mode="after")
    def _validate_environment(self) -> "Settings":
        if self.environment == "production":
            if not self.secret_key:
                raise RuntimeError(
                    "SECRET_KEY est obligatoire en production : "
                    "générez une valeur avec `openssl rand -hex 32`."
                )
            if self.secret_key == _DEV_SECRET_KEY:
                raise RuntimeError(
                    "SECRET_KEY utilise encore la valeur de développement : "
                    "générez une clé unique pour la production."
                )
            if len(self.secret_key) < 32:
                raise RuntimeError(
                    "SECRET_KEY est trop courte : au moins 32 caractères sont "
                    "requis en production."
                )
            if not self.database_url:
                raise RuntimeError(
                    "DATABASE_URL est obligatoire en production : aucune valeur "
                    "de repli n'est autorisée."
                )
            if "*" in self.cors_origins:
                raise RuntimeError(
                    "CORS_ORIGINS ne doit jamais contenir `*` en production : "
                    "renseignez explicitement les origines autorisées."
                )
        else:
            if not self.database_url:
                logger.warning(
                    "DATABASE_URL absente : utilisation de la valeur de repli de "
                    "développement (%s).",
                    _DEV_DATABASE_URL,
                )
                self.database_url = _DEV_DATABASE_URL
            if not self.secret_key:
                logger.warning(
                    "SECRET_KEY absente : utilisation d'une clé de repli de "
                    "développement, non sécurisée."
                )
                self.secret_key = _DEV_SECRET_KEY
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        """Liste des origines CORS, découpée sur les virgules et nettoyée."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
