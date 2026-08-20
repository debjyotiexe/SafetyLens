# 🦺 SafetyLens AI — Site Ops Command

Real-time PPE compliance platform: custom-trained YOLOv8 detects workers, helmets and vests on live camera feeds; a rules engine raises temporally-confirmed violations; an industrial command center streams alerts, snapshots and analytics.

## Team Roles

| Role | Ownership |
| --- | --- |
| Backend Developer | FastAPI, WebSocket pipeline, authentication, settings API |
| AI/ML Engineer | YOLOv8 training, compliance engine, model registry |
| Cloud Engineer | Docker, deployment, managed database (Phase 2) |
| DB & UI/UX Designer | Database schema, industrial design system, dashboards |
| DevOps Engineer | Git workflow, CI, Docker, release discipline |

## Quickstart (Local)

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
pip install -r requirements.txt
python -m uvicorn main:app --port 8000
```

Open http://localhost:8000

**Demo login:** `admin / ********`  
**Viewer login:** `viewer / ********`

> Credentials are intentionally hidden from the repository documentation.

## Docker

```powershell
docker compose up --build
```

Open http://localhost:8000 after the container starts.

To stop the application:

```powershell
docker compose down
```

## CI

Every push and pull request runs the backend test suite through GitHub Actions.

Current automated tests cover:

- PPE compliance rules
- Helmet violation detection
- Vest violation detection
- Compliance configuration
- Database operations
- Authentication behavior

## Branching

`main` = stable / demo-ready  
`dev` = integration  
`feature/*` = work-in-progress

Recommended workflow:

1. Create a feature branch from `dev`.
2. Implement and test the change.
3. Push the feature branch.
4. Open a Pull Request into `dev`.
5. Ensure CI passes.
6. Review and merge.
7. Promote stable changes to `main`.

## Project Structure

```text
SafetyLens/
│
├── backend/
│   ├── tests/
│   │   ├── test_compliance.py
│   │   └── test_database.py
│   ├── config.py
│   ├── compliance.py
│   ├── database.py
│   ├── main.py
│   └── requirements.txt
│
├── frontend/
│   ├── css/
│   ├── js/
│   ├── index.html
│   ├── login.html
│   └── settings.html
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── .dockerignore
├── .gitignore
├── docker-compose.yml
├── Dockerfile
└── README.md
```

## System Architecture

```text
Camera / Video Feed
        │
        ▼
   YOLOv8 Detection
        │
        ▼
 Compliance Rules Engine
        │
        ├──► Violation Events
        ├──► Incident Snapshots
        └──► Compliance Analytics
        │
        ▼
 FastAPI / WebSocket Backend
        │
        ▼
 Industrial Command Center
```

## Repository Hygiene

The Git repository excludes generated, temporary, and large artifacts, including:

- Python virtual environments
- Python bytecode and `__pycache__`
- SQLite databases
- Generated snapshots
- YOLO model weights (`*.pt`)
- Training datasets
- Generated inference runs
- Large video assets
- Environment files and secrets

Large model weights, datasets, and media assets are managed separately from the source repository.

## Development Status

### Phase 1 — Engineering Foundation

- [x] Git repository
- [x] GitHub repository
- [x] Existing version history preserved
- [x] Clean Git history
- [x] Large media removed from Git history
- [x] Model weights removed from Git history
- [x] Generated inference artifacts removed from Git history
- [x] `.gitignore` configured
- [x] `.dockerignore` configured
- [x] Python requirements defined
- [x] Automated backend tests added
- [x] GitHub Actions CI configured
- [x] Docker configuration added
- [x] Docker Compose configuration added
- [x] Project documentation added

### Phase 2 — Cloud Infrastructure

Planned:

- [ ] Managed PostgreSQL database
- [ ] Cloud deployment
- [ ] Managed object storage
- [ ] Production environment configuration
- [ ] Production secrets management
- [ ] Application monitoring
- [ ] Production CI/CD
- [ ] Cloud-hosted model management

## Technology Stack

| Layer | Technology |
| --- | --- |
| AI / Computer Vision | YOLOv8 |
| Backend | Python, FastAPI |
| Real-time Communication | WebSockets |
| Database | SQLite (local), PostgreSQL planned |
| Frontend | HTML, CSS, JavaScript |
| Containerization | Docker, Docker Compose |
| Version Control | Git, GitHub |
| CI | GitHub Actions |
| Deployment | Planned for Phase 2 |

## License

This project is currently maintained as a project/demo application.
