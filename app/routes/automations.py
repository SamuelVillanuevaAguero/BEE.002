from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.automation import *
from app.schemas.automation import (
    AutomationCreate,
    AutomationResponse,
    AutomationUpdate
)
from app.services import automation_service

router = APIRouter(prefix="/automations", tags=["Automations"])

# ── CRUD ──────────────────────────────────────────────────────────────────────
@router.post("/", response_model=AutomationResponse, status_code=status.HTTP_201_CREATED)
def create_automation_setting(payload: AutomationCreate, db: Session = Depends(get_db)):
    try:
        return automation_service.create_automation_setting(db, payload)
    except HTTPException as http_exception:
        raise http_exception
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TypeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Server error")


@router.get("/", response_model=list[AutomationResponse])
def list_automation_settings(db: Session = Depends(get_db)):
    try:
        return automation_service.list_automation_settings(db)
    except HTTPException as http_exception:
        raise http_exception
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Server error")

@router.get("/{automation_id}", response_model=AutomationResponse)
def get_automation_setting(automation_id: str, db: Session = Depends(get_db)):
    try:
        return automation_service.get_automation_setting(db, automation_id)
    except HTTPException as http_exception:
        raise http_exception
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Server error")


@router.put("/{automation_id}", response_model=AutomationResponse)
def update_automation_setting(automation_id: str, payload: AutomationUpdate, db: Session = Depends(get_db)):
    try:
        return automation_service.update_automation_setting(db, automation_id, payload)
    except HTTPException as http_exception:
        raise http_exception
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TypeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Server error")


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_automation_setting(automation_id: str, db: Session = Depends(get_db)):
    try:
        return automation_service.delete_automation_setting(db, automation_id)
    except HTTPException as http_exception:
        raise http_exception
    except Exception as e:
        print(f"Error deleting automation setting: {e}")
        raise HTTPException(status_code=500, detail="Server error")
