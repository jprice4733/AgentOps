# Agent Instructions

A Vue 3 + FastAPI starter for building on-brand Dataiku DSS webapps. The UI is self-contained:
small local `Ea*` primitives (`frontend/src/components/ui/`) styled by vendored Dataiku design
tokens (`frontend/src/styles/tokens.css`) — no external component-library dependency. **Read
`README.md` first** — it covers architecture, run modes, deploy, and the load-bearing
non-obvious bits. This file is the *operating rules*; the README is the *reference*.

**First action on a fresh copy** (app not yet initialized): `app.env` ships with six
identity/target values **empty** — `LIB_NS`, `APP_PREFIX`, `VITE_APP_NAME`, `ENV_NAME`,
`DKU_INSTANCE`, `PROJECT_KEY`. **`make dev` will block (exit non-zero, listing the
missing keys) until all six are set**, so fill them in *before* running it. That's the
whole setup — no code edits.

**Do not guess these values and do not invent them. Discover the real options, then ask
the user to confirm each one** (use AskUserQuestion). The flow:
1. **App name** — ask the user. Derive `LIB_NS` (lower_snake_case), `APP_PREFIX`
   (UPPER_SNAKE), and `VITE_APP_NAME` (display name) from their answer; show the derived
   values and let them adjust.
