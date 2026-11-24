
from pathlib import Path
from urllib.parse import urlparse
import shutil
import subprocess
import uuid
import re

import yt_dlp

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent.parent
UPLOADS = BASE / "uploads"
OUTPUTS = BASE / "outputs"
DOWNLOADS = BASE / "downloads"
FRONTEND = BASE / "frontend"

for folder in (UPLOADS, OUTPUTS, DOWNLOADS):
    folder.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ViralCut AI", version="2.0")

if FRONTEND.exists():
    app.mount(
        "/static",
        StaticFiles(directory=FRONTEND),
        name="static"
    )


class LinkRequest(BaseModel):
    url: str
    start: float = Field(default=0, ge=0)
    duration: float = Field(default=30, gt=0, le=180)
    aspect: str = "9:16"


class BatchRequest(BaseModel):
    job_id: str
    clip_duration: float = Field(default=30, gt=0, le=180)
    aspect: str = "9:16"
    start: float = Field(default=0, ge=0)
    end: float | None = Field(default=None, gt=0)


class EditRequest(BaseModel):
    job_id: str
    start: float = Field(default=0, ge=0)
    duration: float = Field(default=30, gt=0, le=180)
    aspect: str = "9:16"


RATIOS = {
    "9:16": "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280",
    "16:9": "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",
    "1:1": "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
}


def check_aspect(aspect):
    if aspect not in RATIOS:
        raise HTTPException(400, "Invalid video format")
    return RATIOS[aspect]


def safe_video(job_id):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(400, "Invalid job ID")

    files = list(UPLOADS.glob(f"{job_id}.*"))
    files += list(DOWNLOADS.glob(f"{job_id}.*"))

    if not files:
        raise HTTPException(404, "Video not found")

    return files[0]


def video_duration(path):
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path)
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            raise ValueError("Cannot read video duration")
        return float(result.stdout.strip())
    except Exception:
        raise HTTPException(500, "FFprobe error or invalid video")


def make_clip(source, output, start, duration, aspect):
    video_filter = check_aspect(aspect)

    command = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(source),
        "-t", str(duration),
        "-vf", video_filter,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-movflags", "+faststart",
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
        raise HTTPException(500, "FFmpeg is not installed")
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Video processing timed out")

    if result.returncode != 0:
        raise HTTPException(500, result.stderr[-1500:])

    return output


@app.get("/", response_class=HTMLResponse)
def home():
    index = FRONTEND / "index.html"
    if not index.exists():
        return "<h1>ViralCut AI Backend Running</h1>"
    return index.read_text(encoding="utf-8")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "app": "ViralCut AI",
        "version": "2.0"
    }


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    suffix = Path(file.filename or "video.mp4").suffix.lower()

    if suffix not in [".mp4", ".mov", ".mkv", ".webm"]:
        raise HTTPException(400, "Unsupported video format")

    job_id = uuid.uuid4().hex
    destination = UPLOADS / f"{job_id}{suffix}"

    try:
        with destination.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        await file.close()

    return {
        "job_id": job_id,
        "message": "Upload complete"
    }


@app.post("/api/link")
def download_link(request: LinkRequest):
    parsed = urlparse(request.url)
    host = (parsed.hostname or "").lower()

    allowed = (
        host == "youtube.com"
        or host.endswith(".youtube.com")
        or host == "youtu.be"
        or host == "kick.com"
        or host.endswith(".kick.com")
    )

    if parsed.scheme != "https" or not allowed:
        raise HTTPException(400, "Only HTTPS YouTube and Kick links are allowed")

    if parsed.username or parsed.password:
        raise HTTPException(400, "Invalid URL")

    check_aspect(request.aspect)

    job_id = uuid.uuid4().hex
    output = DOWNLOADS / f"{job_id}.mp4"

    options = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(output),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "max_filesize": 2 * 1024 * 1024 * 1024
    }

    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(request.url, download=True)

        if info.get("is_live"):
            output.unlink(missing_ok=True)
            raise HTTPException(
                400,
                "Live streams need a separate live recording workflow. Use a completed VOD."
            )

    except HTTPException:
        raise
    except Exception as error:
        output.unlink(missing_ok=True)
        raise HTTPException(400, f"Video download failed: {str(error)[:300]}")

    if not output.exists():
        raise HTTPException(500, "Downloaded video file not found")

    return {
        "job_id": job_id,
        "title": info.get("title", "Video"),
        "duration": info.get("duration"),
        "message": "Video downloaded successfully"
    }


@app.post("/api/clip/{job_id}")
def create_clip(
    job_id: str,
    start: float = 0,
    duration: float = 30,
    aspect: str = "9:16"
):
    source = safe_video(job_id)
    length = video_duration(source)

    if duration <= 0 or duration > 180:
        raise HTTPException(400, "Clip duration must be 1–180 seconds")

    if start < 0 or start >= length:
        raise HTTPException(400, "Invalid start time")

    duration = min(duration, length - start)
    output = OUTPUTS / f"{uuid.uuid4().hex}.mp4"

    make_clip(source, output, start, duration, aspect)

    return {
        "download_url": f"/api/download/{output.name}",
        "filename": output.name
    }


@app.post("/api/batch")
def create_batch(request: BatchRequest):
    source = safe_video(request.job_id)
    total = video_duration(source)
    check_aspect(request.aspect)

    end = min(request.end if request.end is not None else total, total)

    if request.start >= end:
        raise HTTPException(400, "Invalid video range")

    clips = []
    position = request.start

    while position < end:
        duration = min(request.clip_duration, end - position)
        filename = f"{uuid.uuid4().hex}.mp4"
        output = OUTPUTS / filename

        make_clip(
            source,
            output,
            position,
            duration,
            request.aspect
        )

        clips.append({
            "filename": filename,
            "start": round(position, 2),
            "duration": round(duration, 2),
            "download_url": f"/api/download/{filename}"
        })

        position += request.clip_duration

    return {
        "total_clips": len(clips),
        "clips": clips,
        "message": "Batch processing complete"
    }


@app.post("/api/edit")
def edit_clip(request: EditRequest):
    source = safe_video(request.job_id)
    total = video_duration(source)

    if request.start >= total:
        raise HTTPException(400, "Invalid start time")

    duration = min(request.duration, total - request.start)
    filename = f"{uuid.uuid4().hex}.mp4"
    output = OUTPUTS / filename

    make_clip(
        source,
        output,
        request.start,
        duration,
        request.aspect
    )

    return {
        "filename": filename,
        "download_url": f"/api/download/{filename}",
        "message": "Edited clip created"
    }


@app.get("/api/download/{filename}")
def download(filename: str):
    if not re.fullmatch(r"[a-f0-9]{32}\.mp4", filename):
        raise HTTPException(400, "Invalid filename")

    path = OUTPUTS / filename

    if not path.exists():
        raise HTTPException(404, "Clip not found")

    return FileResponse(
        path,
        media_type="video/mp4",
        filename=filename
    )
    
