"""FastAPI server for the AutoGit backend."""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from bson import ObjectId
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

from agent import AIGitAgent


load_dotenv()

app = FastAPI(title="AutoGit Backend", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key = os.getenv("GROQ_API_KEY")
mongo_uri = os.getenv("MONGODB_URI")
mongo_database_name = os.getenv("MONGODB_DB", "autogit")
jwt_secret = os.getenv("JWT_SECRET", "autogit-dev-secret")
jwt_algorithm = "HS256"
jwt_expiry_days = int(os.getenv("JWT_EXPIRY_DAYS", "30"))

agent = AIGitAgent(groq_api_key=api_key) if api_key else None
mongo_client: AsyncIOMotorClient | None = None
users_collection = None
sessions_collection = None


class RegisterRequest(BaseModel):
    email: str
    password: str
    username: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthUser(BaseModel):
    id: str
    email: str
    username: str
    created_at: str


class SessionSummary(BaseModel):
    id: str
    title: str
    message_count: int
    updated_at: str


class AuthResponse(BaseModel):
    token: str
    user: AuthUser
    sessions: list[SessionSummary]
    active_session_id: str | None = None


class BootstrapResponse(BaseModel):
    authenticated: bool
    user: AuthUser | None = None
    sessions: list[SessionSummary] = []
    active_session_id: str | None = None


class SessionCreateRequest(BaseModel):
    title: str | None = None


class SessionCreateResponse(BaseModel):
    id: str
    title: str
    message_count: int
    updated_at: str


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    session_title: str


class ChatMessageItem(BaseModel):
    role: str
    content: str
    created_at: str


class ChatHistoryResponse(BaseModel):
    session_id: str
    title: str
    messages: list[ChatMessageItem]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_database() -> None:
    if users_collection is None or sessions_collection is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MongoDB Atlas is not configured",
        )


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return f"{salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, digest_hex = stored_hash.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False

    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return secrets.compare_digest(candidate, expected)


def _create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "iat": _now(),
        "exp": _now() + timedelta(days=jwt_expiry_days),
    }
    return jwt.encode(payload, jwt_secret, algorithm=jwt_algorithm)


def _serialize_user(document: dict[str, Any]) -> AuthUser:
    return AuthUser(
        id=str(document["_id"]),
        email=document["email"],
        username=document.get("username") or document["email"].split("@", 1)[0],
        created_at=document["created_at"].isoformat() if document.get("created_at") else _now().isoformat(),
    )


def _serialize_session_summary(document: dict[str, Any]) -> SessionSummary:
    messages = document.get("messages") or []
    return SessionSummary(
        id=str(document["_id"]),
        title=document.get("title") or "New chat",
        message_count=len(messages),
        updated_at=document["updated_at"].isoformat() if document.get("updated_at") else _now().isoformat(),
    )


def _serialize_message(document: dict[str, Any]) -> ChatMessageItem:
    return ChatMessageItem(
        role=document["role"],
        content=document["content"],
        created_at=document["created_at"].isoformat() if document.get("created_at") else _now().isoformat(),
    )


async def _get_user_document_from_token(token: str) -> dict[str, Any]:
    _require_database()

    try:
        payload = jwt.decode(token, jwt_secret, algorithms=[jwt_algorithm])
    except jwt.PyJWTError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from error

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    try:
        object_id = ObjectId(user_id)
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject") from error

    user_document = await users_collection.find_one({"_id": object_id})
    if user_document is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user_document


