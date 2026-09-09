"""Schéma de référence (baseline) : users, projets, documents.

Cette migration est introspective : chaque table n'est créée que si elle est
absente. Sur une base déjà initialisée par l'ancien
`Base.metadata.create_all()`, l'opération est donc sans effet.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_users() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_id", "users", ["id"], unique=False)
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def _create_projects() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default="En cours",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_id", "projects", ["id"], unique=False)
    op.create_index("ix_projects_user_id", "projects", ["user_id"], unique=False)


def _create_documents() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_id", "documents", ["id"], unique=False)
    op.create_index(
        "ix_documents_project_id", "documents", ["project_id"], unique=False
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "users" not in existing:
        _create_users()
    if "projects" not in existing:
        _create_projects()
    if "documents" not in existing:
        _create_documents()


def downgrade() -> None:
    op.drop_index("ix_documents_project_id", table_name="documents")
    op.drop_index("ix_documents_id", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_projects_user_id", table_name="projects")
    op.drop_index("ix_projects_id", table_name="projects")
    op.drop_table("projects")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")
