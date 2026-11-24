# Task Manager API

A Django REST Framework (DRF) backend for managing tasks with natural-language creation, subtasks, automatic breakdown, list filtering, and request idempotency.

**Base URL (development):** `http://127.0.0.1:8000`  
**API prefix:** `/api/`

---

## 1. Project overview

The Task Manager API exposes a `Task` resource and several workflow endpoints:

| Capability | Description |
|------------|-------------|
| **CRUD** | Create, list, retrieve, update, and delete tasks. |
| **Natural-language creation** | `POST /api/tasks/from-text/` accepts free-form text and derives title, description, and optional `due_date` using a **rule-based parser** in `tasks/ai.py` (not an external LLM). |
| **Subtasks** | `GET`/`POST /api/tasks/{id}/subtasks/` attach child tasks to a **root** parent only. The API enforces a maximum hierarchy depth of one across task creation, updates, subtasks, and breakdown. |
| **Breakdown** | `POST /api/tasks/{id}/breakdown/` splits the parent’s description on commas and the word `" and "`, then creates multiple subtasks in one transaction after validating all generated rows. |
| **List features** | Filter by `completed` and `priority`, full-text search on `title`/`description`, ordering, and page-number pagination (10 items per page). |
| **Priority shortcut** | `GET /api/tasks/priority/{level}/` returns all tasks with a given priority (unpaginated). |
| **Idempotency** | Selected `POST` endpoints accept an `Idempotency-Key` header; successful responses are cached **in memory** for replay. |

---

## 2. Technology stack

| Component | Version (from `requirements.txt`) |
|-----------|-------------------------------------|
| Python | **Not pinned** in `requirements.txt`; development has used **3.14.7** in a local `venv` (not documented as the only supported version) |
| Django | 6.1.3 |
| Django REST Framework | 3.18.3 |
| django-filter | 26.2 |
| PostgreSQL driver | psycopg2-binary 2.9.13 |
| Database | PostgreSQL 16 (via `docker-compose.yaml`) |

Other declared dependencies: `asgiref`, `sqlparse`.

---

## 3. Prerequisites

- **Python 3** — version not specified in the repo; use a release compatible with Django 6.1.3 and your `pip install` outcome. A bundled `venv` in this workspace has used **3.14.7**; other versions are **not** verified in repository documentation or CI.
- **PostgreSQL** (local install or Docker)
- **Docker & Docker Compose** (optional, for the provided Postgres service)
- **pip** and **venv**
- **Postman** (optional, for the collection in `tests/`)

---

## 4. Installation and setup

### 4.1 Clone and enter the project

```bash
cd task_manager
```

*(Replace with your actual clone path.)*

### 4.2 Virtual environment

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 4.3 Install dependencies

```bash
pip install -r requirements.txt
```

### 4.4 Start PostgreSQL (Docker option)

From the project root:

```bash
docker compose up -d
```

This starts Postgres 16 with:

- Database: `taskmanager`
- User / password: `admin` / `admin`
- Host port: **15432** → container `5432`

### 4.5 Database configuration

Connection settings are defined in `config/settings.py` (not environment variables):

| Setting | Value |
|---------|--------|
| `ENGINE` | `django.db.backends.postgresql` |
| `NAME` | `taskmanager` |
| `USER` | `admin` |
| `PASSWORD` | `admin` |
| `HOST` | `127.0.0.1` |
| `PORT` | `15432` |

Adjust these if your Postgres instance differs.

### 4.6 Migrations and runserver

```bash
python manage.py migrate
python manage.py runserver
```

The API is available at `http://127.0.0.1:8000/api/`.

---

## 5. Environment configuration

This project **does not** load settings from `.env` or `os.environ` for database, secrets, or AI keys.

| Variable | Status |
|----------|--------|
| `DJANGO_SETTINGS_MODULE` | Set automatically by `manage.py` / `wsgi.py` to `config.settings` |
| `LLM_API_KEY` | **Not used** — parsing and breakdown are implemented in `tasks/ai.py` without external API calls |

**Security note:** `SECRET_KEY` and database credentials are **hard-coded** in `config/settings.py` for development. Do not deploy as-is; rotate secrets and use environment-backed settings in production.

---

## 6. Data model

### `Task` (`tasks/models.py`)

