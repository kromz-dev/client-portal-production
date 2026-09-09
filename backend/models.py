from datetime import datetime, timezone
from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    # 'admin' (prestataire) ou 'client'. Toujours renseigné (défaut 'client').
    role = Column(String(20), default="client", server_default="client", nullable=False)
    full_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Projets créés/pilotés par cet utilisateur en tant que prestataire.
    projects = relationship(
        "Project",
        back_populates="user",
        foreign_keys="Project.user_id",
        cascade="all, delete-orphan",
    )
    # Projets dont cet utilisateur est le client (FK ON DELETE SET NULL).
    client_projects = relationship(
        "Project",
        back_populates="client",
        foreign_keys="Project.client_id",
    )


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    # Créateur/prestataire du projet.
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Client destinataire du projet (optionnel au niveau schéma).
    client_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="En cours", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    due_date = Column(Date, nullable=True)
    started_at = Column(Date, nullable=True)

    user = relationship("User", back_populates="projects", foreign_keys=[user_id])
    client = relationship("User", back_populates="client_projects", foreign_keys=[client_id])
    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    messages = relationship(
        "Message",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    events = relationship(
        "Event",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Event.created_at.desc()",
    )
    milestones = relationship(
        "Milestone",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Milestone.position",
    )


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # 'livrable' (déposé par le prestataire) ou 'piece_client' (déposé par le client).
    kind = Column(String(20), default="livrable", server_default="livrable", nullable=False)
    # NULL = non revu ; sinon 'approuve' ou 'revision_demandee'.
    review_status = Column(String(20), nullable=True)
    review_comment = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    project = relationship("Project", back_populates="documents")
    uploader = relationship("User", foreign_keys=[uploaded_by])


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    project = relationship("Project", back_populates="messages")
    author = relationship("User", foreign_keys=[author_id])


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    type = Column(String(50), nullable=False)
    summary = Column(String(500), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    project = relationship("Project", back_populates="events")
    actor = relationship("User", foreign_keys=[actor_id])


class Milestone(Base):
    __tablename__ = "milestones"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    position = Column(Integer, default=0, server_default="0", nullable=False)
    # 'a_faire' | 'en_cours' | 'fait'
    status = Column(String(20), default="a_faire", server_default="a_faire", nullable=False)
    due_date = Column(Date, nullable=True)

    project = relationship("Project", back_populates="milestones")
