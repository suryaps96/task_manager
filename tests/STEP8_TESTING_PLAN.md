# Step 8 — Testing Plan (Task Manager API)

Base URL: `http://127.0.0.1:8000`  
Postman collection: `tests/task_manager_postman_collection.json`

## Execution order

1. Start server: `python manage.py runserver`
2. Import the Postman collection
3. Run folders **00 → 09** in order (numeric folder names)
4. Optional: `python manage.py test tasks` (serializer unit tests)

### Idempotency keys (once per collection run)

The **first request** in folder **00 Setup** (`Create parent task for subtasks`) runs a **prerequest** script that generates stable UUID-based keys and saves them with `pm.collectionVariables.set()`:

- `idempotencyKeyCreate` → `idem-create-<uuid>`
- `idempotencyKeyFromText` → `idem-text-<uuid>`
- `idempotencyKeyBreakdown` → `idem-break-<uuid>`

Generation uses `pm.variables.replaceIn('{{$randomUUID}}')` and is guarded by `idempotencyKeysInitialized` so re-running only that setup request does not rotate keys mid-run.

Folder **06** replay tests compare **parsed JSON** (`JSON.stringify` on first response, `pm.expect(replay).to.eql(JSON.parse(saved))`) and assert the **same task `id`** (or the same subtask `id` list for breakdown).

To start fresh idempotency state on the server **and** new keys, restart the Django process (in-memory idempotency store) and clear collection variables or re-import the collection.

### Collection variables (set by setup requests)

| Variable | Set by | Used for |
|----------|--------|----------|
| `parentTaskId` | 00 — Create parent task for subtasks | CRUD retrieve/update, folder 04 subtasks |
| `breakdownParentId` | 00 — meal prep task; **overwritten** in 05 setup with subtask id | 05 breakdown happy path, then invalid breakdown on subtask |
| `subtaskId` | 04 — POST Create subtask (`String(id)`) | 04 nested subtask tests |
| `breakdownIdempotencyParentId` | 06 — breakdown idempotency setup | 06 breakdown idempotency trio |
| `idempotencyKeyCreate`, `idempotencyKeyFromText`, `idempotencyKeyBreakdown` | **00 Setup** (first request prerequest, once per run) | folder 06 |
| `idempotencyKeyRetry` | 06 — fail-then-retry prerequest (once) | corrected retry pair |
| `unknownTaskId` | `999999999` (fixed) | 404 tests |

Collection **pre-request** script defines `assertCustomErrorFn` for full error envelope checks (`code`, `message`, `details[].field`, `details[].issue`).

---

## Postman folder map

| Folder | Coverage |
|--------|----------|
| **00 Setup** | **Generate idempotency keys**; parent task; meal-prep breakdown parent; combined-filter rent task; **12 bulk pagination seeds** |
| **01 Task CRUD** | List (paginated shape), create, retrieve, PATCH, PUT, DELETE |
| **02 Validation & 404** | Validation errors + **PUT unknown id** + GET/PATCH/DELETE 404 with envelope |
| **03 From-text** | NLP create + empty text validation |
| **04 Subtasks** | List/create; **subtaskId wiring**; INVALID_PARENT; reject **POST /api/tasks/ with parent=subtask**; unknown parent 404 |
| **05 Breakdown** | Happy path; empty segments; **setup parent+subtask**; breakdown on subtask via `{{breakdownParentId}}` |
| **06 Idempotency** | Create + from-text; **breakdown** replay (no extra subtasks) + 422 on different body |
| **07 Filter/Search/Order/Page** | Individual queries; **page 1 & 2**; **combined** `?completed=true&priority=high&search=rent&ordering=-created_at&page=1` |
| **08 Priority** | low/medium/high + invalid `urgent` |
| **09 Cascade** | DELETE parent removes children |
| **10 Mock-only** | Parser/breakdown mocks — pytest only |

---

## Part 1 — Test checklist (aligned with collection)

### Task CRUD (folder 01)

- **GET** `/api/tasks/` → **200**, keys `count`, `next`, `previous`, `results`
- **POST** `/api/tasks/` → **201** (full + minimal)
- **GET** `/api/tasks/{id}/` → **200**
- **PATCH** / **PUT** → **200**
- **DELETE** → **204**