| Field | Type | Default / constraints |
|-------|------|------------------------|
| `id` | BigAutoField | Primary key (read-only in API) |
| `title` | `CharField(max_length=255)` | Required |
| `description` | `TextField()` | Required at API layer (see validation) |
| `completed` | `BooleanField` | `default=False` |
| `due_date` | `DateField` | `null=True`, `blank=True` |
| `priority` | `CharField` | Choices: `low`, `medium`, `high`; **default:** `medium` |
| `parent` | `ForeignKey("self")` | `null=True`, `blank=True`, `on_delete=CASCADE`, `related_name="subtasks"` |
| `created_at` | `DateTimeField` | `auto_now_add=True` (read-only in API) |
| `updated_at` | `DateTimeField` | `auto_now=True` (read-only in API) |

### Parent–child relationships

- A task with `parent=null` is a **root** task.
- Subtasks point to their parent via `parent_id`.
- Deleting a parent **cascades** and deletes its subtasks.
- The API enforces a maximum hierarchy depth of one: root tasks may have subtasks, but subtasks cannot have their own subtasks.
- On `POST /api/tasks/` and `PUT`/`PATCH /api/tasks/{id}/`, a non-null `parent` must refer to a root task. Creating a grandchild by setting `parent` to an existing subtask returns **400** `VALIDATION_ERROR`, with `parent` identified in `error.details`.
- **`POST /api/tasks/{id}/subtasks/`** and **`POST /api/tasks/{id}/breakdown/`** return **400** `INVALID_PARENT` when the task in the URL is already a subtask.

---

## 7. API documentation

All routes below are registered under `path('api/', include('tasks.urls'))`.

Unless noted, requests should use `Content-Type: application/json`.

### 7.1 List tasks

| | |
|---|---|
| **Method / URL** | `GET /api/tasks/` |
| **Purpose** | Paginated list of **all** tasks (including subtasks). |
| **Query params** | See §7.10 |
| **Errors** | Successful list uses DRF pagination. Invalid query parameters (e.g. unsupported `ordering`) may return **DRF’s default error JSON**, not the custom envelope (§8). |
| **Success** | **200** — `{ "count", "next", "previous", "results": [ Task, ... ] }` |
| **Page size** | 10 (`tasks/pagination.py`) |

**Example response (truncated):**

```json
{
  "count": 25,
  "next": "http://127.0.0.1:8000/api/tasks/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "title": "Review pull requests",
      "description": "Review open PRs",
      "completed": false,
      "due_date": "2026-04-01",
      "priority": "medium",
      "parent": null,
      "created_at": "2026-11-24T10:00:00Z",
      "updated_at": "2026-11-24T10:00:00Z"
    }
  ]
}
```

---

### 7.2 Create task

| | |
|---|---|
| **Method / URL** | `POST /api/tasks/` |
| **Purpose** | Create a task. |
| **Idempotency** | Optional `Idempotency-Key` header (§10). |
| **Body** | JSON object with task fields (see examples). |
| **Success** | **201** — task object |
| **Validation error** | **400** — `VALIDATION_ERROR`; a non-null `parent` must refer to a root task, and the error detail identifies `parent` |

**Example request:**

```json
{
  "title": "Review pull requests",
  "description": "Review open PRs in the task manager repo",
  "completed": false,
  "priority": "high",
  "due_date": "2026-04-01"
}
```

---

### 7.3 Retrieve task

| | |
|---|---|
| **Method / URL** | `GET /api/tasks/{id}/` |
| **Success** | **200** — task object |
| **Not found** | **404** — `TASK_NOT_FOUND` |

---

### 7.4 Update task

| | |
|---|---|
| **Method / URL** | `PUT /api/tasks/{id}/` (full) or `PATCH /api/tasks/{id}/` (partial) |
| **Success** | **200** — updated task |
| **Validation error** | **400** — `VALIDATION_ERROR` |
| **Not found** | **404** — `TASK_NOT_FOUND` |

---

### 7.5 Delete task

| | |
|---|---|
| **Method / URL** | `DELETE /api/tasks/{id}/` |
| **Success** | **204** — empty body |
| **Not found** | **404** — `TASK_NOT_FOUND` |

---

### 7.6 Create task from natural language

| | |
|---|---|
| **Method / URL** | `POST /api/tasks/from-text/` |
| **Purpose** | Parse `text` and create a task. |
| **Idempotency** | Optional `Idempotency-Key` header. |
| **Body** | `{ "text": "<string>" }` |
| **Success** | **201** — task object |
| **Missing / empty / non-string `text`** | **400** — `VALIDATION_ERROR` (view check; e.g. issue `Text must not be empty`) |
| **`parse_task_text` raises or returns non-dict** | **502** — `PARSER_ERROR` |
| **Parser dict fails `TaskSerializer`** | **502** — `PARSER_VALIDATION_ERROR` |

