"""Contrainte CHECK sur projects.status (valeurs autorisées).

Normalise d'abord les lignes historiques dont le statut n'est pas reconnu,
puis ajoute la contrainte `ck_projects_status`.

Revision ID: 0002_project_status_check
Revises: 0001_baseline
Create Date: 2026-09-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_project_status_check"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALLOWED_STATUSES = ("En attente", "En cours", "Terminé")


def upgrade() -> None:
    # Remet les statuts hérités non conformes à « En cours » pour que la
    # contrainte ne puisse pas échouer à la création.
    op.execute(
        "UPDATE projects SET status = 'En cours' "
        "WHERE status NOT IN ('En attente', 'En cours', 'Terminé')"
    )
    # `batch_alter_table` : sur PostgreSQL c'est un simple ALTER TABLE ADD
    # CONSTRAINT ; sur SQLite (dev/tests local) Alembic recrée la table, car
    # SQLite ne sait pas ajouter une contrainte a posteriori.
    with op.batch_alter_table("projects") as batch_op:
        batch_op.create_check_constraint(
            "ck_projects_status",
            sa.column("status").in_(_ALLOWED_STATUSES),
        )


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_constraint("ck_projects_status", type_="check")
