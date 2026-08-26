# Blueprint — Dataiku DSS Webapp Starter

A copy-to-start template for building on-brand webapps on Dataiku DSS.
If you know Python and data but have never shipped a web frontend, this gets you there:
the plumbing — local dev, DSS deployment, sidebar, settings, data access — is already wired up.
You fill in your domain logic.

**Stack:** Vue 3 (frontend) · FastAPI (backend) · Tailwind + vendored Dataiku design tokens · `reka-ui` (headless UI primitives) · `uv` / `npm` (package managers).

---

## Quick start

### Prerequisites

| Tool | What it is | Install |
|------|-----------|---------|
| [`uv`](https://docs.astral.sh/uv/) | Python package manager (replaces `pip`/`venv`) | `curl -Lsf https://astral.sh/uv/install.sh \| sh` |
| [`Node.js`](https://nodejs.org/) | JavaScript runtime; ships with `npm`, the frontend package manager | [nodejs.org](https://nodejs.org/) or `brew install node` |
| `dku` CLI | Dataiku command-line tool for deploying | Install globally so it's on your PATH, then authenticate with `dku auth` |
| `~/.dataiku/config.json` | Your local DSS credentials | |

### Get started

Clone the repo, set the app identity in `app.env`, start the app:

```bash
git clone git@github.com:dataiku/bs-blueprint.git my-app
cd my-app
# edit app.env: LIB_NS, APP_PREFIX, VITE_APP_NAME, ENV_NAME, DKU_INSTANCE, PROJECT_KEY
make dev                          # → open http://localhost:5173
```

`app.env` is the single source of truth for the app's identity and DSS target — that's
the whole setup, no code edits. `make dev` installs deps on first run and **blocks
(exits non-zero) until those six values are set**, listing any that are missing. The
frontend hot-reloads on save; the backend reloads on Python file saves. No DSS
connection needed for the Wizard, Charts, and Flow views.

> **Setting up with an AI coding agent?** Don't let it guess the identity/target values.
> The agent should discover the real options and ask you to confirm: derive `LIB_NS` /
> `APP_PREFIX` / `VITE_APP_NAME` from an app name you give it, list your DSS instances
> (`dku auth list`) for `DKU_INSTANCE`, and run `dku project list` to pick
> `PROJECT_KEY`. It writes them to `app.env` only after you confirm, then runs `make dev`.
> (See `AGENTS.md` for the exact agent instructions.)

```bash
make stop     # kill both servers
make status   # see which ports are running
make logs     # tail the log files in .run/logs/
make deps     # force-reinstall both Python and Node deps
```

### Deploy to DSS

Two one-time steps, then one command:

**One-time setup:**

1. The wizard sets `PROJECT_KEY` and `ENV_NAME` for you; to change them later, edit `app.env`:
   ```bash
   PROJECT_KEY=MY_PROJECT   # your DSS project key (uppercase, created automatically if missing)
   ENV_NAME=my-code-env     # a Python ≥3.11 code env on the DSS instance
   ```
   Leave `WEBAPP_ID=` empty — `make deploy` will create the webapp and write its ID back.

2. Make sure the code env is already created on DSS (DSS UI → Administration → Code envs),
   with at least `fastapi` and `uvicorn` installed.

**Deploy:**

```bash
make deploy
```

This builds the frontend, creates the DSS project and webapp if they don't exist yet,
uploads all code to the project library, patches the webapp definition, and restarts the
backend. The new webapp's ID is written back to `app.env` automatically so subsequent
deploys reuse the same webapp. Open the webapp in DSS — it should show your app.

---

## What even is a Dataiku webapp?

*This section is for readers who haven't built a DSS webapp before. Skip if you have.*

A DSS webapp is a small website that lives **inside a DSS project** and has direct access
to that project's datasets, models, LLMs, and variables. Users open it from the DSS
interface; it appears in an embedded frame (an `<iframe>`).

### Two halves

Every webapp in this template has two parts that run in different places:

- **Frontend** — the HTML/CSS/JavaScript that runs in the **user's browser**. This is
  what the user sees and clicks. It can't read DSS data directly — it has to ask the backend.

- **Backend** — a Python process that runs **on the DSS server** (or on your laptop in
  local dev). It has access to all the Dataiku Python APIs: datasets, LLMs, project
  variables, everything. It exposes an HTTP API (`/api/...`) that the frontend calls.

### Two run modes

The same codebase runs in two different configurations:

```
LOCAL DEV
─────────────────────────────────────────────────────────
  Browser                     Your laptop
  ┌────────────┐    :5173      ┌─────────────────┐
  │  Vue SPA   │◄─────────────│  Vite dev server│  npm run dev
  │            │              └─────────────────┘
  │  /api/...  │─────────────►┌─────────────────┐
  └────────────┘   :5000      │  FastAPI         │  uv run uvicorn
                              │  + dss_client    │──► ~/.dataiku/config.json
                              └─────────────────┘
  Vite proxies /api to FastAPI. Hot reload on every save.
  No deploy needed to iterate.


IN DSS (after make deploy)
─────────────────────────────────────────────────────────
  Browser                     DSS server
  ┌─────────────────────────────────────────────────────┐
  │  DSS UI                                             │
  │  ┌─────────────────────────────────────────────┐   │
  │  │ webapp iframe                               │   │
  │  │  ┌─────────────────────────────────────┐   │   │
  │  │  │  Vue SPA         served by FastAPI  │   │   │
  │  │  │  /api/... ──────────────────────►   │   │   │
  │  │  │              FastAPI               │   │   │
  │  │  │              + dataiku Python API  │   │   │
  │  │  └─────────────────────────────────────┘   │   │
  │  └─────────────────────────────────────────────┘   │
  └─────────────────────────────────────────────────────┘
  One FastAPI process serves the built frontend files
  AND answers /api calls. The dataiku module is
  available and talks to the surrounding DSS project.
```

The key insight: **the exact same Python code** handles both modes. `dss_client.get_project()`
detects which mode it's in and connects to DSS accordingly.

---

## Architecture in detail

### Repository layout

```
my-app/
│
├── app.env              ← Single source of truth: app name, project key, webapp ID,
│                          code env, ports. Edit here before deploying. Never commit .env.
├── .env.example         ← Template for local overrides (DSS URL/key if not using dku CLI)
├── Makefile             ← dev / stop / status / logs / deploy / install
├── pyproject.toml       ← Python dependencies (FastAPI, dataiku-api-client, pandas…)
│
├── backend/             ← Python. Runs on the server (locally: your laptop; in DSS: DSS server)
│   ├── app.py           ← The wiring: CORS, register all route modules, mount static files in DSS
│   ├── config.py        ← Reads APP_PREFIX from env → derives all other config variables
│   ├── dss_client.py    ← The dual-mode connector: dataiku.api_client() in DSS, dataikuapi locally
│   ├── routes/
│   │   ├── system.py    ← /api/system/health, /llms, /settings (GET + PUT)
│   │   └── example.py   ← /api/example/datasets, /preview  ← replace with your routes
│   └── services/
│       └── settings.py  ← App settings persisted to DSS project variables
│
├── dss_webapp/          ← The thin DSS glue layer (not application logic)
│   ├── deploy.sh        ← Uploads backend + built frontend to DSS, patches webapp definition
│   ├── backend.py       ← DSS-injected entry point: sets env vars, calls configure(app)
│   ├── html.html        ← Minimal HTML div that the webapp definition shows
│   ├── js.js            ← Creates a full-page iframe pointing at the FastAPI backend
│   └── css.css          ← body { margin: 0 } — hides the outer page chrome
│
└── frontend/            ← TypeScript/Vue. Runs in the user's browser.
    ├── package.json     ← Node dependencies (Vue, Vite, Tailwind, reka-ui…)
    ├── vite.config.ts   ← Build tool config: /api proxy, base path, single-bundle output
    ├── tsconfig*.json   ← TypeScript config
    └── src/
        ├── main.ts          ← App entry point: create Vue app, add Pinia + router, mount
        ├── App.vue          ← Root component: just <router-view />
        ├── styles/tokens.css ← Dataiku design tokens (colors, sidebar, radius, dark mode)
        ├── style.css        ← Tailwind setup + bridges tokens.css into Tailwind utilities
        ├── config.ts        ← App name + icon — the two things to change when you copy this
        ├── utils/api.ts     ← apiUrl(): the iframe path-prefix fix (see below)
        ├── router/index.ts  ← All pages live here; sidebar builds itself from route metadata
        ├── components/ui/   ← Local Ea* primitives (EaButton, EaSelect, EaEmpty…)
        ├── components/layout/AppSidebar.vue ← Local sidebar, built from route metadata
        ├── composables/useAppMenu.ts ← Turns route metadata into sidebar menu items
        ├── router/features.ts ← Optional-block routes, registered only when ENABLE_* is on
        ├── layouts/
        │   └── DefaultLayout.vue  ← Sidebar + <router-view /> shell
        ├── stores/
        │   ├── settings.ts  ← LLM selection and other settings, synced to DSS via /api

        └── views/
            ├── ExampleView.vue   ← Dataset picker + row preview: the full FE↔BE↔DSS demo
            └── SettingsView.vue  ← LLM picker backed by /api/system/settings
```

---

### The frontend, explained

The frontend is a **SPA** (Single-Page Application): one HTML file is loaded once, and
all navigation happens in JavaScript without full page reloads. We use **Vue 3** as the
framework — roughly similar to React or Angular if you've heard of those.

**Styling** comes from **Tailwind CSS** (utility classes like `text-sm`, `flex`, `gap-4`)
backed by **Dataiku design tokens** vendored into `src/styles/tokens.css` (colors, sidebar
palette, radius, dark mode). The token values mirror Dataiku's brand, so utilities like
`bg-primary` and `text-muted-foreground` make the app look like a Dataiku product. Form
controls and empty states are small local components in `src/components/ui/` (`EaSelect`,
`EaButton`, `EaEmpty`, `SettingsSwitchItem`) — token-styled wrappers, mostly built on
[`reka-ui`](https://reka-ui.com) headless primitives. There is no external component-library
dependency to track or update.

**Routing** — the sidebar is not manually built. Add a page like this in `router/index.ts`:

```typescript
{
  path: 'my-feature',
  name: 'myFeature',
  component: MyView,
  meta: { title: 'My Feature', icon: DatabaseIcon, menu: 'primary', order: 2 },
}
```

The `meta` object is all `AppSidebar` (`components/layout/AppSidebar.vue`, via the
`useAppMenu` composable) needs. The sidebar item appears automatically. Settings always lives
at the bottom (`menu: 'tertiary'`). Optional blocks declare their routes in
`router/features.ts` and are only registered when their `ENABLE_*` flag is on.

**State** is managed with **Pinia** (Vue's official state library, simpler than Redux).
One store ships with the blueprint:
- `settings.ts` — fetches and persists app settings through the backend `/api/system/settings`
  endpoint, which stores them in the DSS **project variables** (survives webapp restarts).

**API calls** always go through `apiUrl()` from `utils/api.ts`. See the non-obvious bits
section below for why.

---

### The backend, explained

The backend is a **FastAPI** application — a modern Python web framework, faster to write
than Flask and with automatic API documentation.

The central function is `configure(app)` in `backend/app.py`. It registers all the routes
and middleware onto a FastAPI app instance. In local dev, the module also creates its own
`app = FastAPI()` and calls `configure(app)`, so `uvicorn backend.app:app` works. In DSS,
the `dss_webapp/backend.py` entry point sets some environment variables and then calls
`configure(app)` on the DSS-injected `app` — it never creates its own instance.

The **dual-mode connector** in `backend/dss_client.py` is what makes the same code work
in both environments:

```python
def get_project():
    if config.DSS_MODE:                          # flag set by dss_webapp/backend.py in DSS
        import dataiku
        return dataiku.api_client().get_default_project()
    # local dev: read from ~/.dataiku/config.json
    return dataikuapi.DSSClient(...).get_project(config.PROJECT_KEY)
```

Every route that needs data calls `get_project()` — it never needs to know which mode it's in.
Detection is the explicit `DSS_MODE` flag, **not** `import dataiku` success: local dev installs
the real `dataiku` package, so that import succeeds locally too and would otherwise look like
in-DSS.

**Local dev installs `dataiku-internal-client` for real row previews.** The public
`dataiku-api-client` lists datasets and reads schemas, but its streaming reader differs from the
in-DSS one, so dataset *row* previews degrade to schema-only locally. The blueprint pulls in the
real internal `dataiku` (`dataiku-internal-client`, a required dev dependency) so `get_dataiku()`
in `dss_client.py` can run `dataiku.Dataset(...).get_dataframe()` against the remote instance —
identical to in-DSS. `dataikuapi` stays for the control-plane. See **Architecture decisions →
"Local dataset previews via `dataiku-internal-client`"** for the full rationale and trade-offs.

**Routes vs services** — routes handle HTTP (parse params, return JSON, raise HTTP errors).
Services contain the actual logic and Dataiku API calls. The `system.py` route calls
`project.list_llms(...)` to find available LLMs; `settings.py` uses
`project.get_variables()` / `project.set_variables()` to persist settings. The `example.py`
route calls `dataiku.Dataset(name).get_dataframe(limit=n)` in DSS to fetch rows.

---

### The DSS integration, explained

**Code env** — DSS runs Python in isolated environments called *code envs*. Your webapp
must have one specified (set `ENV_NAME` in `app.env`). It needs at least `fastapi`
and `uvicorn` installed. Python ≥3.11 is recommended (see tech notes).

**Project library** — each DSS project has a Python package directory (`python/`) that's
on `sys.path` for anything running in that project. `make deploy` uploads the backend and
the built frontend into `python/<LIB_NS>/` so DSS can import your code.

**Project variables** — a simple key-value store per DSS project, writable from Python
(`project.get_variables()` / `project.set_variables()`). The blueprint uses them to store
app settings (selected LLM, etc.) so they survive webapp restarts.

**What `make deploy` does, step by step:**

```
1. cd frontend && npm run build
     → Compiles Vue/TS → static HTML/JS/CSS in frontend/dist/

2. dku project create --if-not-exists
     → Creates the DSS project if it doesn't exist yet (idempotent).

3. dku webapp create  (only when WEBAPP_ID is empty in app.env)
     → Creates a new STANDARD webapp; writes the generated ID back to app.env.

4. dku library mkdir + write  (for every file in backend/ and frontend/dist/)
     → Uploads to python/<LIB_NS>/backend/ and python/<LIB_NS>/frontend_dist/

5. dku webapp get-definition → patch JSON → dku webapp set-definition
     → Sets backendFramework=FASTAPI, code env, and the html/js/css glue code

6. dku webapp stop + start
     → DSS imports <LIB_NS>.backend.app and calls configure(app) on its FastAPI instance
     → deploy.sh then polls `dku webapp status` until the backend reports running.
       If it doesn't come up within ~45 s, the script exits non-zero and prints the
       recent backend logs inline (from `dku webapp logs`) — no need to open the DSS UI.
```

---

### The non-obvious bits, explained

These are the parts that look like magic until you know why they exist. Don't remove them.

**`apiUrl()` and the router `baseUrl` — the iframe sub-path problem**

When DSS shows the webapp, the browser's URL looks like:
```
https://my-dss.company.com/web-apps-backends/MY_PROJECT/WEBAPP_ID/
```
The SPA is loaded inside an `<iframe>` at that path. If the frontend does a bare
`fetch('/api/datasets')`, the browser resolves it against the origin root:
```
https://my-dss.company.com/api/datasets   ← wrong! hits DSS, not your FastAPI
```
It needs to be:
```
https://my-dss.company.com/web-apps-backends/MY_PROJECT/WEBAPP_ID/api/datasets
```

`apiUrl()` in `utils/api.ts` solves this by capturing `window.location.pathname` at
startup — before Vue Router starts changing it — and prepending it to every API call.
The same logic applies to the router: it sets its `base` to the current pathname when
embedded, so that internal navigation stays under the iframe path.

In local dev (no iframe), `apiUrl('/api/x')` returns `/api/x` unchanged, and Vite's
proxy routes it to FastAPI. No special handling needed.

**`base: './'` and the single-bundle output — serving assets from a sub-path**

Vite's default is to produce assets with absolute paths (`/assets/index.js`). That breaks
in the DSS sub-path. Setting `base: './'` makes paths relative, so they resolve correctly
wherever the HTML file is served from.

Code-splitting (the default behavior where Vite produces many small JS chunks) also breaks
in DSS because the server doesn't reliably serve those extra files. The Vite config forces
a single output bundle:

```typescript
rollupOptions: {
  output: {
    entryFileNames: 'assets/index.js',
    chunkFileNames: 'assets/[name].js',
    assetFileNames: 'assets/index.[ext]',
  },
}
```

**`dedupe: ['vue', 'vue-router']` — preventing two copies of Vue**

Some dependencies (e.g. `reka-ui`) list Vue and vue-router as *peer dependencies*, meaning
they expect the consuming app to provide them. When npm resolves the dependency tree it can
sometimes install a second copy. Two Vue instances break reactivity silently and in
mysterious ways. The `dedupe` option in `vite.config.ts` forces Vite to always use the single
copy from the top-level `node_modules`.

**`from __future__ import annotations` / Python ≥3.11**

Modern Python type hints like `str | None` (union types) and `list[str]` (lowercase
generics) require Python 3.10+. DSS's default Python environment may be 3.9. The backend
uses `from __future__ import annotations` in every module as a compatibility shim. Better
still: create a code env with Python 3.11+ and set it in `app.env` as `ENV_NAME`.

---

## Configuration and renaming

All per-project settings live in `app.env`, which is checked into git. The identity
and DSS-target keys (`LIB_NS`, `APP_PREFIX`, `VITE_APP_NAME`, `ENV_NAME`, `PROJECT_KEY`,
`DKU_INSTANCE`) ship **empty** — fill them in, and `make dev` refuses to start until
they are set.

| Key | Used by | Purpose |
|-----|---------|---------|
| `LIB_NS` | `deploy.sh` | Python package namespace in the DSS library (`python/<LIB_NS>/`) |
| `APP_PREFIX` | `deploy.sh`, `backend/config.py` | Prefix for environment variables (`MYAPP_DSS_MODE`, etc.) |
| `VITE_APP_NAME` | `frontend/src/config.ts` | Display name in the sidebar header |
| `PROJECT_KEY` | `deploy.sh`, `backend/dss_client.py` | DSS project to deploy to and query locally |
| `WEBAPP_ID` | `deploy.sh` | ID of the webapp in that project |
| `ENV_NAME` | `deploy.sh` | Code env on the DSS instance (Python ≥3.11 recommended) |
| `BACKEND_PORT` | `Makefile` | Local dev port for FastAPI (default: 5000) |
| `FRONTEND_PORT` | `Makefile` | Local dev port for Vite (default: 5173) |

Local secrets that shouldn't be committed (DSS URL, API key override) go in `.env`
(gitignored). Copy `.env.example` to get started.

**Renaming** — edit the identity keys in `app.env` (`LIB_NS`, `APP_PREFIX`,
`VITE_APP_NAME`, `ENV_NAME`) and restart `make dev`. There are no in-code identity
tokens to rewrite: the display name and the FastAPI title read `VITE_APP_NAME`, the
DSS webapp Python is generated from `LIB_NS`/`APP_PREFIX` at deploy time, and the
sidebar icon is a fixed brand mark in `frontend/src/config.ts` (swap it there if you
want a different one).

---

## Extending the app

### Add a new page

1. Create `frontend/src/views/MyView.vue`
2. Add a route in `frontend/src/router/index.ts` — the sidebar builds itself from `meta`:
   ```typescript
   {
     path: 'my-feature',
     name: 'myFeature',
     component: MyView,
     meta: { title: 'My Feature', icon: DatabaseIcon, menu: 'primary', order: 2 },
   }
   ```
   Import your icon from `lucide-vue-next`. `menu: 'primary'` puts it in the main
   navigation; `menu: 'tertiary'` puts it in the footer (like Settings).
   See [The frontend, explained](#the-frontend-explained) for how the router drives the sidebar.

### Add a backend API endpoint

1. Create `backend/routes/my_feature.py`:
   ```python
   from fastapi import APIRouter
   from ..dss_client import get_project

   router = APIRouter(prefix="/api/my-feature")

   @router.get("/items")
   def list_items():
       project = get_project()           # works locally and in DSS
       datasets = project.list_datasets()
       return [{"name": d["name"]} for d in datasets]
   ```
2. Register it in `backend/app.py`:
   ```python
   from .routes.my_feature import router as my_feature_router
   # inside configure():
   app.include_router(my_feature_router)
   ```
3. Call it from the frontend with `fetch(apiUrl('/api/my-feature/items'))`.
   See [The non-obvious bits](#the-non-obvious-bits-explained) for why `apiUrl()` is needed.

### Add a settings field

Settings are persisted to DSS **project variables** (survive webapp restarts, shared
across all users of the webapp).

1. Add the key to `ALLOWED_KEYS` in `backend/services/settings.py` and to `_blank()`.
2. Add the field to `AppSettings` interface in `frontend/src/stores/settings.ts`.
3. Add a control in `frontend/src/views/SettingsView.vue`.

---

## Glossary

| Term | Plain-English definition |
|------|--------------------------|
| **SPA** | Single-Page Application — one HTML file, all navigation done in JS, no full page reloads |
| **Vite** | Build tool for the frontend: runs a fast dev server with hot reload and compiles TypeScript + Vue to plain JS/CSS for production |
| **Vue 3** | JavaScript framework for building UIs (comparable to React); uses `.vue` files with `<script>`, `<template>`, `<style>` |
| **Pinia** | Vue's state management library — a store is a reactive object shared across components |
| **Tailwind CSS** | Utility-class CSS library: instead of writing `.my-button { color: red }`, you write `class="text-red-500"` directly in HTML |
| **Design tokens** | CSS variables in `src/styles/tokens.css` (Dataiku colors, sidebar palette, radius, dark mode), bridged into Tailwind utilities so `bg-primary` etc. look like a Dataiku product |
| **reka-ui** | Headless (unstyled) Vue UI primitives used to build the local `Ea*` components in `src/components/ui/` |
| **FastAPI** | Python web framework: you decorate functions with `@router.get("/path")` and they become API endpoints |
| **`uv`** | Python package manager; `uv sync` reads `pyproject.toml` and creates a virtualenv with the right deps |
| **`npm`** | Node package manager (ships with Node.js); `npm install` reads `package.json` |
| **Code env** | DSS's isolated Python environment for a webapp or recipe; created in Administration → Code envs |
| **Project library** | The `python/` directory inside a DSS project that's on `sys.path` for everything in that project; `make deploy` uploads the backend here |
| **Project variables** | Key-value store per DSS project, readable and writable from Python at runtime; used here to persist app settings |
| **Managed folder** | DSS object for storing arbitrary files (PDFs, images, etc.) inside a project; use instead of the local filesystem (which isn't writable in DSS) |
| **iframe** | HTML element that embeds one website inside another; DSS shows webapps this way |

---

## Optional building blocks

The blueprint ships five optional, independently toggled features. All five are **on by default** so a new teammate sees the full catalogue of what's available on first boot. Turn off the ones you don't need by setting `ENABLE_*=0` in `app.env` (one line per flag) and restarting `make dev`.

The three **self-contained** blocks (Wizard, Charts, Flow) render with zero configuration — no DSS, no LLM. The two **DSS-dependent** blocks (Documents, Chatbot) need a Managed Folder or LLM and will show a "needs configuration" empty state until wired up.

### Wizard

A 3-step guided creation form that validates each step before proceeding, then POSTs a single payload. Demonstrates the multi-step input pattern: collect → validate → review → submit.

Each step is its own child route (`/wizard/basics`, `/wizard/details`, `/wizard/review`). The routes are tagged `meta.menuLevel: 'flow'`, which makes the app sidebar switch to its flow-level view: a vertical stepper with one circle per step, a hollow (disabled) circle for steps you can't reach yet, and a "Back" link to the app-level nav. Step disabling is driven by per-route `meta.state` callbacks reading the wizard Pinia store.

**What it adds:** a "New element" sidebar CTA, `POST /api/wizard/submit`. No persistence — replace the result logic in `backend/routes/wizard.py` with a real DSS write (project variables, dataset append, managed folder) when you're ready.

**Enable:**
```bash
ENABLE_WIZARD=1   # in app.env
```

**Verify locally:**
1. `make dev` → click "New element" → sidebar switches to the vertical stepper; Details and Review circles are hollow.
2. Fill in Name and Category → Next button enables, the remaining circles fill and become clickable.
3. Step 2 (Notes) is optional — Next always enabled.
4. Review step → click Create → success card shows the returned id.

**Graduation options:** the routed-steps structure already scales to longer or branching wizards — add a child route per step and (if needed) a `meta.state` callback to gate it.

---

### Charts

An ECharts dashboard (KPI sparklines, donut, gauge, bar/line charts) fed by **frontend mock
data** (`src/data/mock/`). It's a **frontend-only** block — there is no backend route — so it
demonstrates the chart-component pattern without needing a DSS connection.

**What it adds:** a "Charts" sidebar entry and the dashboard components in
`components/dashboard/*.vue`. Replace the mock data with a real DSS dataset read (add a backend
route like the other blocks and fetch via `apiUrl()`).

**Enable:**
```bash
ENABLE_CHARTS=1   # in app.env (frontend build flag only — read by Vite, not the backend)
```

**Verify locally:**
1. `make dev` → "Charts" appears in the sidebar.
2. The dashboard renders (KPIs, donut, gauge, timelines) from mock data.
3. Resize the window — charts autoresize.

**Using the chart components:** each component builds an ECharts `option` typed as
`EChartsOption` and registers its pieces with `use([…])`. Colors come from the chart design
tokens (`var(--chart-1..5)`), so they follow dark/light mode automatically.

---

### Flow

A Vue Flow node/edge graph rendered from a backend endpoint. Demonstrates how to turn domain data (pipeline stages, dataset dependencies, recipe graphs) into an interactive, pannable, zoomable node graph.

**What it adds:** a "Flow" sidebar entry, `GET /api/flow/sample` (4-node pipeline graph). Node positions are baked into the backend response — no layout library required for the hello-world.

**Enable:**
```bash
ENABLE_FLOW=1   # in app.env
```

**Verify locally:**
1. `make dev` → "Flow" appears in the sidebar.
2. A 4-node pipeline graph renders (Raw Data → Process → Enrich → Output).
3. Pan and zoom work; the canvas fits the graph on load.

**Graduation options:** for auto-layout of large graphs, add `@dagrejs/dagre` (npm) and compute node positions on the frontend — keep the backend response position-free in that case.

---

### Documents

Lets users upload files (PDF, images, text, audio/video) to a DSS Managed Folder, with metadata stored in SQLite. An optional LLM auto-describe feature (`ENABLE_DESCRIBE`) produces a 1–3 sentence summary of each file using the configured LLM.

**What it adds:** a "Documents" sidebar entry, six backend endpoints (`/api/documents`), a DSS Managed Folder (auto-created on first upload), the shared SQLite + persistence layer.

**Enable:**
```bash
# In app.env
ENABLE_DOCUMENTS=1

# Optional: LLM auto-describe (requires langchain-core + pymupdf in the code env)
ENABLE_DESCRIBE=1
```

**Verify locally:**
1. `make dev` → "Documents" appears in the sidebar.
2. Upload a file → it appears in the list.
3. Download link returns the original bytes.

**Folder auto-creation:** the backend looks up or creates a DSS Managed Folder named `<APP_PREFIX> Documents` on first upload, then caches its id in the app-settings project variable. If auto-creation fails (no writable connection on your local dev instance), create the folder manually in the DSS UI and set `documents_folder_id` in Settings.

---

### Chatbot (agent + tool-call approval)

An LLM agent that streams responses via SSE and can call tools. Mutating tools require the user's approval before execution — the agent suspends, the UI shows Allow/Deny buttons, the user decides, the agent resumes.

**What it adds:** an "Assistant" sidebar entry, conversation management (CRUD), the SSE message streaming endpoint, the permission broker, a tool registry (5 starter tools — 4 read-only + 1 mutating demo), conversation history in SQLite, and a "Tool permissions" section in Settings.

**Enable:**
```bash
ENABLE_CHATBOT=1   # in app.env
```

**Verify locally:**
1. `make dev` → "Assistant" appears in the sidebar.
2. Pick an LLM in Settings.
3. Type a message → tokens stream in.
4. Ask "list my datasets" → `list_datasets` runs automatically (policy: allow).
5. Ask to "make a note: hello" → `create_scratch_note` shows Allow/Deny buttons.
6. Click Allow → the agent resumes and completes its response.

**Starter tools shipped:**
| Tool | Policy | Purpose |
|---|---|---|
| `list_datasets` | allow | Lists all datasets in the project; demonstrates dual-mode DSS access |
| `inspect_dataset` | allow | Returns schema (column names + types) for a named dataset |
| `sample_data` | allow | Returns up to N rows from a dataset as a markdown table |
| `search_knowledge_base` | allow | Semantic search across all knowledge banks in the project |
| `create_scratch_note` | prompt | **Mutating demo** — writes to DSS project variables; demonstrates the full approval flow |

When `ENABLE_DOCUMENTS=1` is also set, two additional tools (`list_documents`, `read_document`) are added automatically.

**Both on together:** the agent gains `list_documents`/`read_document` tools and its system prompt includes a summary of uploaded documents, so it can answer questions about uploaded files.

---

### Flag reference

Each `ENABLE_*` flag in `app.env` controls **both** the backend route and the frontend sidebar
entry. Vite reads these flags directly at build time via `envPrefix: ['VITE_', 'ENABLE_']`
in `vite.config.ts` — no separate `VITE_ENABLE_*` line needed.

| Key | Purpose |
|---|---|
| `ENABLE_WIZARD` | Register Wizard route (`POST /api/wizard/submit`) + show sidebar entry |
| `ENABLE_CHARTS` | Register the Charts route + sidebar entry (frontend-only; mock data, no backend route) |
| `ENABLE_FLOW` | Register Flow route (`GET /api/flow/sample`) + show sidebar entry |
| `ENABLE_DOCUMENTS` | Register Documents routes + enable folder/SQLite + show sidebar entry |
| `ENABLE_CHATBOT` | Register Chatbot routes + agent loop + show sidebar entry |
| `ENABLE_DESCRIBE` | LLM auto-describe on upload (backend-only sub-option of Documents) |

---

## Architecture decisions & trade-offs

This blueprint makes several non-obvious choices. They are **deliberate**, documented here so your team can debate them, extend from them, or replace them when your app outgrows the starter constraints. Each entry follows the pattern: **Decision → Why → Trade-off → When to revisit.**

---

### SQLite for persistence

**Decision:** chat conversations, messages, and document metadata live in an embedded SQLite database. The live file location depends on context:

| Context | Path |
|---|---|
| Local dev | `<repo>/.run/state.db` |
| DSS (live) | `get_workload_local_folder_path() / state.db` — a per-webapp directory on the DSS instance disk (e.g. `/data/dataiku/run/webapps/<ID>/workload-local/`). Persists across backend restarts as long as the webapp is not fully redeployed. |

**Why:** SQLite gives real transactional semantics, indexes, foreign keys, and a clean data-access layer (`services/memory_state.py`). Alternatives were considered and explicitly rejected:
- *Project variables* — the single JSON blob per key has a size limit and lacks querying. Fine for a handful of settings, not for conversation history.
- *Managed-folder JSON* — loses transactional guarantees and becomes a concurrency hazard under concurrent requests.
- *External SQL connection* — no extra infra needed, especially valuable for a starter that should work on any DSS instance.

**Trade-off:** this is a **single-writer** design. SQLite does not support multiple concurrent writers. DSS webapp backends run single-process by default (`autoStartBackend` in the webapp definition), so this is safe as-is.

**When to revisit:**
- Your app needs more than one backend process (load balancing, zero-downtime deploys).
- You need true ACID guarantees across multiple concurrent users modifying shared data.

The upgrade path: swap `get_conn()` for a connection pool backed by a DSS SQL connection (Postgres, Snowflake, etc.). The service layer (`memory_state.py`, `documents_service.py`) is the only thing that changes — the routes and the agent loop are unaffected.

---

### Tool-call approval, not user RBAC

**Decision:** the chatbot uses a *tool-call approval* model (the agent asks before mutating; the user approves or denies inline) rather than user-level role-based access control.

**Why:** the tool-call approval model solves the most immediate safety concern for an agentic starter — giving users visibility and control over what the agent does — without requiring any user authentication infrastructure. Who can *open* the webapp is controlled by DSS (project permissions). Everyone who can open it shares the same capability level.

**What this is not:** this is not authorization. There is no concept of "admin vs. read-only user," no per-user data isolation, no audit log of who approved what.

**When to revisit:** when your app needs real per-user authorization (multi-tenant data, admin-only configuration changes, audit trails), build it by:
1. Resolving the DSS user with `dataiku.api_client().get_auth_info()` (see `services/current_user.py` for the pattern).
2. Mapping the user or their DSS group to a role (stored in project variables or a dedicated dataset).
3. Injecting a role check as a FastAPI dependency on routes that need it.
None of this infrastructure is absent by accident — it was left out to keep the starter focused.

---

### Single-bundle Vite output (no code-splitting)

**Decision:** `vite.config.ts` forces a single JavaScript output file (`assets/index.js`) and uses `base: './'` for relative asset paths.

**Why:** the frontend is served from inside a DSS webapp iframe at a sub-path (e.g. `https://my-dss.company.com/web-apps-backends/PROJECT/WEBAPP_ID/`). DSS's project-library serving does not reliably handle the chunk manifest that Vite's default code-splitting produces — requests for dynamically-imported chunks 404. A single bundle avoids this entirely.

**Trade-off:** the bundle cannot be lazy-loaded. All views — including disabled blocks — are bundled. It also means `import()` lazy routes cannot be used; all route components must be statically imported. With all five optional blocks enabled (the default), the JS bundle is approximately 1 MB minified / 350 KB gzipped, which includes echarts (~600 KB) and @vue-flow/core. If you don't use Charts or Flow and want to fully reclaim that weight, remove the npm packages (`npm remove echarts vue-echarts @vue-flow/core`) in addition to setting the flags to 0 — disabling the block via env flags alone hides the UI but does not shrink the bundle.

**When to revisit:** if the app grows to where the initial load time is noticeably slow (> 2–3 s on a reasonable connection), the right fix is to change the DSS library serving strategy (host the frontend externally or use a DSS API node with proper static-file handling) rather than fighting Vite's code-splitting within the current constraints.

---

### Dual-mode `get_project()` (one code path, two environments)

**Decision:** all DSS access goes through `backend/dss_client.py::get_project()`, which returns a `dataikuapi.DSSProject` in both local dev and in-DSS modes.

**Why:** the alternative — branching on `DSS_MODE` inside every route — produces duplicated logic that diverges over time. One accessor, two environments, no branching in business logic.

**Trade-off:** the local dev path adds a network round-trip to the remote DSS instance for every API call (no local mock). This is acceptable because the blueprint targets real-data development, not unit-testable mock data.

---

### Local dataset previews via `dataiku-internal-client`

**Decision:** local dev installs the **real in-DSS `dataiku` package** as a **required** dev dependency, pulled from the instance's own `dataiku-internal-client` tarball (`pyproject.toml` `[dependency-groups] dev`, pinned to the team instance URL `…/public/packages/dataiku-internal-client.tar.gz`). The public `dataiku-api-client` (`dataikuapi`) is kept. `backend/dss_client.py::get_dataiku()` configures the package for remote use (`set_remote_dss` + `set_default_project_key`) so `dataiku.Dataset(...).get_dataframe()` runs locally exactly as in DSS; `routes/example.py` and `tools/registry.py` read rows through it — **the single code path, no `dataikuapi` row-reading fallback** (run `uv sync` and it's always there).

**Why:** `dataiku-api-client` alone lists datasets and reads schemas, but its streaming `iter_rows()` diverges from the in-DSS implementation and raises mid-iteration — so dataset *row* previews silently degrade to schema-only locally. The internal `dataiku` reproduces the exact in-DSS data-plane. Two alternatives were rejected:
- *A local DSS kit on `PYTHONPATH`* — works, but requires every developer to have a kit installed and pins to whatever version they happen to have (e.g. a `14.4.2` kit against a `14.6.0` instance). The served tarball is **version-matched to the instance** and installs like any other dependency.
- *Dropping `dataikuapi` to "reduce dependencies"* — impossible. The internal `dataiku` is built **on top of** `dataikuapi` (`dataiku/core/intercom.py` → `from dataikuapi import DSSClient`; `dataiku.api_client()` returns a `dataikuapi.DSSClient`), and the entire control-plane the backend uses (`list_datasets`, `get_schema`, `list_llms`, `get_variables`/`set_variables`, managed folders, knowledge banks) is `dataikuapi`. The tarball neither bundles nor declares it. The two are **complementary**: `dataikuapi` = control-plane, `dataiku` = data-plane — and there's no weight to reclaim (`dataikuapi`'s deps are already pulled in).

**Trade-off:** the URL is **instance-specific and hardcoded** for our team, and unversioned — a DSS upgrade changes the tarball, so refresh the lock with `uv lock --upgrade-package dataiku-internal-client`. It's dev-only: inside DSS the runtime provides `dataiku`, and dev-group deps aren't shipped in the deployable wheel. Because there is no row-reading fallback, local dev **requires** `uv sync` (and DSS connectivity) — a stale checkout that skipped it will `ImportError` on `dataiku` rather than silently degrading. That's a deliberate trade for one simple code path.

**When to revisit:** when the blueprint must target **multiple instances**, derive the URL from the configured instance (`~/.dataiku/config.json` / `DKU_INSTANCE`) instead of hardcoding it; or, if the team standardizes on locally-installed kits, point at the kit instead.

---

## Tech notes

- **Python ≥3.11** — recommended for the code env. The backend uses `from __future__ import annotations` as a 3.9 compatibility shim, but type errors can still surface on very old envs.
- **Design tokens / UI** — the app owns its look: tokens in `frontend/src/styles/tokens.css`, local `Ea*` components in `frontend/src/components/ui/` (built on `reka-ui`). There is no external component-library dependency. To re-theme, edit the token values in one place.
- **Settings storage key** — `<prefix>_app_settings` in the project's *standard* variables namespace. Two webapps in the same project with different `APP_PREFIX` values won't collide.
- **No writable local filesystem in DSS** — the plugin install directory is read-only. Use **Managed Folders** for user-uploaded files and **project variables** for configuration.
- **WebSockets** — DSS's WSGI layer doesn't support WebSocket upgrades. If you need push updates, use Server-Sent Events (SSE) instead (FastAPI's `sse-starlette` package, already in `pyproject.toml`).
