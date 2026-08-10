from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import security
from ..deps import get_token, require_user
from ..rate_limit import limiter
from ..schemas import LoginReq, SignupReq

router = APIRouter()


@router.post("/signup", status_code=201)
@limiter.limit("10/hour")
def signup(request: Request, body: SignupReq):
    try:
        user = security.create_user(body.name, body.email, body.password, body.phone)
    except security.AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    token = security.create_session(user["id"])
    return {"token": token, "user": user}


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, body: LoginReq):
    user = security.authenticate(body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = security.create_session(user["id"])
    return {"token": token, "user": user}


@router.get("/me")
def me(user: dict = Depends(require_user)):
    return {"user": user}


@router.post("/logout")
def logout(token: str = Depends(get_token)):
    security.delete_session(token)
    return {"ok": True}
