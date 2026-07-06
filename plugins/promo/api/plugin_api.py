"""
МАЯК plugin API — backend для вкладки «МАЯК» в Hermes dashboard.

Endpoints:
  GET    /api/plugins/promo/sources          — список источников мониторинга
  POST   /api/plugins/promo/sources          — добавить источник
  DELETE /api/plugins/promo/sources/<id>     — удалить источник
  GET    /api/plugins/promo/sessions         — текущие сессии интервьюера
  GET    /api/plugins/promo/weekly           — последний weekly plan
  GET    /api/plugins/promo/drafts           — черновики постов/видео

Использует FastAPI APIRouter по документации Hermes:
  https://hermes-agent.nousresearch.com/docs/guides/build-a-hermes-plugin
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter()

# Хранилище источников
SOURCES_FILE = Path.home() / ".hermes" / "profiles" / "personal_promo" / "state" / "promo-sources.yaml"
JOURNAL_ROOT = Path.home() / "MarketingClients" / "kirill-vechkasov-personal-brand" / "journal"


# ─── Pydantic модели ──────────────────────────────────────────────────

class SourceCreate(BaseModel):
    platform: str = Field(..., description="threads | youtube | reddit | x | telegram")
    handle: str = Field(..., description="@username, channel URL, или r/Subreddit")
    label: Optional[str] = Field(None, description="Опциональное имя для удобства")


class SourceItem(BaseModel):
    id: str
    platform: str
    handle: str
    label: Optional[str] = None
    added_at: str


class SourcesResponse(BaseModel):
    sources: list[SourceItem]
    total: int
    by_platform: dict[str, int]


# ─── Утилиты ─────────────────────────────────────────────────────────

def _ensure_sources_file() -> None:
    SOURCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not SOURCES_FILE.exists():
        SOURCES_FILE.write_text(
            yaml.safe_dump({"sources": []}, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )


def _load_sources() -> list[dict]:
    _ensure_sources_file()
    try:
        data = yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8")) or {}
        return data.get("sources", [])
    except yaml.YAMLError:
        return []


def _save_sources(sources: list[dict]) -> None:
    SOURCES_FILE.write_text(
        yaml.safe_dump({"sources": sources}, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )


def _make_id(platform: str, handle: str) -> str:
    import hashlib
    raw = f"{platform}:{handle}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


# ─── Endpoints ───────────────────────────────────────────────────────

@router.get("/sources", response_model=SourcesResponse)
async def get_sources():
    raw = _load_sources()
    by_platform: dict[str, int] = {}
    items = []
    for s in raw:
        items.append(SourceItem(
            id=s.get("id", _make_id(s["platform"], s["handle"])),
            platform=s["platform"],
            handle=s["handle"],
            label=s.get("label"),
            added_at=s.get("added_at", ""),
        ))
        by_platform[s["platform"]] = by_platform.get(s["platform"], 0) + 1
    return SourcesResponse(sources=items, total=len(items), by_platform=by_platform)


@router.post("/sources")
async def add_source(source: SourceCreate):
    if source.platform not in ("threads", "youtube", "reddit", "x", "telegram"):
        raise HTTPException(status_code=400, detail=f"Unknown platform: {source.platform}")

    sources = _load_sources()
    new_id = _make_id(source.platform, source.handle)

    if any(s.get("id") == new_id for s in sources):
        raise HTTPException(status_code=409, detail="Source already exists")

    sources.append({
        "id": new_id,
        "platform": source.platform,
        "handle": source.handle.strip(),
        "label": source.label.strip() if source.label else None,
        "added_at": datetime.utcnow().isoformat(),
    })

    _save_sources(sources)
    return {"ok": True, "id": new_id, "total": len(sources)}


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str):
    sources = _load_sources()
    new_sources = [s for s in sources if s.get("id") != source_id]
    if len(new_sources) == len(sources):
        raise HTTPException(status_code=404, detail="Source not found")
    _save_sources(new_sources)
    return {"ok": True, "removed": source_id, "total": len(new_sources)}


@router.get("/sessions")
async def get_sessions():
    state_file = Path.home() / "Work" / "apps" / "promo-daemon" / "state.json"
    if not state_file.exists():
        return {"active": False, "reason": "no state file"}
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"active": False, "reason": "corrupt state"}

    current = state.get("current_session", {})
    stats = state.get("stats", {})
    return {
        "active": current.get("state") not in ("idle", "closed", None),
        "session_id": current.get("session_id"),
        "plane": current.get("plane"),
        "questions_asked": current.get("questions_asked", 0),
        "started_at": current.get("started_at"),
        "last_question_at": current.get("last_question_at"),
        "stats": {
            "total_questions": stats.get("total_questions", 0),
            "total_answers": stats.get("total_answers", 0),
            "completion_rate": stats.get("completion_rate"),
            "content_potential_avg": stats.get("content_potential_avg"),
        },
    }


@router.get("/weekly")
async def get_latest_weekly():
    if not JOURNAL_ROOT.exists():
        return {"found": False}

    weekly_files = []
    for d in JOURNAL_ROOT.glob("*/??/weekly"):
        if d.exists():
            weekly_files.extend(d.glob("*.md"))

    if not weekly_files:
        return {"found": False}

    latest = max(weekly_files, key=lambda p: p.stat().st_mtime)
    return {
        "found": True,
        "path": str(latest.relative_to(Path.home())),
        "modified": latest.stat().st_mtime,
        "content": latest.read_text(encoding="utf-8"),
    }


@router.get("/drafts")
async def get_drafts():
    if not JOURNAL_ROOT.exists():
        return {"drafts": []}

    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=7)

    drafts = []
    for drafts_dir in JOURNAL_ROOT.glob("*/??/*/drafts"):
        if not drafts_dir.exists():
            continue
        for f in drafts_dir.glob("*.md"):
            try:
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    continue
                drafts.append({
                    "path": str(f.relative_to(Path.home())),
                    "modified": f.stat().st_mtime,
                    "title": f.stem,
                })
            except (OSError, ValueError):
                continue

    drafts.sort(key=lambda d: d["modified"], reverse=True)
    return {"drafts": drafts[:20]}