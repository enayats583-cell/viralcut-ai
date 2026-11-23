# ViralCut AI — Starter Project

A starter scaffold for a personal AI clipping website. It includes:
- FastAPI backend
- Upload endpoint for videos
- Basic FFmpeg-based vertical/square/wide clip rendering
- A simple browser UI

## Important
This is a starter project, not a finished hosted SaaS. You need a server with FFmpeg installed.
Only process videos/streams you own or have permission to use. Some YouTube/Kick URLs may not be downloadable; platform restrictions and live-stream availability apply.

## Run locally
1. Install Python 3.11+ and FFmpeg.
2. In this folder run:
   `python -m venv .venv`
3. Activate the environment, then:
   `pip install -r requirements.txt`
4. Start the backend:
   `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
5. Open `http://localhost:8000`.

## Next development steps
- Add authenticated user accounts and an admin-only lifetime-premium flag.
- Add speech-to-text captions (for example, a Whisper-compatible service).
- Add scene/speech/highlight scoring for automatic moment selection.
- Add a job queue and cloud storage for long videos.
- Add authorized YouTube/Kick ingestion integrations where permitted.

Unlimited clips and lifetime premium should be implemented as account entitlements and server capacity policies, not as a client-side switch.
