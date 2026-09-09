"""Rôles prestataire/client et collaboration (messages, événements, jalons).

Migration introspective et idempotente : chaque colonne ou table n'est ajoutée
que si elle est absente (vérification via `sa.inspect`). Les `add_column`
passent par `batch_alter_table` pour rester compatibles SQLite (dev/tests local),
comme la migration 0002.

Cette migration NE modifie PAS le rôle des utilisateurs existants : la promotion
du premier administrateur est faite au démarrage de l'application
(`ensure_bootstrap_admin`).

Revision ID: 0003_roles_client_collaboration
Revises: 0002_project_status_check
Create Date: 2026-09-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_roles_client_collaboration"
down_revision: Union[str, None] = "0002_project_status_check"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector, table: str) -> set:
    return {col["name"] for col in inspector.get_columns(table)}


def _index_names(inspector, table: str) -> set:
    return {idx["name"] for idx in inspector.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # ------------------------------------------------------------------ users
    user_cols = _column_names(inspector, "users")
    add_role = "role" not in user_cols
    add_full_name = "full_name" not in user_cols
    if add_role or add_full_name:
        with op.batch_alter_table("users") as batch_op:
            if add_role:
                batch_op.add_column(
                    sa.Column(
                        "role",
                        sa.String(length=20),
                        server_default="client",
                        nullable=False,
                    )
                )
            if add_full_name:
                batch_op.add_column(
                    sa.Column("full_name", sa.String(length=255), nullable=True)
                )

    # --------------------------------------------------------------- projects
    project_cols = _column_names(inspector, "projects")
    add_client_id = "client_id" not in project_cols
    add_due_date = "due_date" not in project_cols
    add_started_at = "started_at" not in project_cols
    if add_client_id or add_due_date or add_started_at:
        with op.batch_alter_table("projects") as batch_op:
            if add_client_id:
                batch_op.add_column(sa.Column("client_id", sa.Integer(), nullable=True))
            if add_due_date:
                batch_op.add_column(sa.Column("due_date", sa.Date(), nullable=True))
            if add_started_at:
                batch_op.add_column(sa.Column("started_at", sa.Date(), nullable=True))
            if add_client_id:
                batch_op.create_foreign_key(
                    "fk_projects_client_id_users",
                    "users",
                    ["client_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
    if add_client_id and "ix_projects_client_id" not in _index_names(inspector, "projects"):
        op.create_index("ix_projects_client_id", "projects", ["client_id"], unique=False)

    # -------------------------------------------------------------- documents
    document_cols = _column_names(inspector, "documents")
    add_uploaded_by = "uploaded_by" not in document_cols
    add_kind = "kind" not in document_cols
    add_review_status = "review_status" not in document_cols
    add_review_comment = "review_comment" not in document_cols
    add_reviewed_at = "reviewed_at" not in document_cols
    if any(
        (
            add_uploaded_by,
            add_kind,
            add_review_status,
            add_review_comment,
            add_reviewed_at,
        )
    ):
        with op.batch_alter_table("documents") as batch_op:
            if add_uploaded_by:
                batch_op.add_column(
                    sa.Column("uploaded_by", sa.Integer(), nullable=True)
                )
            if add_kind:
                batch_op.add_column(
                    sa.Column(
                        "kind",
                        sa.String(length=20),
                        server_default="livrable",
                        nullable=False,
                    )
                )
            if add_review_status:
                batch_op.add_column(
                    sa.Column("review_status", sa.String(length=20), nullable=True)
                )
            if add_review_comment:
                batch_op.add_column(sa.Column("review_comment", sa.Text(), nullable=True))
            if add_reviewed_at:
                batch_op.add_column(
                    sa.Column(
                        "reviewed_at", sa.DateTime(timezone=True), nullable=True
                    )
                )
            if add_uploaded_by:
                batch_op.create_foreign_key(
                    "fk_documents_uploaded_by_users",
                    "users",
                    ["uploaded_by"],
                    ["id"],
                    ondelete="SET NULL",
                )

    # --------------------------------------------------------------- messages
    if "messages" not in tables:
        op.create_table(
            "messages",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("author_id", sa.Integer(), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["project_id"], ["projects.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["author_id"], ["users.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_messages_id", "messages", ["id"], unique=False)
        op.create_index(
            "ix_messages_project_id", "messages", ["project_id"], unique=False
        )

    # ----------------------------------------------------------------- events
    if "events" not in tables:
        op.create_table(
            "events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("actor_id", sa.Integer(), nullable=True),
            sa.Column("type", sa.String(length=50), nullable=False),
            sa.Column("summary", sa.String(length=500), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["project_id"], ["projects.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["actor_id"], ["users.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_events_id", "events", ["id"], unique=False)
        op.create_index(
            "ix_events_project_id", "events", ["project_id"], unique=False
        )

    # ------------------------------------------------------------- milestones
    if "milestones" not in tables:
        op.create_table(
            "milestones",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column(
                "position", sa.Integer(), server_default="0", nullable=False
            ),
            sa.Column(
                "status",
                sa.String(length=20),
                server_default="a_faire",
                nullable=False,
            ),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.ForeignKeyConstraint(
                ["project_id"], ["projects.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_milestones_id", "milestones", ["id"], unique=False)
        op.create_index(
            "ix_milestones_project_id", "milestones", ["project_id"], unique=False
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    for table in ("milestones", "events", "messages"):
        if table in tables:
            for idx in _index_names(inspector, table):
                op.drop_index(idx, table_name=table)
            op.drop_table(table)

    if "documents" in tables:
        document_cols = _column_names(inspector, "documents")
        with op.batch_alter_table("documents") as batch_op:
            if "fk_documents_uploaded_by_users" in {
                fk["name"] for fk in inspector.get_foreign_keys("documents")
            }:
                batch_op.drop_constraint(
                    "fk_documents_uploaded_by_users", type_="foreignkey"
                )
            for col in (
                "reviewed_at",
                "review_comment",
                "review_status",
                "kind",
                "uploaded_by",
            ):
                if col in document_cols:
                    batch_op.drop_column(col)

    if "projects" in tables:
        project_cols = _column_names(inspector, "projects")
        if "ix_projects_client_id" in _index_names(inspector, "projects"):
            op.drop_index("ix_projects_client_id", table_name="projects")
        with op.batch_alter_table("projects") as batch_op:
            if "fk_projects_client_id_users" in {
                fk["name"] for fk in inspector.get_foreign_keys("projects")
            }:
                batch_op.drop_constraint(
                    "fk_projects_client_id_users", type_="foreignkey"
                )
            for col in ("started_at", "due_date", "client_id"):
                if col in project_cols:
                    batch_op.drop_column(col)

    if "users" in tables:
        user_cols = _column_names(inspector, "users")
        with op.batch_alter_table("users") as batch_op:
            for col in ("full_name", "role"):
                if col in user_cols:
                    batch_op.drop_column(col)