### Validation & not found (folder 02)

- Empty/whitespace title, empty description, description > 500, `due_date` `2026-02-30`, invalid priority, non-boolean `completed` → **400** `VALIDATION_ERROR`
- **GET/PATCH/PUT/DELETE** `/api/tasks/999999999/` → **404** `TASK_NOT_FOUND` (full envelope)

### From-text (folder 03)

- **POST** `/api/tasks/from-text/` → **201** or **400** on empty/whitespace/missing `text`

### Subtasks (folder 04)

- **GET/POST** `/api/tasks/{parent}/subtasks/` → **200** / **201**
- **POST** subtasks on subtask id → **400** `INVALID_PARENT`
- **POST** `/api/tasks/` with `"parent": <subtaskId>` → **400** `VALIDATION_ERROR`; `error.details` identifies `parent`

### Breakdown (folder 05)

- **POST** `/api/tasks/{parent}/breakdown/` → **201** array (happy path)
- Non-splittable description → **400** `BREAKDOWN_ERROR`
- **POST** breakdown when `breakdownParentId` is a subtask → **400** `INVALID_PARENT`

### Idempotency (folder 06)

- **POST** `/api/tasks/`, `/api/tasks/from-text/`, `/api/tasks/{id}/breakdown/` with `Idempotency-Key`
- Same key + same body after success → replay (create/from-text/breakdown)
- Breakdown replay: **GET subtasks count unchanged**
- Same key + different body → **422** `IDEMPOTENCY_KEY_REUSED`
- Failed create then fix with same key → second succeeds (**400** not stored)

### List queries (folder 07)

- `completed`, `priority`, `search`, `ordering`, `page=1`, **`page=2`** (needs `count > 10` from 00 bulk seed)
- Combined: `/api/tasks/?completed=true&priority=high&search=rent&ordering=-created_at&page=1`

### Priority (folder 08)

- **GET** `/api/tasks/priority/{low|medium|high}/` → **200** array
- **GET** `/api/tasks/priority/urgent/` → **400** `INVALID_PRIORITY`

---

## Part 2 — Edge cases

| Case | Postman folder | Automated? |
|------|----------------|------------|
| All validation rows in Part 1 | 02 | Yes |
| 404 envelope on GET/PATCH/PUT/DELETE | 02 | Yes |
| Grandchild via POST `/api/tasks/` | 04 | Yes (expects **400** `VALIDATION_ERROR`; detail field `parent`) |
| Breakdown idempotency / no duplicate subtasks | 06 | Yes |
| Parser/breakdown mock failures | 10 | No — pytest + `unittest.mock` |

---

## Part 3 — Expected response shapes

**Task (success):** `id`, `title`, `description`, `completed`, `due_date`, `priority`, `parent`, `created_at`, `updated_at`

**List (success):** `count`, `next`, `previous`, `results`

**Error:**

```json
{
  "error": {
    "code": "STRING",
    "message": "STRING",
    "details": [{ "field": "string", "issue": "string" }]
  }
}
```

---

## Part 4 — Debugging breakpoints

See original plan in repository history; locations unchanged in `tasks/ai.py` (`parse_task_text`, `break_down_task`) and `tasks/views.py` (`from_text`, `breakdown`, `check_idempotency`).

---

## Part 5 — Remaining gaps (not in Postman)

- Malformed JSON body / missing `Content-Type`
- Invalid `ordering` field
- `from-text` with non-string `text` (e.g. number)
- Second breakdown **without** idempotency key (duplicate subtasks)
- Idempotency store cleared on server restart
- Mock-only parser/breakdown failure paths (folder 10)

---

## Known collection behaviors

- **Folder 05** runs happy-path breakdown before overwriting `breakdownParentId` with a subtask id for the invalid-breakdown test.
- **Folder 04** must run **POST Create subtask** before requests that use `{{subtaskId}}` (prerequest throws if empty).
- **Page 2** test skips gracefully if `count ≤ 10` (re-run **00 Setup** bulk seed).