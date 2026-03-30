"""Pydantic request/response schemas for the bulletin board API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr


# ── User ──────────────────────────────────────────────────────────────────────


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    bio: str | None = None


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    bio: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Category ──────────────────────────────────────────────────────────────────


class CategoryCreate(BaseModel):
    name: str
    description: str | None = None


class CategoryResponse(BaseModel):
    id: int
    name: str
    description: str | None

    model_config = {"from_attributes": True}


# ── Post ──────────────────────────────────────────────────────────────────────


class PostCreate(BaseModel):
    title: str
    content: str
    category_id: int | None = None


class PostResponse(BaseModel):
    id: int
    title: str
    content: str
    author_id: int
    category_id: int | None
    view_count: int
    is_pinned: bool
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── Comment ───────────────────────────────────────────────────────────────────


class CommentCreate(BaseModel):
    content: str


class CommentResponse(BaseModel):
    id: int
    content: str
    post_id: int
    author_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
