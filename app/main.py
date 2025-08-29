from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from PIL import Image, ImageFilter, UnidentifiedImageError
from io import BytesIO

# Auth (uses your existing auth.py)
from app.auth import verify_token, router as auth_router

app = FastAPI(title="Image Processing API (MVP)")

@app.get("/health")
def health():
    return {"status": "ok"}

def to_stream(img: Image.Image, fmt: str = "PNG") -> StreamingResponse:
    buf = BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png", headers={
        "Content-Disposition": 'inline; filename="output.png"'
    })

def open_image_or_400(file: UploadFile) -> Image.Image:
    try:
        img = Image.open(file.file)
        img.load()  # ensure it actually reads (catches truncated inputs)
        return img
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="Invalid image file")

# === Image endpoints (plural) ===

@app.post("/images/grayscale")
async def grayscale(file: UploadFile = File(...), current = Depends(verify_token)):
    img = open_image_or_400(file).convert("RGB")
    gray = img.convert("L")
    return to_stream(gray, "PNG")

@app.post("/images/resize")
async def resize(
    w: int = Query(..., gt=0, le=8000),
    h: int = Query(..., gt=0, le=8000),
    file: UploadFile = File(...),
):
    img = open_image_or_400(file).convert("RGB")
    resized = img.resize((w, h))
    return to_stream(resized, "PNG")

@app.post("/images/edges")
async def edges(file: UploadFile = File(...)):
    img = open_image_or_400(file).convert("L")
    edged = img.filter(ImageFilter.FIND_EDGES)
    return to_stream(edged, "PNG")

# === Auth endpoints (from your auth router) ===
app.include_router(auth_router)

