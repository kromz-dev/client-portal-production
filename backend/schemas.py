from datetime import date, datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


# ==============================================================================
# Authentication Schemas
# ==============================================================================

class UserLogin(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    email: Optional[str] = None


class ChangePassword(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    full_name: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ActorSummary(BaseModel):
    """Résumé d'un utilisateur pour l'affichage d'un message ou d'un événement."""

    id: int
    email: str
    full_name: Optional[str] = None
    role: str

    model_config = ConfigDict(from_attributes=True)


class ClientSummary(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Clients Schemas (gestion par le prestataire)
# ==============================================================================

class ClientCreate(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class ClientResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClientListItem(ClientResponse):
    project_count: int = 0


# ==============================================================================
# Document Schemas
# ==============================================================================

class DocumentResponse(BaseModel):
    id: int
    project_id: int
    filename: str
    uploaded_at: datetime
    uploaded_by: Optional[int] = None
    kind: str
    review_status: Optional[str] = None
    review_comment: Optional[str] = None
    reviewed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DocumentReview(BaseModel):
    decision: Literal["approuve", "revision_demandee"]
    comment: Optional[str] = Field(None, max_length=2000)


# ==============================================================================
# Message Schemas
# ==============================================================================

class MessageCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)


class MessageResponse(BaseModel):
    id: int
    body: str
    created_at: datetime
    author: Optional[ActorSummary] = None

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Event Schemas
# ==============================================================================

class EventResponse(BaseModel):
    id: int
    type: str
    summary: str
    created_at: datetime
    actor: Optional[ActorSummary] = None

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Milestone Schemas
# ==============================================================================

class MilestoneCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    due_date: Optional[date] = None
    position: Optional[int] = Field(None, ge=0)


class MilestoneUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[Literal["a_faire", "en_cours", "fait"]] = None
    due_date: Optional[date] = None
    position: Optional[int] = Field(None, ge=0)


class MilestoneResponse(BaseModel):
    id: int
    project_id: int
    title: str
    position: int
    status: str
    due_date: Optional[date] = None

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Project Schemas
# ==============================================================================

class ProjectCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[Literal["En attente", "En cours", "Terminé"]] = "En cours"
    client_id: int
    due_date: Optional[date] = None
    started_at: Optional[date] = None


class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[Literal["En attente", "En cours", "Terminé"]] = None
    client_id: Optional[int] = None
    due_date: Optional[date] = None
    started_at: Optional[date] = None


class ProjectResponse(BaseModel):
    id: int
    user_id: int
    client_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    status: str
    created_at: datetime
    due_date: Optional[date] = None
    started_at: Optional[date] = None
    client: Optional[ClientSummary] = None
    documents: List[DocumentResponse] = []
    message_count: int = 0
    milestones_done: int = 0
    milestones_total: int = 0

    model_config = ConfigDict(from_attributes=True)


class ProjectDetailResponse(ProjectResponse):
    milestones: List[MilestoneResponse] = []
    events: List[EventResponse] = []
