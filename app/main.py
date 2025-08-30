from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse, FileResponse
from PIL import Image, ImageFilter, UnidentifiedImageError
from io import BytesIO
import os, shutil, time, hashlib, secrets
from app.auth import verify_token, router as auth_router, get_current_user, require_role, User
from sqlalchemy.orm import Session
from app.db import init_db, SessionLocal
from app.models import ImageJob, JobStatus
import numpy as np, cv2
from app.routers.images import router as images_router
from app.routers.external import router as external_router

app = FastAPI(title="Image Processing API")

app.include_router(auth_router)
app.include_router(images_router, prefix="/v1")
app.include_router(external_router, prefix="/v1")

@app.on_event("startup")
      def _startup():
      init_db()

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

# --- Helpers ---
@app.get("/health")
def health():
    return {"status": "ok"}

def to_stream(img: Image.Image, fmt: str = "PNG") -> StreamingResponse:
    buf = BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png",
                             headers={"Content-Disposition": 'inline; filename="output.png"'})

def open_image_or_400(file: UploadFile) -> Image.Image:
    try:
        img = Image.open(file.file)
        img.load()
        return img
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="Invalid image file")

# == Image endpoints ==
@app.post("/images/grayscale")
async def grayscale(file: UploadFile = File(...), current=Depends(verify_token)):
    img = open_image_or_400(file).convert("RGB")
    gray = img.convert("L")
    return to_stream(gray, "PNG")

@app.post("/images/resize")
async def resize(
    current=Depends(verify_token),
    w: int = Query(..., gt=0, le=8000),
    h: int = Query(..., gt=0, le=8000),
    file: UploadFile = File(...),
):
    img = open_image_or_400(file).convert("RGB")
    resized = img.resize((w, h))
    return to_stream(resized, "PNG")

@app.post("/images/edges")
async def edges(
    current=Depends(verify_token),
    file: UploadFile = File(...),
    ksize: int = Query(5, ge=3, le=15),
    sigma: float = Query(1.4, ge=0.3, le=5.0),
    low: int = Query(50, ge=0, le=255),
    high: int = Query(150, ge=0, le=255),
    passes: int = Query(6, ge=1, le=20),
):
    data = await file.read()
    img_np = np.frombuffer(data, np.uint8)
    src = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
    if src is None:
        raise HTTPException(400, "Invalid image file")

    gray = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
    edges = None
    for _ in range(passes):
        blurred = cv2.GaussianBlur(gray, (ksize | 1, ksize | 1), sigma)
        edges = cv2.Canny(blurred, low, high, L2gradient=True)
        gray = edges

    pil_img = Image.fromarray(edges)
    return to_stream(pil_img, "PNG")

# === Job-based endpoints ===
@app.post("/images/jobs")
async def create_job(
    file: UploadFile = File(...),
    op: str = Query("grayscale", pattern="^(grayscale|edge)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not file.content_type.startswith("image/"):
        raise HTTPException(415, "Only image/* uploads are supported")

    # save original (binary file)
    original_path = os.path.join(UPLOADS, file.filename)
    with open(original_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # create metadata row
    job = ImageJob(
        user_id=user.username,
        original_path=original_path,
        mime_type=file.content_type,
        params={"op": op},
        status=JobStatus.processing,
    )
    db.add(job); db.commit(); db.refresh(job)

    # process
    try:
        im = Image.open(original_path).convert("RGB")
        w, h = im.size
        if op == "grayscale":
            out = im.convert("L")
        else:
            out = im.convert("L").filter(ImageFilter.FIND_EDGES)

        processed_path = os.path.join(PROCESSED, f"{job.id}.png")
        out.save(processed_path)

        job.processed_path = processed_path
        job.width, job.height = w, h
        job.status = JobStatus.done
        db.commit()
    except Exception as e:
        job.status = JobStatus.error
        job.error_message = str(e)
        db.commit()
        raise HTTPException(500, f"Processing failed: {e}")

    return {"job_id": job.id, "status": job.status, "mime_type": job.mime_type}

@app.get("/images/{job_id}/meta")
def get_meta(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.get(ImageJob, job_id)
    if not job or job.user_id != user.username:
        raise HTTPException(404, "Not found")
    return {
        "job_id": job.id,
        "status": job.status,
        "mime_type": job.mime_type,
        "params": job.params,
        "width": job.width,
        "height": job.height,
        "created_at": job.created_at.isoformat(),
        "original_path": job.original_path if job.status == JobStatus.done else None,
        "processed_path": job.processed_path if job.status == JobStatus.done else None,
        "error_message": job.error_message,
    }

@app.get("/images/{job_id}/file")
def get_file(
    job_id: str,
    kind: str = Query("processed", pattern="^(processed|original)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.get(ImageJob, job_id)
    if not job or job.user_id != user.username:
        raise HTTPException(404, "Not found")
    path = job.processed_path if kind == "processed" else job.original_path
    if not path or not os.path.exists(path):
        raise HTTPException(404, "file missing")
    return FileResponse(path, media_type=job.mime_type)

# === CPU intensive endpoint (kept) ===
@app.get("/cpu-burn")
def cpu_burn(ms: int = 250, iters: int = 60000):
    end = time.time() + ms/1000.0
    payload = secrets.token_bytes(1024)
    n = 0
    while time.time() < end:
        x = payload
        for _ in range(iters):
            x = hashlib.sha256(x).digest()
        n += 1
    return {"ok": True, "cycles": n, "pid": os.getpid()}

# === User/role endpoints (kept) ===
@app.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"username": user.username, "role": user.role}

@app.get("/admin/ping")
def admin_ping(user: User = Depends(require_role("admin"))):
    return {"ok": True, "msg": "admin only"}
