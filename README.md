# 🦺 SafetyLens AI — Site Ops Command

Real-time PPE compliance platform: custom-trained YOLOv8 detects workers,
helmets and vests on any camera feed; a rules engine raises temporally-confirmed
violations; an industrial command center streams alerts, snapshots and analytics.

## Team Roles

| Role                | Ownership                                          |
| ------------------- | -------------------------------------------------- |
| Backend Developer   | FastAPI, WebSocket pipeline, auth, settings API    |
| AI/ML Engineer      | YOLOv8 training, compliance engine, model registry |
| Cloud Engineer      | Docker, deployment, managed DB (Phase 2)           |
| DB & UI/UX Designer | Schema, industrial design system, dashboards       |
| DevOps Engineer     | Git workflow, CI, Docker, release discipline       |

## Quickstart (local)

```
cd backend
python -m venv venv && venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
pip install -r requirements.txt
python -m uvicorn main:app --port 8000
```

Open http://localhost:8000 — login: `admin/admin123` · `viewer/view123`

## Docker

```
docker compose up --build
```

## CI

Every push runs the pytest suite (compliance engine + database) via GitHub Actions.

## Branching

`main` = stable · `dev` = integration · `feature/*` = work-in-progress. PRs require green CI.