**Example request:**

```json
{
  "text": "remind me to buy groceries tomorrow"
}
```

---

### 7.7 List / create subtasks

| | |
|---|---|
| **Method / URL** | `GET /api/tasks/{id}/subtasks/` |
| **Purpose** | List direct children of task `{id}`. |
| **Success** | **200** — JSON **array** of tasks (not paginated) |
| **Not found** | **404** — `TASK_NOT_FOUND` |

| | |
|---|---|
| **Method / URL** | `POST /api/tasks/{id}/subtasks/` |
| **Purpose** | Create one subtask under parent `{id}` (parent must be a root task). |
| **Body** | Same fields as create task (parent is set server-side). |
| **Success** | **201** — subtask with `parent` set |
| **Parent is a subtask** | **400** — `INVALID_PARENT` |
| **Validation error** | **400** — `VALIDATION_ERROR` |

---

### 7.8 Break down task

| | |
|---|---|
| **Method / URL** | `POST /api/tasks/{id}/breakdown/` |
| **Purpose** | Generate subtasks from parent's `description`. |
| **Idempotency** | Optional `Idempotency-Key` header. |
| **Body** | `{}` (request body is part of idempotency key; use consistent JSON). |
| **Success** | **201** — JSON **array** of created subtasks |
| **Subtask target** | **400** — `INVALID_PARENT` |
| **Empty / non-list parser output from `break_down_task`** | **400** — `BREAKDOWN_ERROR` (`No subtasks could be generated`) |
| **Generated rows fail `TaskSerializer`** | **502** — `BREAKDOWN_VALIDATION_ERROR` (nothing saved) |
| **Unhandled exception in breakdown handler** | **502** — `BREAKDOWN_ERROR` (`Task breakdown failed`) |

**Example parent description:** `"Buy ingredients, chop vegetables, and cook grains"` → multiple subtasks.

---

### 7.9 Tasks by priority (shortcut)

| | |
|---|---|
| **Method / URL** | `GET /api/tasks/priority/{level}/` |
| **`level`** | `low`, `medium`, or `high` |
| **Success** | **200** — JSON array of tasks |
| **Invalid level** | **400** — `INVALID_PRIORITY` |

---

### 7.10 Query parameters (list endpoint)

| Parameter | Behaviour (`TaskViewSet`) |
|-----------|----------------------------|
| `completed` | Exact filter (`true` / `false`) |
| `priority` | Exact filter: `low`, `medium`, `high` |
| `search` | Search `title` and `description` |
| `ordering` | Fields: `created_at`, `updated_at`, `due_date`, `priority`; prefix `-` for descending. Default: `-created_at` |
| `page` | Page number (DRF `PageNumberPagination`) |

**Example combined query:**

```http
GET /api/tasks/?completed=true&priority=high&search=rent&ordering=-created_at&page=1
```

---

### 7.11 Django admin

| | |
|---|---|
| **URL** | `GET /admin/` |
| **Notes** | `Task` is registered in `tasks/admin.py`; requires a Django superuser (`createsuperuser`). |

---

## 8. Validation and error handling

### Success task JSON

All writable fields from `TaskSerializer` (`fields = '__all__'`):

`id`, `title`, `description`, `completed`, `due_date`, `priority`, `parent`, `created_at`, `updated_at`

Read-only in API: `id`, `created_at`, `updated_at`.

### Serializer rules (`tasks/serializers.py`)

| Rule | Error |
|------|--------|
| Title empty or whitespace-only | `Title cannot contain only whitespace.` |
| Description empty or whitespace-only | `Description cannot be empty.` |
| Description length **> 500** | `Description cannot be more than 500 characters.` |
| Invalid `priority` | DRF choice validation |
| Invalid `due_date` (e.g. `2026-02-30`) | DRF date validation |
| Invalid `completed` type | DRF boolean validation |
| `parent` refers to a subtask, or a task with subtasks is made a subtask | Parent validation (`parent` detail) |

### Custom error envelope (`tasks/utils.py` → `error_response`)

