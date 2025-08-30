# app/routers/images.py
from fastapi import APIRouter, Query, Response
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

router = APIRouter(prefix="/images", tags=["images"])

class ImageOut(BaseModel):
    id: int
    owner: str
    filename: str
    kind: str            # "original" | "grayscale" | "edge"
    status: str          # "ready" | "processing" | "failed"
    created_at: datetime

SORT_FIELDS = {"created_at", "filename", "kind", "status", "id"}
SORT_ORDERS = {"asc", "desc"}

@router.get("/", response_model=List[ImageOut])
def list_images(
    response: Response,
    # pagination (support both styles)
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    page: Optional[int] = Query(None, ge=1),
    per_page: Optional[int] = Query(None, ge=1, le=100),

    # filtering
    owner: Optional[str] = None,
    kind: Optional[str] = Query(None, pattern="^(original|grayscale|edge)$"),
    status: Optional[str] = Query(None, pattern="^(ready|processing|failed)$"),
    created_after: Optional[datetime] = None,
    created_before: Optional[datetime] = None,

    # sorting
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
):
    # normalize pagination
    if page is not None or per_page is not None:
        p = page or 1
        pp = per_page or limit
        limit, offset = pp, (p - 1) * pp

    # validate sorting
    if sort_by not in SORT_FIELDS:
        sort_by = "created_at"
    if order not in SORT_ORDERS:
        order = "desc"

    # ---------- OPTION A: in-memory store (quick test) ----------
    try:
        from app.data_store import IMAGES  # <- create this in Step 3
        data = IMAGES.copy()
        use_db = False
    except Exception:
        data = []
        use_db = True

    items: List[ImageOut] = []

    if not use_db:
        # filter
        if owner:
            data = [x for x in data if x["owner"] == owner]
        if kind:
            data = [x for x in data if x["kind"] == kind]
        if status:
            data = [x for x in data if x["status"] == status]
        if created_after:
            data = [x for x in data if x["created_at"] >= created_after]
        if created_before:
            data = [x for x in data if x["created_at"] <= created_before]

        total = len(data)
        reverse = (order == "desc")
        data.sort(key=lambda x: x[sort_by], reverse=reverse)
        page_items = data[offset: offset + limit]
        items = [ImageOut(**it) for it in page_items]

    else:
        # ---------- OPTION B: SQLAlchemy (flip to real DB) ----------
        # from app.db import SessionLocal
        # from app.models import Image  # your SQLAlchemy model
        # with SessionLocal() as db:
        #     q = db.query(Image)
        #     if owner: q = q.filter(Image.owner == owner)
        #     if kind: q = q.filter(Image.kind == kind)
        #     if status: q = q.filter(Image.status == status)
        #     if created_after: q = q.filter(Image.created_at >= created_after)
        #     if created_before: q = q.filter(Image.created_at <= created_before)
        #     total = q.count()
        #     sort_col = getattr(Image, sort_by)
        #     q = q.order_by(sort_col.asc() if order == "asc" else sort_col.desc())
        #     rows = q.offset(offset).limit(limit).all()
        #     items = [
        #         ImageOut(
        #             id=r.id, owner=r.owner, filename=r.filename,
        #             kind=r.kind, status=r.status, created_at=r.created_at
        #         ) for r in rows
        #     ]
        total = 0  # placeholder if DB not wired

    # headers: total + RFC5988 pagination links
    response.headers["X-Total-Count"] = str(total)

    def build_link(off, lim):
        qs = []
        qs.append(f"limit={lim}")
        qs.append(f"offset={off}")
        if owner: qs.append(f"owner={owner}")
        if kind: qs.append(f"kind={kind}")
        if status: qs.append(f"status={status}")
        if created_after: qs.append(f"created_after={created_after.isoformat()}")
        if created_before: qs.append(f"created_before={created_before.isoformat()}")
        qs.append(f"sort_by={sort_by}")
        qs.append(f"order={order}")
        return f'</v1/images?{"&".join(qs)}>'

    links = []
    links.append(build_link(offset, limit) + '; rel="self"')
    if offset + limit < total:
        links.append(build_link(offset + limit, limit) + '; rel="next"')
    if offset > 0:
        prev_off = max(0, offset - limit)
        links.append(build_link(prev_off, limit) + '; rel="prev"')
    if total > 0:
        last_page_off = ((total - 1) // limit) * limit
        links.append(build_link(last_page_off, limit) + '; rel="last"')

    response.headers["Link"] = ", ".join(links)
    return items
