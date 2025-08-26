from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import StreamingResponse
from PIL import Image, ImageFilter, UnidentifiedImageError
from io import BytesIO

app = FastAPI(title="Image Processing API (MVP)")

@app.get("/health")
def health():
    return {"status": "ok"}

def to_stream(img: Image.Image, fmt="PNG"):
    buf = BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

def open_image_or_400(file: UploadFile) -> Image.Image:
    try:
        img = Image.open(file.file)
        img.load()  # force load to catch truncated inputs
        return img
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="Invalid image file")

@app.post("/image/grayscale")
async def grayscale(file: UploadFile = File(...)):
    img = open_image_or_400(file).convert("RGB")
    gray = img.convert("L")
    return to_stream(gray, "PNG")

@app.post("/image/resize")
async def resize(
    w: int = Query(..., gt=0, le=8000),
    h: int = Query(..., gt=0, le=8000),
    file: UploadFile = File(...),
):
    img = open_image_or_400(file).convert("RGB")
    resized = img.resize((w, h))
    return to_stream(resized, "PNG")

@app.post("/image/edges")
async def edges(file: UploadFile = File(...)):
    img = open_image_or_400(file).convert("L")
    edged = img.filter(ImageFilter.FIND_EDGES)
    return to_stream(edged, "PNG")