2. **`DKU_INSTANCE`** — list the configured instances with `dku auth list -o json` (the dku
   CLI's auth profiles; the active one has `"active": true`, and `dku whoami` confirms it) and
   ask which to target. Use the profile `name` as the `DKU_INSTANCE` value.
3. **`PROJECT_KEY`** — run `dku project list` against that instance, present the existing
   projects, and ask which one to deploy to (or whether to create a new key).
4. **`ENV_NAME`** — propose `<lib_ns>-env` (deploy.sh auto-creates it on first deploy)
   and let the user override.

Only after the user has confirmed the values, write them into `app.env` and start the app:
```bash
make dev       # installs deps if needed, starts FastAPI :5000 + Vite :5173
```
To rename later, just edit `app.env` and restart `make dev`.

---

## Commands

**Dev loop:**
```bash
make dev      # install deps (once) + start FastAPI :5000 + Vite :5173
make stop     # kill both servers
make status   # see what's running
make logs     # tail .run/logs/
```

**Frontend (from `frontend/`):**
```bash
npm run typecheck   # vue-tsc — run this before declaring frontend work done
npm run build       # production bundle → frontend/dist/
```

**Backend:** Python deps managed by `uv`; runs via `make dev` (no separate command needed).

**Deploy to DSS** (fill in `app.env` first — needs `PROJECT_KEY`; `WEBAPP_ID` is auto-created if empty):
```bash
make deploy   # npm run build → upload to DSS library → restart webapp → confirm running
```
`make deploy` is **self-diagnosing**: after the restart it polls `dku webapp status` until the
backend is running, and if it doesn't come up it exits non-zero and prints the recent backend
logs inline.  Re-fetch logs at any time with:
```bash
dku webapp logs $WEBAPP_ID -P $PROJECT_KEY
```

No lint or test runner ships by default — this is intentional. If the user adds them, keep
them light.

---

## Building blocks (optional features)

Five optional blocks ship in the template. All five are **on by default** as a showcase — set any you don't need to `0` in `app.env` (one line per flag) and restart `make dev`.

The three **self-contained** blocks (Wizard, Charts, Flow) need no DSS or LLM and render immediately. The two **DSS-dependent** blocks (Documents, Chatbot) show a friendly "needs configuration" empty state until a Managed Folder / LLM is wired up.

### Enable/disable
```bash
# In app.env — one line per flag gates the block. Most gate both a backend route
# and the frontend sidebar item; the frontend reads ENABLE_* at build time (Vite
# envPrefix). NB: CHARTS is frontend-only (mock data, no backend route).
ENABLE_WIZARD=1       # /api/wizard/submit + sidebar (no DSS, no persistence)
ENABLE_CHARTS=1       # sidebar + charts view only — frontend mock data, no backend route
ENABLE_FLOW=1         # /api/flow/sample + sidebar (no DSS)
ENABLE_DOCUMENTS=1    # /api/documents + managed-folder + SQLite + sidebar
ENABLE_CHATBOT=1      # /api/chat + agent loop + permission broker + sidebar
ENABLE_DESCRIBE=1     # sub-option of DOCUMENTS: LLM auto-describe (backend-only flag)
```

### File locations
- **Wizard:** `backend/routes/wizard.py`; `frontend/src/views/wizard/` (`WizardFlowView.vue` shell + `WizardStepBasics.vue`, `WizardStepDetails.vue`, `WizardStepReview.vue`), `frontend/src/stores/wizard.ts`, `frontend/src/types/wizard.ts`. Each step is a child route tagged `meta.menuLevel: 'flow'` — that tag is what makes the sidebar render the vertical stepper.
- **Charts (frontend-only — no backend route; uses mock data):** `frontend/src/views/ChartsView.vue`, `frontend/src/components/dashboard/*.vue` (echarts), `frontend/src/data/mock/`. Route registered in `frontend/src/router/features.ts` under `ENABLE_CHARTS`.
- **Flow:** `backend/routes/flow.py`; `frontend/src/views/FlowView.vue`, `frontend/src/stores/flow.ts`, `frontend/src/types/flow.ts`.
- **Documents:** `backend/routes/documents.py`, `backend/services/documents_service.py`, `backend/services/document_describer.py` (DESCRIBE only); `frontend/src/views/DocumentsView.vue`, `frontend/src/stores/documents.ts`, `frontend/src/types/documents.ts`.
- **Chatbot:** `backend/routes/chat.py`, `backend/services/chat_agent.py`, `backend/services/permission_broker.py`, `backend/services/memory_state.py`, `backend/tools/registry.py`; `frontend/src/views/AssistantView.vue`, `frontend/src/components/chat/`, `frontend/src/stores/chat.ts`, `frontend/src/types/chat.ts`.
- **Agents (card-grid blueprint, always on — no ENABLE_* flag):** `backend/routes/agents.py`; `frontend/src/views/AgentsView.vue`, `frontend/src/components/agents/AgentCard.vue`, `frontend/src/stores/agents.ts`, `frontend/src/types/agents.ts`. Lives in the sidebar's Administration section, whose visibility is a runtime toggle: `frontend/src/stores/admin.ts` (localStorage, default ON) + `frontend/src/views/AdminView.vue` (footer Admin tab).
- **Shared persistence:** `backend/services/db.py`.

**Bundle weight caveat:** echarts and @vue-flow/core are statically bundled (the single-bundle constraint means they ship even when their block is disabled). To fully reclaim the weight, also run `npm remove echarts vue-echarts @vue-flow/core` in `frontend/`.

### Core rules for working with blocks

1. **A disabled block must be zero-cost.** No SQLite file created, no heavy deps loaded, no sidebar item shown. Maintain this by keeping all heavy imports (langchain-core, pymupdf, DSS calls) **inside handlers and behind** `if config.ENABLE_*` guards — never at module top.

2. **SQLite is single-writer.** Do NOT run uvicorn with `--workers > 1`. Two concurrent writers corrupt the DB. DSS webapp backends are single-process by default, so this is safe as-is (see README "Architecture decisions" → SQLite decision for when to graduate).

3. **`state.db` lives in the workload-local folder.** The live file is at `get_workload_local_folder_path() / state.db` on the DSS instance disk (local dev: `<repo>/.run/state.db`). It persists across backend restarts as long as the webapp is not fully redeployed.

4. **Managed folder is auto-created by name.** `documents_service._resolve_folder_id()` looks up or creates a folder named `{PREFIX} Documents`. If it fails locally (no writable connection), create the folder manually and set `documents_folder_id` in Settings.

5. **One flag per feature.** `ENABLE_DOCUMENTS=1` in `app.env` activates both the backend route and the frontend sidebar item. The frontend reads `ENABLE_*` directly at build time via Vite's `envPrefix`; no separate `VITE_ENABLE_*` line is needed.

6. **Tool-call approval ≠ authorization.** The chatbot permission broker gates what the agent may do, not who can use the app. DSS project permissions control access to the webapp. See README "Architecture decisions" → Tool-call approval for when to add real RBAC.

7. **Add a tool** by adding a `@tool`-decorated function to `backend/tools/registry.py` and updating `DEFAULT_TOOL_POLICY` in `backend/services/settings.py`.

---

## Keep it simple

These apps are built by data scientists to solve specific problems, **not** to build full applications. Default to the smallest change that works.

**Don't add** (unless the user explicitly asks): OpenSpec workflow, large component libraries, BDD/integration test suites, base64 doc pipelines, CI sync
pipelines, or multiple abstraction layers.

**Do:** one view + one route + (if needed) one backend route file + one service file.
Follow the existing shape:
- `frontend/src/views/ExampleView.vue` → `backend/routes/example.py` → `backend/services/`
- **Replace** the example view/route with real domain logic; don't accrete alongside it.

---

## UI / UX consistency

Apps built on this blueprint should look like Dataiku products. Follow these rules:

### Use the local `Ea*` primitives first
Reach for the local primitives in `frontend/src/components/ui/` (`import { EaSelect, EaButton,
EaEmpty, SettingsSwitchItem } from '@/components/ui'`) before writing custom markup. They are
small, token-styled wrappers — extend them or add a new one alongside (built on `reka-ui` for
anything interactive) rather than reaching for an external component library. For icons, use
`lucide-vue-next`.

See `frontend/src/views/ExampleView.vue` — it is the copy-this template for any new data view.

### Never hardcode colors
Use Tailwind utilities backed by the design tokens (defined in `frontend/src/styles/tokens.css`,
bridged to Tailwind in `frontend/src/style.css`):

| Purpose | Class |
|---|---|
| Page/card background | `bg-background`, `bg-card`, `bg-muted/30` |
| Default text | `text-foreground` |
| Secondary/caption text | `text-muted-foreground` |
| Error text | `text-destructive` |
| Brand accent | `bg-primary`, `text-primary-foreground` |
| Borders | `border`, `border-border` |
| Radius | `rounded-lg` (cards/tables), `rounded-md` (inputs) |

No raw hex values. No `style="color: #..."`. No Tailwind arbitrary color values like
`text-[#3b4e8c]`.

### Let the sidebar build itself
Never hand-build menu arrays. Add a page by adding a route with `meta`:
```typescript
// frontend/src/router/index.ts
{
  path: 'my-feature',
  name: 'myFeature',
  component: MyView,
  meta: { title: 'My Feature', icon: DatabaseIcon, menu: 'primary', order: 2 },
}
```
`menu: 'primary'` → main sidebar under the "Analysis" section label. `menu: 'secondary'` →
"Administration" section, shown only when the Admin toggle is on (`stores/admin.ts`,
localStorage, default ON). `menu: 'tertiary'` → footer (like Settings and Admin). The sidebar
(`frontend/src/components/layout/AppSidebar.vue`) and its menu composable
(`frontend/src/composables/useAppMenu.ts`) render it automatically from the router. Import icons
from `lucide-vue-next`.

**Optional blocks register conditionally.** A block's route lives in
`frontend/src/router/features.ts`, gated by its `ENABLE_*` flag — a disabled block is simply not
registered (so the sidebar omits it and its URL falls through to the home redirect). Always-on
core routes (dataset, agents, settings, admin) live in `frontend/src/router/index.ts`.

### Branding
The app's display name comes from `app.env` (`VITE_APP_NAME` → `APP_NAME` at build
time, also used for the browser tab title and FastAPI title). The sidebar icon is
`APP_ICON` in `frontend/src/config.ts`, which defaults to the fixed `Blocks` mark —
swap it for another `lucide-vue-next` component if the domain calls for it. Don't add
logo image files.

