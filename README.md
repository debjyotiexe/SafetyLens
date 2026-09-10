# 🦺 SafetyLens AI — Site Ops Command

Real-time PPE compliance platform for construction and industrial sites.
A custom-trained YOLOv8 detects persons, helmets, vests, gloves, boots and goggles on live
camera feeds; a person-relative geometric rules engine raises temporally-confirmed
violations; an industrial command center streams alerts, snapshots and analytics.

## Features
- **Command Center** — live WebSocket video with annotated detections, KPIs, audio alarms
- **Multi-Camera** — browser feed + RTSP streams + video files, concurrent background processing
- **Incident Manager** — filterable violation log, snapshot evidence, resolve workflow, CSV export
- **Alert Dispatch** — email (SMTP + snapshot), webhook (Slack/Teams), log; failure-isolated handlers
- **Identity** — public landing page, registration, PBKDF2 hashing, token TTL, login throttling
- **User Management** — admin console for roles and account status (last-admin protected)
- **Storage Abstraction** — local backend today, cloud object-storage seam ready for Phase 3

## Quickstart (local)
```
cd backend
python -m venv venv && venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
pip install -r requirements.txt
python -m uvicorn main:app --port 8000
```
Open http://localhost:8000 — demo logins are seeded (see your team notes; credentials intentionally not published).

## Docker
```
docker compose up --build
```

## Tests
```
cd backend
python -m pytest tests/ -v
```
80 automated tests: compliance, pipeline parity, cameras, alerts, auth, incidents, storage, thresholds.

## Project Structure
```
backend/   main.py · pipeline.py · compliance.py · camera_manager.py ·
           alert_dispatch.py · storage.py · database.py · config.py ·
           train_model.py · tests/
frontend/  landing · login · register · index · incidents · cameras ·
           users · settings  + industrial HUD design system
```

## Detection Thresholds
- Positive/general classes: `0.30`
- Explicit negative PPE classes: `0.15`
- Temporal confirmation: `3` consecutive frames · cooldown `30s`

## Team Roles
| Role | Ownership |
|---|---|
| Backend Developer | FastAPI, WebSocket pipeline, auth, incidents API |
| AI/ML Engineer | YOLOv8 training, compliance engine, model registry |
| Cloud Engineer | Docker, camera threading, deployment (Phase 3) |
| DB & UI/UX Designer | Schema, industrial design system, dashboards |
| DevOps Engineer | Git workflow, CI, release discipline |

## Roadmap Status
- [x] Phase 1 — engineering foundation (Git, Docker, CI, detection engine)
- [x] Sprint B — enterprise features (cameras, incidents, alerts)
- [x] Sprint C-1 — identity, onboarding, storage abstraction
- [ ] Sprint C-2 — reports & analytics (in progress)
- [ ] Geofencing zones · worker tracking · demo mode
- [ ] Phase 3 — $0 cloud deployment (Postgres + object storage)

## Repository Hygiene
Excluded from Git: venvs, bytecode, SQLite DBs, snapshots, model weights (`*.pt`),
datasets, runs/, large media, `.env`, diagnostic scripts.