Many **task endpoints** return errors in this shape (used explicitly in `tasks/views.py`):

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Validation failed",
    "details": [
      { "field": "description", "issue": "Description cannot be more than 500 characters." }
    ]
  }
}
```

`details` entries are built from serializer errors via `serializer_errors_to_details` (field names plus issue strings).

### Where the custom envelope applies

| Uses custom `{ "error": { code, message, details } }` | Typical framework / DRF responses (shape may differ) |
|------------------------------------------------------|------------------------------------------------------|
| `POST /api/tasks/` validation; `PUT`/`PATCH` validation | `GET /api/tasks/` list with bad pagination/ordering (not overridden in views) |
| `GET`/`PUT`/`PATCH`/`DELETE` /api/tasks/{id}/` not found | Malformed JSON body (parser runs before the view) |
| `POST /api/tasks/from-text/` validation and parser paths | **405** method not allowed (router default) |
| `GET`/`POST` …/subtasks/`, `POST` …/breakdown/`, `GET` …/priority/ | Unhandled server errors (**500**) — Django/DRF default |
| Idempotency **422** `IDEMPOTENCY_KEY_REUSED` | |

Treat any response **without** a top-level `error.code` as framework-generated unless you confirm otherwise for that route.

### HTTP status and `error.code` reference (custom envelope)

| HTTP | `code` | When (implemented in `tasks/views.py`) |
|------|--------|----------------------------------------|
| 400 | `VALIDATION_ERROR` | Serializer or explicit input validation on create/update/subtasks; empty `text` on from-text |
| 400 | `INVALID_PARENT` | Subtasks or breakdown when target task is already a subtask |
| 400 | `INVALID_PRIORITY` | Invalid `level` on `/api/tasks/priority/{level}/` |
| 400 | `BREAKDOWN_ERROR` | `break_down_task` yields empty or non-list result (before save) |
| 404 | `TASK_NOT_FOUND` | `get_task_or_404` on detail routes and actions that use it |
| 422 | `IDEMPOTENCY_KEY_REUSED` | Same idempotency key, different path or body after a stored success |
| 502 | `PARSER_ERROR` | Exception while parsing from-text (including non-dict return) |
| 502 | `PARSER_VALIDATION_ERROR` | Parsed dict fails `TaskSerializer` on from-text |
| 502 | `BREAKDOWN_ERROR` | Uncaught exception in `breakdown` after subtask generation started |
| 502 | `BREAKDOWN_VALIDATION_ERROR` | Generated subtask dicts fail validation (no DB rows created) |

**Example — description too long (custom envelope):**

```http
POST /api/tasks/
```

```json
{
  "title": "Long text",
  "description": "<501 characters>"
}
```

→ **400**, `VALIDATION_ERROR`, detail on `description`.

---

## 9. Natural-language parsing

Implementation: **`parse_task_text(text, today)`** in `tasks/ai.py` (rule-based, **no LLM**).

### Behaviour

1. Lowercases input for keyword matching.
2. **Due date hints** (implemented as separate `if` / `elif` branches in `parse_task_text`; a later branch can override an earlier date):
   - `"tomorrow"` → `today + 1 day`
   - `"next week"` → `today + 7 days` (elif after tomorrow)
   - `"every month"` → first day of **next** calendar month; sets internal `recurrence = "monthly"`
   - `"1st"` (elif, when `"every month"` did not match) → first day of next month
3. **Title** — strips phrases such as `remind me to`, `tomorrow`, `next week`, `every month`, `on the 1st`, etc., then capitalizes. If the result is empty, uses `text.strip().capitalize()`.
4. **Description** — full original `text`.
5. Returns a **dict**:

```python
{
    "title": "...",
    "description": text,
    "due_date": <date or None>,
    "recurrence": <"monthly" or None>,  # parser only
}
```

### `recurrence` and persistence

`recurrence` is **not** a database field. `TaskSerializer` exposes only model fields, so `recurrence` is **not stored** and does not appear in API responses after save.

### Replacing with an LLM (future)

`from_text` in `tasks/views.py` calls `parse_task_text(text, date.today())` and then validates with `TaskSerializer`. A drop-in replacement could call an external model and return the same dict shape; keep serializer validation so API contracts stay stable.

Breakdown uses **`break_down_task(task)`** in the same module (comma / `" and "` splitting), also replaceable independently.

---

## 10. Idempotency

Header: **`Idempotency-Key`**

### Supported endpoints

- `POST /api/tasks/`
- `POST /api/tasks/from-text/`
- `POST /api/tasks/{id}/breakdown/`

`PATCH`, `PUT`, `DELETE`, and subtask `POST` do **not** implement idempotency.

