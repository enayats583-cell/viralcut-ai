import os
import re
import json
import subprocess
import uuid
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi

BASE = Path(__file__).resolve().parent.parent
UPLOADS = BASE / "uploads"
OUTPUTS = BASE / "outputs"

UPLOADS.mkdir(exist_ok=True)
OUTPUTS.mkdir(exist_ok=True)

app = FastAPI(title="ViralCut AI")
app.mount("/static", StaticFiles(directory=BASE / "frontend"), name="static")


class LinkRequest(BaseModel):
    url: str
    duration: int = 30
    aspect: str = "9:16"


def extract_video_id(url: str) -> str:
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    if not match:
        raise HTTPException(400, "Sahi YouTube link paste karo.")
    return match.group(1)


def find_viral_start_time(video_id: str, duration: int) -> tuple[int, str]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return 30, "Default clip (GEMINI_API_KEY set nahi hai)"

    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "hi"])
        text_lines = [f"[{int(t['start'])}s] {t['text']}" for t in transcript[:250]]
        transcript_text = "\n".join(text_lines)
    except Exception:
        return 30, "Captions nahi mile, default 30s se clip banayi"

    prompt = (
        f"You are a viral short-form video editor. Read this YouTube transcript with timestamps "
        f"and pick the SINGLE most engaging, viral {duration}-second moment.\n"
        f'Return ONLY valid JSON like: {{"start": 120, "reason": "Funny clutch moment"}}\n\n'
        f"{transcript_text}"
    )

    try:
        res = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=25,
        )
        raw = res.json()["candidates"][0]["content"]["parts"][0]["text"]
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group(0))
        return max(0, int(data.get("start", 30))), str(data.get("reason", "AI selected moment"))
    except Exception:
        return 30, "AI busy tha, default 30s se clip banayi"


@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE / "frontend" / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health():
    return {"status": "ok", "app": "ViralCut AI"}


@app.post("/api/auto-clip")
def auto_clip(req: LinkRequest):
    if req.duration <= 0 or req.duration > 180:
        raise HTTPException(400, "Duration 1 se 180 seconds ke beech rakho.")

    ratios = {
        "9:16": "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280",
        "16:9": "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",
        "1:1": "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080",
    }
    if req.aspect not in ratios:
        raise HTTPException(400, "Invalid aspect ratio.")

    video_id = extract_video_id(req.url)
    start_sec, reason = find_viral_start_time(video_id, req.duration)
    end_sec = start_sec + req.duration

    job_id = uuid.uuid4().hex
    raw_file = UPLOADS / f"{job_id}.mp4"
    out_file = OUTPUTS / f"{job_id}.mp4"

    # Sirf zaroori hissa download karo taaki server fast chale
    dl_cmd = [
        "yt-dlp",
        "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
        "--download-sections", f"*{start_sec}-{end_sec}",
        "--force-keyframes-at-cuts",
        "--merge-output-format", "mp4",
        "-o", str(raw_file),
        req.url,
    ]
    dl = subprocess.run(dl_cmd, capture_output=True, text=True)
    if dl.returncode != 0 or not raw_file.exists():
        raise HTTPException(500, f"Video download fail hua: {dl.stderr[-250:]}")

    # 9:16 / 16:9 / 1:1 crop karo
    ff_cmd = [
        "ffmpeg", "-y",
        "-i", str(raw_file),
        "-t", str(req.duration),
        "-vf", ratios[req.aspect],
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac",
        str(out_file),
    ]
    ff = subprocess.run(ff_cmd, capture_output=True, text=True)
    raw_file.unlink(missing_ok=True)

    if ff.returncode != 0 or not out_file.exists():
        raise HTTPException(500, "FFmpeg clip processing fail hua.")

    return {
        "download_url": f"/api/download/{job_id}",
        "start_time": start_sec,
        "reason": reason,
    }


@app.get("/api/download/{job_id}")
def download_clip(job_id: str):
    file_path = OUTPUTS / f"{job_id}.mp4"
    if not file_path.exists():
        raise HTTPException(404, "Clip nahi mili.")
    return FileResponse(file_path, media_type="video/mp4", filename=f"viralcut_{job_id[:6]}.mp4")
    