async def _get_current_user(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    return await _get_user_document_from_token(token)


async def _list_sessions_for_user(user_id: str) -> list[SessionSummary]:
    _require_database()

    documents = await sessions_collection.find({"user_id": ObjectId(user_id)}).sort("updated_at", -1).to_list(length=25)
    return [_serialize_session_summary(document) for document in documents]


async def _get_session_document(user_id: str, session_id: str) -> dict[str, Any]:
    _require_database()

    try:
        session_object_id = ObjectId(session_id)
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id") from error

    session_document = await sessions_collection.find_one({"_id": session_object_id, "user_id": ObjectId(user_id)})
    if session_document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")

    return session_document


async def _create_session_document(user_id: str, title: str | None = None) -> dict[str, Any]:
    _require_database()

    now = _now()
    session_document = {
        "user_id": ObjectId(user_id),
        "title": (title or "New chat").strip() or "New chat",
        "messages": [],
        "created_at": now,
        "updated_at": now,
    }
    result = await sessions_collection.insert_one(session_document)
    session_document["_id"] = result.inserted_id
    return session_document


async def _ensure_session_for_message(user_id: str, session_id: str | None, first_message: str) -> dict[str, Any]:
    if session_id:
        return await _get_session_document(user_id, session_id)

    preview = first_message.strip().replace("\n", " ")[:48]
    title = preview or "New chat"
    return await _create_session_document(user_id, title=title)


async def _append_chat_messages(session_document: dict[str, Any], user_message: str, assistant_message: str) -> None:
    _require_database()

    now = _now()
    await sessions_collection.update_one(
        {"_id": session_document["_id"]},
        {
            "$push": {
                "messages": {
                    "$each": [
                        {"role": "user", "content": user_message, "created_at": now},
                        {"role": "assistant", "content": assistant_message, "created_at": now},
                    ]
                }
            },
            "$set": {
                "updated_at": now,
                "title": session_document.get("title") or "New chat",
            },
        },
    )


@app.on_event("startup")
async def startup_event() -> None:
    global mongo_client, users_collection, sessions_collection

    if not mongo_uri:
        return

    mongo_client = AsyncIOMotorClient(mongo_uri)
    database = mongo_client[mongo_database_name]
    users_collection = database["users"]
    sessions_collection = database["chat_sessions"]

    await users_collection.create_index("email", unique=True)
    await sessions_collection.create_index([("user_id", 1), ("updated_at", -1)])


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/register", response_model=AuthResponse)
async def register(request: RegisterRequest) -> AuthResponse:
    _require_database()

    email = _normalize_email(request.email)
    password = request.password.strip()
    username = (request.username or email.split("@", 1)[0]).strip() or email.split("@", 1)[0]

    if "@" not in email or len(email) < 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A valid email address is required")
    if len(password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters")

    existing_user = await users_collection.find_one({"email": email})
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")

    now = _now()
    user_document = {
        "email": email,
        "username": username,
        "password_hash": _hash_password(password),
        "created_at": now,
        "updated_at": now,
    }

    result = await users_collection.insert_one(user_document)
    saved_user = await users_collection.find_one({"_id": result.inserted_id})
    if saved_user is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create account")

    sessions = await _list_sessions_for_user(str(result.inserted_id))
    token = _create_token(str(result.inserted_id))
    return AuthResponse(token=token, user=_serialize_user(saved_user), sessions=sessions, active_session_id=None)


@app.post("/auth/login", response_model=AuthResponse)
async def login(request: LoginRequest) -> AuthResponse:
    _require_database()

    email = _normalize_email(request.email)
    password = request.password.strip()

    user_document = await users_collection.find_one({"email": email})
    if user_document is None or not _verify_password(password, user_document.get("password_hash", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    sessions = await _list_sessions_for_user(str(user_document["_id"]))
    active_session_id = sessions[0].id if sessions else None
    token = _create_token(str(user_document["_id"]))
    return AuthResponse(token=token, user=_serialize_user(user_document), sessions=sessions, active_session_id=active_session_id)


@app.get("/auth/bootstrap", response_model=BootstrapResponse)
async def bootstrap(authorization: str | None = Header(default=None)) -> BootstrapResponse:
    if not authorization or not authorization.startswith("Bearer "):
        return BootstrapResponse(authenticated=False, sessions=[])

    try:
        user_document = await _get_current_user(authorization)
    except HTTPException:
        return BootstrapResponse(authenticated=False, sessions=[])

    sessions = await _list_sessions_for_user(str(user_document["_id"]))
    active_session_id = sessions[0].id if sessions else None
    return BootstrapResponse(
        authenticated=True,
        user=_serialize_user(user_document),
        sessions=sessions,
        active_session_id=active_session_id,
    )


@app.get("/auth/me", response_model=AuthUser)
async def me(authorization: str | None = Header(default=None)) -> AuthUser:
    user_document = await _get_current_user(authorization)
    return _serialize_user(user_document)


@app.post("/auth/logout")
async def logout() -> dict[str, bool]:
    return {"ok": True}


@app.post("/chats/sessions", response_model=SessionCreateResponse)
async def create_session(request: SessionCreateRequest, authorization: str | None = Header(default=None)) -> SessionCreateResponse:
    user_document = await _get_current_user(authorization)
    session_document = await _create_session_document(str(user_document["_id"]), request.title)
    summary = _serialize_session_summary(session_document)
    return SessionCreateResponse(
        id=summary.id,
        title=summary.title,
        message_count=summary.message_count,
        updated_at=summary.updated_at,
    )


@app.get("/chats/sessions", response_model=list[SessionSummary])
async def list_sessions(authorization: str | None = Header(default=None)) -> list[SessionSummary]:
    user_document = await _get_current_user(authorization)
    return await _list_sessions_for_user(str(user_document["_id"]))


@app.get("/chats/sessions/{session_id}", response_model=ChatHistoryResponse)
async def get_session_history(session_id: str, authorization: str | None = Header(default=None)) -> ChatHistoryResponse:
    user_document = await _get_current_user(authorization)
    session_document = await _get_session_document(str(user_document["_id"]), session_id)
    messages = [_serialize_message(message) for message in session_document.get("messages", [])]
    return ChatHistoryResponse(session_id=str(session_document["_id"]), title=session_document.get("title") or "New chat", messages=messages)


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, authorization: str | None = Header(default=None)) -> ChatResponse:
    if not api_key or agent is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="GROQ_API_KEY is not configured")

    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="message is required")

    user_document = await _get_current_user(authorization)
    session_document = await _ensure_session_for_message(str(user_document["_id"]), request.session_id, message)

    history = [{"role": entry["role"], "content": entry["content"]} for entry in session_document.get("messages", [])]
    response_text = agent.process_message(message, history)
    await _append_chat_messages(session_document, message, response_text)

    return ChatResponse(
        response=response_text,
        session_id=str(session_document["_id"]),
        session_title=session_document.get("title") or "New chat",
    )