### Visual idiom — match the existing style
```vue
<template>
  <div class="h-full overflow-auto">
    <div class="max-w-5xl mx-auto p-8 space-y-6">
      <header>
        <h1 class="text-2xl font-semibold">Page Title</h1>
        <p class="text-sm text-muted-foreground mt-1">Short description.</p>
      </header>
      <!-- content: border rounded-lg for cards/tables, bg-muted/30 for header strips -->
    </div>
  </div>
</template>
```

### Always use `apiUrl()` for API calls
```typescript
import { apiUrl } from '@/utils/api'
const res = await fetch(apiUrl('/api/my-feature/items'))
```
Never `fetch('/api/...')` directly — the bare path breaks when the SPA runs inside the DSS
iframe. See README "The non-obvious bits, explained" for why.

### No binary assets in deployable code
DSS libraries are text-only. Use Lucide icon components for all iconography. If a raster
image is truly necessary, embed it base64 in a `.vue` component rather than adding a `.png`
file — but this is rarely needed for simple apps.

---

## Code style & conventions

**Python**
- `from __future__ import annotations` at the top of every module (Python 3.9 compat shim)
- Type hints on all function signatures
- `routes/` — parse HTTP params, return JSON, raise `HTTPException`. No direct DSS calls.
- `services/` — business logic and Dataiku API calls
- Access DSS via `get_project()` from `backend/dss_client.py` — it handles both local dev
  and in-DSS automatically; never branch on `DSS_MODE` yourself
- `snake_case` names; `"double quotes"` for strings

**Vue / TypeScript**
- Vue 3 Composition API, `<script setup lang="ts">` in every component
- `defineOptions({ name: 'MyView' })` at the top of views
- `PascalCase` for component files and imports
- `camelCase` for TS variables/functions; `single-quotes` for strings
- Shared reactive state → Pinia store in `frontend/src/stores/`

**Naming**
- `LIB_NS` — lowercase-underscore Python package name (`my_app`)
- `APP_PREFIX` — UPPER_SNAKE (`MY_APP`)
- These must stay in sync; edit both in `app.env` to rename

---

## Working with Dataiku projects

