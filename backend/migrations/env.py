"""Environnement Alembic pour le Portail Client.

L'URL de la base est fournie par `config.settings.database_url` ; on importe
`models` afin que toutes les tables soient enregistrées dans `Base.metadata`.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from config import settings
from database import Base
import models  # noqa: F401  (import nécessaire pour peupler Base.metadata)

# Objet de configuration Alembic (accès aux valeurs du fichier .ini).
config = context.config

# Interprète le fichier de configuration pour la journalisation Python.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Fournit dynamiquement l'URL de connexion.
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Exécute les migrations en mode « offline » (génération de SQL sans connexion)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Exécute les migrations en mode « online » (connexion réelle à la base)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
