# ViralCut AI — starter project

A self-hostable starter for turning user-owned or authorized long videos into short clips.

## Included
- Responsive Next.js landing/upload interface
- FastAPI backend with upload endpoint and job status
- FFmpeg-based clip extraction from uploaded media
- Basic speech transcript hook using faster-whisper (optional)
- Heuristic moment ranking scaffold (replace with a stronger model later)

## Important limitations
- This starter does **not** download arbitrary YouTube/live-stream URLs. Many platforms restrict downloading or provide no permitted direct media URL. Add integrations only where you have rights and the platform/API permits it.
- “Viral” cannot be guaranteed. The included ranking is a starter heuristic, not a prediction of virality.
- Free hosting tiers have storage, runtime, bandwidth and CPU limits. Public unlimited processing requires paid infrastructure or strict queues/quotas.
- Use only videos you own or have permission to process. Add moderation, abuse reporting, retention/deletion policies and rate limits before opening publicly.

## Run locally

### Requirements
- Node.js 20+
- Python 3.11+
- FFmpeg installed and available on PATH

### Backend
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend
In another terminal:
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:3000

Set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local` if needed.

## Next production steps
1. Add authentication and per-user project ownership.
2. Move uploads and outputs to object storage; never store large media on ephemeral server disks.
3. Add background workers (Redis + RQ/Celery) and a job queue.
4. Add upload size, duration, concurrency and daily quotas.
5. Add a rights confirmation checkbox and takedown/report process.
6. Add captions, face-aware reframing, language selection and downloadable ZIPs.
7. Add permitted URL integrations (official APIs or user-provided direct media URLs).
