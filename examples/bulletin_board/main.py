"""Bulletin board (게시판) FastAPI application."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from .database import engine, get_db
from .models import Base, Category, Comment, Post, User
from .schemas import (
    CategoryCreate,
    CategoryResponse,
    CommentCreate,
    CommentResponse,
    PostCreate,
    PostResponse,
    UserCreate,
    UserResponse,
)

app = FastAPI(title="Bulletin Board API", version="0.1.0")

Base.metadata.create_all(bind=engine)

DB = Annotated[Session, Depends(get_db)]


# ── Users ─────────────────────────────────────────────────────────────────────


@app.post("/users/", response_model=UserResponse, status_code=201)
def create_user(body: UserCreate, db: DB) -> User:
    user = User(
        username=body.username,
        email=body.email,
        hashed_password=body.password,  # hash in production
        bio=body.bio,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: DB) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ── Categories ────────────────────────────────────────────────────────────────


@app.post("/categories/", response_model=CategoryResponse, status_code=201)
def create_category(body: CategoryCreate, db: DB) -> Category:
    category = Category(name=body.name, description=body.description)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@app.get("/categories/", response_model=list[CategoryResponse])
def list_categories(db: DB) -> list[Category]:
    return db.query(Category).all()


# ── Posts ─────────────────────────────────────────────────────────────────────


@app.post("/posts/", response_model=PostResponse, status_code=201)
def create_post(body: PostCreate, author_id: int, db: DB) -> Post:
    post = Post(
        title=body.title,
        content=body.content,
        author_id=author_id,
        category_id=body.category_id,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@app.get("/posts/", response_model=list[PostResponse])
def list_posts(db: DB, skip: int = 0, limit: int = 20) -> list[Post]:
    return db.query(Post).order_by(Post.created_at.desc()).offset(skip).limit(limit).all()


@app.get("/posts/{post_id}", response_model=PostResponse)
def get_post(post_id: int, db: DB) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    post.view_count += 1
    db.commit()
    db.refresh(post)
    return post


# ── Comments ──────────────────────────────────────────────────────────────────


@app.post("/posts/{post_id}/comments/", response_model=CommentResponse, status_code=201)
def create_comment(post_id: int, body: CommentCreate, author_id: int, db: DB) -> Comment:
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    comment = Comment(content=body.content, post_id=post_id, author_id=author_id)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


@app.get("/posts/{post_id}/comments/", response_model=list[CommentResponse])
def list_comments(post_id: int, db: DB) -> list[Comment]:
    return db.query(Comment).filter(Comment.post_id == post_id).all()
