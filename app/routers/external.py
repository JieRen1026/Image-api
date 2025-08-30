# app/routers/external.py
from fastapi import APIRouter, Query, HTTPException, Depends
from fastapi.responses import StreamingResponse
from typing import Optional
import urllib.parse
import os, uuid, asyncio
from io import BytesIO
from PIL import Image, ImageFilter
import httpx

from app.auth import get_current_user, User
from app.db import SessionLocal
from sqlalchemy.orm import Session
from app.models import ImageJob, JobStatus

router = APIRouter(prefix="/external", tags=["external"])

DATA_DIR = os.getenv("DATA_DIR", "/data")
UPLOADS = os.path.join(DATA_DIR, "uploads")
PROCESSED = os.path.join(DATA_DIR, "processed")

os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(PROCESSED, exist_ok=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def to_stream(img: Image.Image, fmt: str = "PNG") -> StreamingResponse:
    buf = BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    mt = "image/png" if fmt.upper() == "PNG" else "image/jpeg"
    return StreamingResponse(buf, media_type=mt,
                             headers={"Content-Disposition": 'inline; filename="output.png"'})

async def _get_with_retries(url: str, *, follow_redirects: bool = True, timeout: float = 20.0, attempts: int = 3) -> httpx.Response:
    async with httpx.AsyncClient(follow_redirects=follow_redirects, timeout=timeout) as client:
        last_exc = None
        for i in range(1, attempts + 1):
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    return r
                # retry on 429/5xx
                if r.status_code in (429, 500, 502, 503, 504):
                    await asyncio.sleep(0.6 * i)
                    continue
                # other non-200: no retry
                raise HTTPException(502, f"External API HTTP {r.status_code}")
            except (httpx.ReadTimeout, httpx.ConnectError) as e:
                last_exc = e
                await asyncio.sleep(0.6 * i)
        # exhausted
        if last_exc:
            raise HTTPException(502, f"External API network error: {last_exc}")
        raise HTTPException(502, "External API failed after retries")

@router.get("/random")
async def fetch_random_image(
    w: int = Query(512, ge=16, le=4096),
    h: int = Query(512, ge=16, le=4096),
    op: Optional[str] = Query(None, pattern="^(grayscale|edge)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Pull a random image from Picsum, optionally process, save job, return image.
    """
    url = f"https://picsum.photos/{w}/{h}"
    r = await _get_with_retries(url, follow_redirects=True)

    # simple content-type sanity check
    ctype = r.headers.get("content-type", "")
    if "image" not in ctype:
        raise HTTPException(502, f"External API returned non-image ({ctype})")

    # save original
    original_path = os.path.join(UPLOADS, f"ext_{uuid.uuid4().hex}.jpg")
    with open(original_path, "wb") as f:
        f.write(r.content)

    # create job
    job = ImageJob(
        user_id=user.username,
        original_path=original_path,
        mime_type="image/jpeg",
        params={"source": "picsum", "op": op},
        status=JobStatus.processing,
    )
    db.add(job); db.commit(); db.refresh(job)

    # process (optional)
    im = Image.open(BytesIO(r.content)).convert("RGB")
    if op == "grayscale":
        out = im.convert("L"); fmt = "PNG"
    elif op == "edge":
        out = im.convert("L").filter(ImageFilter.FIND_EDGES); fmt = "PNG"
    else:
        out = im; fmt = "JPEG"

    processed_path = os.path.join(PROCESSED, f"{job.id}.png" if fmt == "PNG" else f"{job.id}.jpg")
    out.save(processed_path)

    # update job
    job.processed_path = processed_path
    job.status = JobStatus.done
    job.width, job.height = out.size
    db.commit()

    return to_stream(out, fmt)

@router.get("/qrcode")
async def generate_qrcode(
    text: str = Query(..., min_length=1, max_length=2048),
    size: int = Query(256, ge=64, le=1024),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate a QR code via QRServer, store as a job, and return it.
    """
    enc = urllib.parse.quote_plus(text)
    url = f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&data={enc}"
    r = await _get_with_retries(url, follow_redirects=True)

    ctype = r.headers.get("content-type", "")
    if "image" not in ctype:
        raise HTTPException(502, f"External API returned non-image ({ctype})")

    # save original (same as processed)
    original_path = os.path.join(UPLOADS, f"qr_{uuid.uuid4().hex}.png")
    with open(original_path, "wb") as f:
        f.write(r.content)

    job = ImageJob(
        user_id=user.username,
        original_path=original_path,
        mime_type="image/png",
        params={"source": "qrserver", "text_len": len(text)},
        status=JobStatus.processing,
    )
    db.add(job); db.commit(); db.refresh(job)

    processed_path = os.path.join(PROCESSED, f"{job.id}.png")
    with open(processed_path, "wb") as f:
        f.write(r.content)

    job.processed_path = processed_path
    job.status = JobStatus.done
    job.width = size; job.height = size
    db.commit()

    img = Image.open(BytesIO(r.content))
    return to_stream(img, "PNG")
