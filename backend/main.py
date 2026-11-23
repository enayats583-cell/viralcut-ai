
from pathlib import Path
import shutil
import subprocess
import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).resolve().parent.parent
UPLOADS = BASE / "uploads"
OUTPUTS = BASE / "outputs"

UPLOADS.mkdir(exist_ok=True)
OUTPUTS.mkdir(exist_ok=True)

app = FastAPI(title="ViralCut AI")

app.mount(
    "/static",
    StaticFiles(directory=BASE / "frontend"),
    name="static"
)

@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE / "frontend" / "index.html").read_text()

@app.get("/api/health")
def health():
    return {"status": "ok", "app": "ViralCut AI"}

@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    suffix = Path(file.filename or "video.mp4").suffix or ".mp4"

    if suffix.lower() not in [".mp4", ".mov", ".mkv", ".webm"]:
        raise HTTPException(400, "Unsupported video format")

    job_id = uuid.uuid4().hex
    destination = UPLOADS / f"{job_id}{suffix.lower()}"

    with destination.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"job_id": job_id, "message": "Upload complete"}

@app.post("/api/clip/{job_id}")
def create_clip(
    job_id: str,
    start: float = 0,
    duration: float = 30,
    aspect: str = "9:16"
):
    matches = list(UPLOADS.glob(f"{job_id}.*"))

    if not matches:
        raise HTTPException(404, "Video not found")

    if duration <= 0 or duration > 180:
        raise HTTPException(400, "Invalid duration")

    ratios = {
        "9:16": "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280",
        "16:9": "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",
        "1:1": "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
    }

    if aspect not in ratios:
        raise HTTPException(400, "Invalid aspect ratio")

    output = OUTPUTS / f"{job_id}.mp4"

    command = [
        "ffmpeg", "-y",
        "-ss", str(max(0, start)),
        "-i", str(matches[0]),
        "-t", str(duration),
        "-vf", ratios[aspect],
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        str(output)
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=900
        )
    except FileNotFoundError:
        raise HTTPException(500, "FFmpeg not installed")

    if result.returncode != 0:
        raise HTTPException(500, result.stderr[-1000:])

    return {"download_url": f"/api/download/{output.name}"}

@app.get("/api/download/{filename}")
def download(filename: str):
    path = OUTPUTS / Path(filename).name

    if not path.exists():
        raise HTTPException(404, "Clip not found")

    return FileResponse(path, media_type="video/mp4")
          
