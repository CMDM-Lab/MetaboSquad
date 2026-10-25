"""artifacts.py - list the files in an agent output folder"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.artifacts import list_folder

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


@router.get("")
def get_artifacts(folder: str = Query(...)) -> dict[str, Any]:
    try:
        return list_folder(folder)
    except ValueError:
        raise HTTPException(status_code=403, detail="不合法的路徑")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="找不到資料夾")
