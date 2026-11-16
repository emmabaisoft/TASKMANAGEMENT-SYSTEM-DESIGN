# TASKMANAGEMENT – system design

Reverse-engineered architecture and database design of the TASKMANAGEMENT backend, as draw.io diagrams.

- **Source:** project repo `TASKMANAGEMENT`, branch `main`, commit `d98fc033`. The project repo was treated as read-only.
- **Generated:** 2026-11-16.
- **Format:** every diagram is an uncompressed `.drawio` file. Open them in diagrams.net or the VS Code draw.io extension.
- **Not rendered:** no draw.io renderer was available where these were generated, so the files were checked structurally (see [Validation](#validation)) but not looked at on a canvas. Expect to tidy edge routing by hand, especially in the large ERDs.

## What the system is

A Django 5.2 / Django REST Framework monolith served by Daphne (ASGI), with Celery workers and beat on a Redis broker, PostgreSQL as the database, and a Next.js frontend that is mounted in a host platform as the `taskmgt` module. It is multi-tenant per institution. The backend has 12 Django apps; `performance` holds about half of the tables and routes.

## Diagrams

### Database

| File | Tabs | Shows |
|---|---|---|
| `database/erd-full.drawio` | Overview (keys only); Framework tables | All 242 application tables with PK and FK columns, grouped in coloured containers per domain. The second tab has the 16 Django and third-party tables plus the pgvector table. |
| `database/erd-users.drawio` | 1 | 20 tables, all columns |
| `database/erd-institution.drawio` | 1 | 16 tables |
| `database/erd-projects.drawio` | 1 | 19 tables |
| `database/erd-tasks.drawio` | 1 | 16 tables |
| `database/erd-performance.drawio` | 10 | 117 tables split by sub-area: Resources, KPI configuration, Assignments, Reports, Free reports, Attention, Attendance, PIP, Appraisal forms, Loyalty |
| `database/erd-approval.drawio` | 1 | 11 tables |
| `database/erd-calendar2.drawio` | 1 | 7 tables |
| `database/erd-communication.drawio` | 1 | 4 tables |
| `database/erd-reports.drawio` | 1 | 27 tables |
| `database/erd-settings.drawio` | 1 | 3 tables |
| `database/erd-audit.drawio` | 1 | 1 table |
| `database/erd-system.drawio` | 1 | 1 table |

Reading the ERDs:

- Each table lists every column with its PostgreSQL type, `NULL` / `NOT NULL`, and key markers (`PK`, `FK`, `UQ`, `IX`, `GFK`).
- Composite unique constraints, check constraints and declared indexes are the italic rows at the bottom of a table.
- Relationship lines use crow's-foot notation; the legend on every page explains the four combinations used.
- A dashed table is a reference stub for a table defined in another file or tab.
- `created_by_id` and `updated_by_id` are foreign keys to `users_customuser` on almost every table (422 of the 886 foreign keys). They are listed as FK columns but their lines are not drawn.
- Columns marked `⟨enum⟩` are Django `choices`; the values are listed in the "Enums" box on each page.

### Architecture

| File | Shows |
|---|---|
| `architecture/01-system-context.drawio` | C4 level 1: the system, its actors and external systems |
| `architecture/02-containers.drawio` | C4 level 2: frontend module, API application, Celery worker and beat, PostgreSQL, Redis, media storage, and the protocols between them |
| `architecture/03-components-backend.drawio` | C4 level 3: request pipeline, the 12 apps, cross-cutting components. Second tab: app-to-app import matrix |

### Flows

| File | Shows |
|---|---|
| `flows/seq-login-and-institution-selection.drawio` | Login, multi-institution selection, authenticated request, token refresh |
| `flows/seq-partner-system-provisioning.drawio` | Partner platform activates an institution, creates a user, and receives callbacks |
| `flows/seq-approval-workflow.drawio` | Maker-checker approval of a change, level by level |
| `flows/seq-performance-report-submission-and-review.drawio` | Assignment generation, report submission, entry review, finalisation |
| `flows/seq-scheduled-report-email.drawio` | Beat-driven report generation, PDF, e-mail delivery, cleanup |
| `flows/seq-notification-delivery.drawio` | Notification creation, partner callback, REST and SSE delivery |
| `flows/state-approval-status.drawio` | `approval_status` lifecycle shared by 32 approvable tables |
| `flows/state-approval-task.drawio` | `ApprovalTask.status` and `Approval.status` |
| `flows/state-performance-report.drawio` | `PerformanceReport.status` and `PerformanceReportEntry.status` |
| `flows/state-requested-report-instance.drawio` | `PerformanceRequestedReportInstance.status` |
| `flows/state-performance-improvement-plan.drawio` | `PerformanceImprovementPlan.status`, `PIPReview.status`, review assessment status |
| `flows/state-attention-record.drawio` | `PerformanceAttentionRecord.review_status` and `ManualPerformanceConcern.status` |

### API and security

| File | Shows |
|---|---|
| `api/api-overview.drawio` | Index tab with counts per app, then one tab per app: HTTP methods, path, authentication, permission codes, tables referenced, for 344 routes |
| `security/auth-rbac.drawio` | Three tabs: authentication flow, RBAC data model, permission evaluation |

### Not produced

- **Deployment diagram:** skipped as agreed. The repo has two Dockerfiles and no compose, Kubernetes, CI/CD or IaC configuration.
- **State diagrams for institution onboarding and work-achievement submissions:** planned in discovery, dropped because no code path assigning most of their status values was found. They are listed under open questions instead.
- **Project and task status state diagrams:** statuses are rows in `ProjectTaskStatus`, `StandaloneTaskStatus` and related tables, so there is no fixed state machine to draw.

## Sources

| Diagram | Derived from (project repo, commit `d98fc033`) |
|---|---|
| ERDs | All 451 migration files under `backend/*/migrations/`, loaded into Django's in-memory migration state by `tools/extract_schema.py`. No database was contacted. The result is stored in `database/schema-snapshot.json`. Generic foreign keys come from the model classes. The pgvector table comes from `backend/setup_pgvector.sh`. |
| System context, containers | `backend/core/settings.py`, `core/asgi.py`, `core/celery.py`, `core/urls.py`, `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/package.json`, `frontend/module.json`, `backend/requirements.txt`, `backend/readME.md`, and the outbound call sites in `system/`, `users/views.py`, `calendar2/zoom_api.py`, `institution/models.py` |
| Components | `core/settings.py` (middleware, apps), `core/middleware.py`, each app's `urls.py` / `views.py` / `serializers.py` / `services.py` / `tasks.py`, `utilities/`, `approval/models.py`, `communication/notifications.py`. The import matrix is a static count of import statements. |
| Auth and RBAC | `users/authentication.py`, `system/authentication.py`, `system/utils.py`, `utilities/permissions.py`, `users/models.py`, `users/views.py`, `users/services.py`, `users/tasks.py`, `core/middleware.py` |
| API map | Django URL resolver walked by `tools/extract_api.py`; stored in `api/api-snapshot.json` |
| Login sequence | `users/views.py` (`LoginView`, `SelectInstitutionView`, `CustomTokenRefreshView`), `users/authentication.py`, `users/models.py` (`get_token`) |
| Partner sequence | `institution/views.py` (`TaskMgtActivationView`), `users/views.py` (`ExternalSystemsUserCreateView`), `users/tasks.py`, `system/tasks.py` |
| Approval sequence and states | `approval/models.py`, `approval/urls.py`, `performance/views.py` (`KpiDetailView` as the example) |
| Performance report sequence and states | `performance/services.py`, `performance/utils.py`, `performance/models.py`, `performance/tasks.py`, `performance/REPORT_LIFECYCLE.md` |
| Scheduled report sequence | `reports/tasks.py`, `core/celery.py` |
| Notification sequence | `communication/notifications.py`, `communication/views.py`, `system/tasks.py` |
| PIP and attention states | `performance/services.py` (`PIPService`, `PIPReviewService`, `PIPLifecycleService`, `PerformanceAttentionEvaluationService`), `performance/models.py`, `performance/views.py` |

## Validation

`python3 tools/validate.py` was run on the final files and reports no errors:

- All 30 files (58 tabs) are well-formed XML with the `mxfile > diagram > mxGraphModel > root` structure, cells `0` and `1`, unique cell ids, and valid edge endpoints.
- No two sibling shapes overlap.
- ERD cross-check against the schema snapshot: all 258 tables appear in `erd-full.drawio`; all 242 application tables appear in a per-domain file with every one of their 3,273 columns; all 464 non-audit foreign keys have a line with the correct cardinality; nothing is drawn that the snapshot does not contain, apart from the pgvector table, which is marked "Inferred – verify".
- Migrations and models agree for every application table. The only difference is in a framework table: `auth_group_permissions.id` is `bigint` in the migration state and `integer` in the model.
- The project repo's `git status` is identical to how it was before work started. It had one uncommitted change beforehand (`backend/performance/services.py`, one added line), which was not touched.

## Assumptions

- Column types are the PostgreSQL types Django emits for each field. They were not read from a live database.
- Enum values are Django `choices`. They are enforced in application code only; the columns are plain `varchar`.
- "Tables referenced" in the API map means models named in the view class or in the serializers it names. It is a static reading.
- "Permission codes" in the API map come from `method_permissions` or from literal `can_…` strings in the view class. Checks inside serializers or services are not visible to the extractor.
- The frontend is drawn as one container. Its internals were not analysed.
- Real hostnames, e-mail addresses and keys found in settings and source files are not reproduced; diagrams use generic names.

## Inferred items (marked "Inferred – verify" in the diagrams)

| Where | Item |
|---|---|
| `erd-full.drawio`, Framework tab | The pgvector table `sql_knowledge1` is created by a shell script, not a migration. Whether it exists in a given environment is unknown. |
| `01-system-context.drawio` | Who scrapes `/metrics`. Whether Zoom is used: a token helper exists on `Institution`, but the meeting-creation call is commented out. |
| `02-containers.drawio` | That web and worker processes share one media volume, and how many instances of each run. |
| `auth-rbac.drawio` | How `StaffGroupRole` feeds `UserPermission` was not traced line by line. |
| `seq-partner-system-provisioning.drawio` | The full list of business events that trigger a partner callback. |
| `seq-notification-delivery.drawio` | Nothing writes the Redis list the SSE stream reads. |
| `state-approval-status.drawio` | `Task` and `StandaloneTask` assign `deleted` and `rejected`, which are not declared choices. |
| `state-performance-report.drawio` | Whether a report rejected in review can be resubmitted. |
| `state-requested-report-instance.drawio` | `cancelled` has no assignment; a waived-to-pending reversal may exist; whether a missed instance can still be submitted late. |
| `state-attention-record.drawio` | `under_review` and `closed` have no caller; `ManualPerformanceConcern.resolved` has no assignment. |

## Open questions

1. **SSE notifications:** `GET /api/communication/notifications/sse/` reads the Redis list `notifications:{user_id}`, but the only `RPUSH` to it is commented out. Is the stream still meant to deliver notifications, or is the REST list the real channel?
2. **Routes with no permission check in the view:** 166 of 344 routes are authenticated but show no permission code in the view class, including all 19 approval routes and all 9 communication routes. Are these checked in serializers or services, or are they open to any authenticated member of the institution?
3. **`/api/user/taskmgt-user-state-data/`** is declared `AllowAny` but reads `request.user`. Is that intended?
4. **Google sign-in:** `GoogleAuthCallbackView` reads `settings.GOOGLE_AUTH_REDIRECT_URL`, which `core/settings.py` does not define. Is Google sign-in in use?
5. **Unused integrations:** Groq, Africa's Talking, Microsoft Teams/MSAL and Zoom are installed or configured but have no live call path. Planned, or dead?
6. **Cache:** there is no `CACHES` setting, so the cache is per process. The resource lookup in `ResourceMiddleware` and the partner-system helpers rely on it. Is a shared cache configured outside the repo?
7. **Celery beat:** nine schedules are defined in code, and the scheduler is `django-celery-beat`'s database scheduler. `send_overdue_approval_reminders` exists but is not in the code schedule. Are further schedules held only in the database?
8. **`Institution.approval_status`** has values `pending / approved / rejected / under_review` with no assignments in code. Who moves an institution between them?
9. **Stale documentation:** `backend/readME.md` describes a different product and links to an external ERD that was not consulted. Should it be treated as obsolete?
10. **Deployment:** `frontend/Dockerfile` ends with `npm run dev`, and the backend image is Python 3.10 while `.python-version` says 3.12. What actually runs in production?

## Regenerating

The diagrams are produced by the scripts in `tools/`. The two extractors need the project's own Python environment; the generators need only Python 3.

```sh
PROJECT=../TASKMANAGEMENT/backend

# 1. Re-read the project (read-only: no database connection, no bytecode written)
PYTHONDONTWRITEBYTECODE=1 $PROJECT/.venv/bin/python tools/extract_schema.py $PROJECT database/schema-snapshot.json
PYTHONDONTWRITEBYTECODE=1 $PROJECT/.venv/bin/python tools/extract_api.py    $PROJECT api/api-snapshot.json

# 2. Regenerate the diagrams
python3 tools/gen_erd.py
python3 tools/gen_architecture.py
python3 tools/gen_flows.py
python3 tools/gen_api.py

# 3. Validate
python3 tools/validate.py
```

Run the commands from this repo, not from inside the project repo. The extractors import the project's settings, so `backend/.env` must be present.

What updates by itself and what does not:

- **ERDs and API map** are fully generated. After a schema or route change, rerun steps 1 to 3 and review `git diff` on the two snapshot JSON files to see what changed.
- **New `performance` model:** `gen_erd.py` stops with an error until the model is assigned to a sub-area in `PERF_AREAS`.
- **Architecture, security, sequence and state diagrams** are modelled by hand inside `gen_architecture.py` and `gen_flows.py`; only the layout is computed. When the code they describe changes, edit the content in those scripts and rerun them. The import matrix in `gen_architecture.py` (`IMPORTS`) is also a hand-copied count.
- **Manual edits in draw.io are overwritten** the next time a generator runs. Either change the generator, or stop regenerating that file.
- Cell ids are stable (`tbl_<table>`, `col_<table>_<column>`, `fk_<table>_<column>`), so regenerated files diff cleanly.
- The VS Code draw.io extension rewrites a file in its own indented format when it saves it. That produces a large diff with no real change; rerunning the generator restores the original formatting.