Two tools, two moments. Use the **`dku` CLI** at the terminal to *discover* what's in
the target project while you develop; use the **Dataiku Python API** inside the backend
to *access* it at runtime. The CLI is for you; the Python API is for the app.

### `dku` CLI — discover before you code (dev-time)

The backend talks to one DSS project — `PROJECT_KEY` in `app.env`. Before writing a
route against it, inspect it so you code against real dataset names, schemas, and LLM ids
instead of guessing. `dku` uses the same local credentials as the backend (`dku auth`,
stored in `~/.dataiku/config.json`). `dku` must be installed globally and on PATH
(authenticate once with `dku auth`); it is not a project dependency.

```bash
dku whoami                                          # confirm which instance/profile you're on
dku project inspect $PROJECT_KEY -o json            # datasets, recipes, variables in one call
dku dataset list -P $PROJECT_KEY                    # available datasets
dku dataset schema my_dataset -P $PROJECT_KEY       # exact column names + types
dku dataset head my_dataset -P $PROJECT_KEY -n 5   # sample real values
dku llm list -P $PROJECT_KEY                        # LLM ids for /api/system/llms
```

Treat `dku` as **read-only discovery** for app development — don't reshape the target
project (build datasets, create recipes, mutate variables) as a side effect of building a
webapp. Two skills are available if you need more: **`dku-cli`** (every command + flags)
and **`dataiku`** (platform concepts). Reach for them for anything beyond the basics above.

### Dataiku Python API — access at runtime (in the backend)

Always go through `get_project()` from `backend/dss_client.py`. It returns a project handle
that works both locally (`dataikuapi`) and inside DSS (`dataiku`) — never build a client or
branch on the environment yourself.

```python
from ..dss_client import get_project

project = get_project()
project.list_datasets()                             # see routes/example.py
project.get_dataset(name).get_schema()
project.list_llms(purpose="GENERIC_COMPLETION")     # see routes/system.py
project.get_variables() / project.set_variables()   # persist settings
```

**Reading dataset rows** goes through one path: `get_dataiku().Dataset(name).get_dataframe(limit=n)`
(pandas) — the runtime `dataiku` in DSS, or the installed `dataiku-internal-client` against the
remote instance locally (a **required** dev dependency pinned to the instance; see README
"Architecture decisions"). `get_dataiku()` from `backend/dss_client.py` always returns the
configured module — **there is no `dataikuapi` row-reading fallback** (run `uv sync`);
`backend/routes/example.py` shows the pattern — copy it rather than reinventing it. `dataikuapi`
stays required for the control-plane (`get_project()`: `list_datasets`, schemas, LLMs, variables,
folders). **Environment detection is the `DSS_MODE` flag, not `import dataiku` success** — the
installed package makes `dataiku` importable locally, so import-success would misfire. For LLM
calls, prefer wiring through the DSS LLM Mesh over hardcoding provider SDKs or API keys.

---

## Don't remove

These pieces are load-bearing for DSS embedding. See README "The non-obvious bits, explained":

- `frontend/src/utils/api.ts` — `apiUrl()` — fixes API paths inside the DSS iframe
- `frontend/src/router/index.ts` — `baseUrl = window.location.pathname` — fixes Vue Router base
- `frontend/vite.config.ts` — `base: './'` — relative asset paths for sub-path serving
- `frontend/vite.config.ts` — single-bundle rollup output — code-splitting breaks in DSS
- `frontend/vite.config.ts` — `dedupe: ['vue', 'vue-router']` — prevents two Vue instances
- `frontend/src/styles/tokens.css` — the Dataiku design tokens; `frontend/src/style.css` bridges them to Tailwind. Removing them strips the visual identity.
- `frontend/src/vite-env.d.ts` — `/// <reference types="vite/client" />` — declares `import.meta.env` and `*.vue`/`*.css` module types (typecheck fails without it)
- `backend/dss_client.py` — `get_project()` — dual-mode connector (local + in-DSS)
- `dss_webapp/backend.py` — must set `os.environ["APP_PREFIX"]` before importing `configure()`

**Additional load-bearing pieces when blocks are enabled:**
- `dss_webapp/deploy.sh` lines forwarding `LIB_NS`/`ENABLE_*` — blocks would silently be off in DSS without them
- `backend/services/documents_service.py::_resolve_folder_id()` — auto-creates/looks up the managed folder; do not hardcode an id

---

## When done

1. `cd frontend && npm run typecheck` — passes with no errors
2. `make dev` — new view appears in the sidebar and loads without console errors
3. New API endpoints respond correctly via `apiUrl()` calls (Vite proxies to FastAPI locally)
4. `make deploy` — only when the user wants the app pushed to DSS
