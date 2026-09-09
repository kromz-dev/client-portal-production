from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


# ==============================================================================
# Authentication Schemas
# ==============================================================================

class UserRegister(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, description="User email address")
    password: str = Field(..., min_length=6, max_length=128, description="User password (min 6 characters)")


class UserLogin(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    email: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Document Schemas
# ==============================================================================

class DocumentResponse(BaseModel):
    id: int
    project_id: int
    filename: str
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Project Schemas
# ==============================================================================

class ProjectCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[Literal["En attente", "En cours", "Terminé"]] = "En cours"


class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[Literal["En attente", "En cours", "Terminé"]] = None


class ProjectResponse(BaseModel):
    id: int
    user_id: int
    title: str
    description: Optional[str] = None
    status: str
    created_at: datetime
    documents: List[DocumentResponse] = []

    model_config = ConfigDict(from_attributes=True)
