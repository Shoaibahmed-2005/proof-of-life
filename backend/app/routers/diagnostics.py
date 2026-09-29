"""Scan diagnostics from the app (officer): per-scan timing, fps, SNR, gates."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from sqlmodel import select

from app.core.deps import CurrentOfficer, DbSession
from app.db.models import ScanDiagnostic

router = APIRouter()

CSV_FIELDS = [c for c in ScanDiagnostic.model_fields]


@router.get("/diagnostics", summary="Recent scan diagnostics (officer)")
def list_diagnostics(db: DbSession, officer: CurrentOfficer,
                     limit: int = Query(200, ge=1, le=5000), device: str | None = None) -> list[dict]:
    stmt = select(ScanDiagnostic)
    if device:
        stmt = stmt.where(ScanDiagnostic.device_model == device)
    rows = db.exec(stmt.order_by(ScanDiagnostic.id.desc()).limit(limit)).all()
    return [r.model_dump(mode="json") for r in rows]


@router.get("/diagnostics.csv", response_class=PlainTextResponse, summary="Scan diagnostics as CSV (officer)")
def diagnostics_csv(db: DbSession, officer: CurrentOfficer) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for r in db.exec(select(ScanDiagnostic).order_by(ScanDiagnostic.id)).all():
        writer.writerow(r.model_dump(mode="json"))
    return buf.getvalue()