### Matching logic (`check_idempotency` in `tasks/views.py`)

Stored key scope:

```text
{ "path": <request.path>, "data": <deep copy of request.data> }
```

| Scenario | Result |
|----------|--------|
| Same key, **same** path + body after a **successful** response | Replay stored **status** and **body** |
| Same key, **different** path or body after a stored success | **422** `IDEMPOTENCY_KEY_REUSED` |
| Failed request (e.g. **400**) | **Not** stored; retry with same key may succeed |

### Storage limitations

Records live in the module-level dict `idempotency_store` in `tasks/views.py`:

- **In-memory only** — cleared on process restart
- **Not shared** across multiple workers or hosts
- **Not persisted** to the database

For production, replace with durable storage (Redis, DB, etc.) — **not implemented** today.

---

## 11. Testing

### Django unit tests

```bash
python manage.py test tasks
```

Current coverage is primarily **`TaskSerializer`** validation in `tasks/tests.py` (no full API integration suite in-repo).

### Postman collection

1. Import `tests/task_manager_postman_collection.json`.
2. Ensure `baseUrl` is `http://127.0.0.1:8000`.
3. Run folders **00 → 09** in order (see `tests/STEP8_TESTING_PLAN.md`).

Idempotency keys are generated once in the first **00 Setup** request. Restart the Django server between full collection runs if you need a clean in-memory idempotency store.

### Mock-only scenarios

Parser/breakdown failure paths (`PARSER_ERROR`, invalid generated subtasks, etc.) require **`unittest.mock`** against `parse_task_text` / `break_down_task` — documented in Postman folder **10 Mock-only**; not exercisable via HTTP alone.

---

## 12. Project structure

```text
task_manager/
├── config/                 # Django project settings and root URLs
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── tasks/                  # Task app (models, API, AI helpers)
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   ├── ai.py
│   ├── utils.py
│   ├── pagination.py
│   ├── admin.py
│   ├── tests.py
│   └── migrations/
├── tests/                  # Postman collection and testing plan
│   ├── task_manager_postman_collection.json
│   └── STEP8_TESTING_PLAN.md
├── docker-compose.yaml     # PostgreSQL 16 service
├── manage.py
├── requirements.txt
└── README.md
```

*(A local `venv/` directory is typical but not part of application source.)*

---

## 13. Future improvements

Not implemented in the current codebase; possible next steps:

- **LLM-backed parsing** — replace or augment `parse_task_text` / `break_down_task` with an external API (would introduce env-based API keys).
- **Persistent idempotency** — Redis or database backing instead of `idempotency_store`.
- **Environment-based settings** — externalize `SECRET_KEY` and database credentials.
- **Authentication / authorization** — no auth on API endpoints today.

---

## Files inspected

| File | Purpose |
|------|---------|
| `requirements.txt` | Dependencies and versions |
| `docker-compose.yaml` | Postgres service |
| `manage.py` | Django entrypoint |
| `config/settings.py` | DB, apps, middleware |
| `config/urls.py` | `/api/` mount |
| `tasks/models.py` | `Task` schema |
| `tasks/serializers.py` | Validation rules |
| `tasks/views.py` | ViewSet, idempotency, actions |
| `tasks/urls.py` | DRF router |
| `tasks/ai.py` | `parse_task_text`, `break_down_task` |
| `tasks/utils.py` | Error envelope helpers |
| `tasks/pagination.py` | Page size 10 |
| `tasks/admin.py` | Admin registration |
| `tasks/tests.py` | Serializer tests |
| `tasks/migrations/` | Schema history |
| `tests/STEP8_TESTING_PLAN.md` | Postman execution notes |
| `tests/task_manager_postman_collection.json` | API test collection |

### Not verified / not present in repo

- **Supported Python versions** — not declared in `requirements.txt` or `pyproject.toml`; **3.14.7** appears in a local `venv` only. No CI or test matrix in the repo confirms other versions.
- **Exact DRF responses** for invalid list query parameters — list action is not customized; error bodies were not verified against a running server in this documentation pass.
- **`LLM_API_KEY`** — no references in application code; **not required**.
- **`.env` / environment-based configuration** — not implemented.
- **`REST_FRAMEWORK` global settings** — not defined in `config/settings.py`; DRF defaults apply except per-viewset configuration.
- **Authentication, throttling, CORS** — not configured on the API.
- **CI/CD or production deployment** — not documented in repo files.