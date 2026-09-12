# JSL GreenSteel – Carbon & Energy Optimization Calculator

Foundation build for **Problem Statement 3: Carbon and Energy Calculator for
Steelmaking**. This estimates carbon emissions per tonne of stainless steel
from: scrap %, virgin material %, grade, scrap quality, energy source,
electricity consumption, fuel consumption, and alloy additions.

> ⚠️ **All emission factors and reference data in `/data/*.json` are
> DEMO_PLACEHOLDER values.** No scientific emission factor has been
> invented as if it were real — every number is explicitly flagged
> `DEMO_PLACEHOLDER` in its file, in API responses, and in the UI. Replace
> them with sourced data before any real use.

## What's implemented in this foundation

- **Carbon calculator** — full working UI + API, wiring all 8 required inputs into a transparent, itemized per-tonne CO2e estimate.
- **Reference data service** — grades, scrap quality, energy sources, emission factors, baseline scenario.
- **Assumptions & Sources page** — every placeholder factor listed with its (placeholder) source note.
- Clean modular structure ready for the remaining modules (material balance, alloy chemistry, validated emissions, LP/MILP optimization, sensitivity, scenarios, validation, uncertainty).

## What's intentionally NOT implemented yet

Material balance, alloy chemistry, validated emission calculation,
LP/MILP optimization, sensitivity analysis, scenario comparison, formal
validation, and uncertainty analysis are stubbed as routed-but-placeholder
pages in the frontend. The backend's `/optimize` route exists and returns
`501 Not Implemented` by design — see `backend/optimization/lp_optimizer.py`.

## Project structure

```
frontend/          React + TypeScript + Tailwind + Recharts
  src/
    components/    Sidebar, TopBar, Panel, DemoDataBadge
    pages/          CalculatorPage, AssumptionsPage, PlannedModulePage
    charts/         EmissionsBreakdownChart (Recharts)
    services/       api.ts (fetch client)
    types/          calculator.ts, referenceData.ts
    utils/          format.ts
backend/            Python FastAPI
  main.py
  models/           Pydantic schemas
  services/         carbon_calculator.py
  data/             loader.py (reads project-level /data/*.json)
  optimization/     lp_optimizer.py (stub, raises NotImplementedError)
  validation/       input_validation.py
  tests/            pytest smoke tests
data/               emission_factors.json, steel_grades.json,
                    scrap_quality.json, energy_sources.json, baseline.json
                    (all DEMO_PLACEHOLDER)
```

## Running it

### Backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

- App: http://localhost:5173

The frontend expects the backend at `http://localhost:8000` by default
(override with a `VITE_API_BASE_URL` env var).

### Tests

```bash
cd backend
python -m pytest tests/ -v
```

## Verified working (this build)

- `pytest backend/tests` — 6/6 passing
- `npm run build` (tsc + vite) — succeeds with no type errors
- Backend and frontend dev servers boot and talk to each other; `/reference-data` returns zero validation issues; `/calculate/carbon` returns a correct itemized result for the baseline scenario.

## Deploying the whole repository to Vercel

This repository is configured as a single Vercel project. The Vite frontend is
built from `frontend/` and the FastAPI backend is exposed as the `/api`
Python function from `api/index.py`.

1. Push the entire repository to GitHub (including `api/`, `backend/`, `data/`,
   `frontend/`, `package.json`, `requirements.txt`, and `vercel.json`).
2. Import the GitHub repository into Vercel with the project root left as the
   repository root.
3. Keep the detected build settings, or use:
   - Build command: `npm run build`
   - Output directory: `frontend/dist`
4. Deploy. The frontend uses `/api` automatically in production, so no
   `VITE_API_BASE_URL` variable is required for this setup.

The deployed application and API will be available on the same domain. For
example, the API health check is `/api/health` and the API documentation is
at `/api/docs`. Scenario data is stored in a serverless filesystem and should
be moved to a database before relying on persistence in production.
