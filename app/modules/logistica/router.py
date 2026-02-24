from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from . import models, schemas

router = APIRouter(prefix="/log", tags=["Bitácora"])


