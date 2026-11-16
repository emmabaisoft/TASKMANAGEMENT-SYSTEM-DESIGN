#!/usr/bin/env python3
"""Generate the C4 architecture diagrams and the auth / RBAC diagram.

    python3 tools/gen_architecture.py

These diagrams are hand-modelled from the code (see README for the source
files of every element); only the layout is programmatic.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from drawio import DOMAIN_COLOURS, Diagram, Page, role_style  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = json.load(open(os.path.join(ROOT, "database", "schema-snapshot.json")))
API = json.load(open(os.path.join(ROOT, "api", "api-snapshot.json")))
COMMIT = (SNAP["source"]["commit"] or "unknown")[:8]
SRC = f"Derived from the project repo at commit {COMMIT}"

EDGE = ("edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;fontSize=10;"
        "labelBackgroundColor=#ffffff;strokeColor=#444444;")

C4_LEGEND = [
    ("actor", "Person / actor"),
    ("system", "This system"),
    ("frontend", "Frontend"),
    ("container", "Backend service / component"),
    ("worker", "Background worker / scheduler"),
    ("datastore", "Data store"),
    ("queue", "Broker / cache"),
    ("external", "External system"),
    ("inferred", "Inferred – verify"),
]


def c4(p: Page, cid, name, kind, desc, x, y, w, h, role, parent="1", shape=""):
    label = f"<b>{name}</b><br><span style=\"font-size:10px\">[{kind}]</span>"
    if desc:
        label += f"<br><br><span style=\"font-size:11px\">{desc}</span>"
    style = (shape or "rounded=1;arcSize=8;") + "whiteSpace=wrap;html=1;spacing=8;" + role_style(role)
    return p.vertex(cid, label, style, x, y, w, h, parent=parent)


def link(p: Page, cid, src, tgt, label="", dashed=False, extra=""):
    style = EDGE + ("dashed=1;" if dashed else "") + extra
    return p.edge(cid, label, style, source=src, target=tgt)


def side(exit_side, entry_side):
    pts = {"l": (0, 0.5), "r": (1, 0.5), "t": (0.5, 0), "b": (0.5, 1)}
    ex, ey = pts[exit_side]
    nx, ny = pts[entry_side]
    return f"exitX={ex};exitY={ey};exitDx=0;exitDy=0;entryX={nx};entryY={ny};entryDx=0;entryDy=0;"


# ---------------------------------------------------------------------------
# 01 system context
# ---------------------------------------------------------------------------
def system_context():
    d = Diagram()
    p = d.page("System context")
    p.title("C4 level 1 – System context: Task &amp; Performance Management", SRC)
    p.legend(C4_LEGEND, 1420, 20)

    c4(p, "actor_user", "Institution user", "Person",
       "Employee, supervisor, administrator or institution owner. Works in the browser through the host platform.",
       120, 150, 260, 110, "actor")
    c4(p, "actor_operator", "Platform operator", "Person",
       "Staff/superuser who uses the Django admin site.", 520, 150, 260, 110, "actor")
    c4(p, "actor_recipient", "External report recipient", "Person",
       "Not a system user. Receives scheduled report e-mails (reports.ExternalUser).", 920, 150, 260, 110, "actor")

    c4(p, "sys_taskmgt", "Task &amp; Performance Management", "Software system",
       "Multi-tenant (per institution) projects, tasks, KPIs, performance reports, improvement plans, "
       "approvals, calendar, announcements and scheduled reports.", 470, 420, 360, 170, "system")

    c4(p, "ext_partner", "Partner / host platform", "External system",
       "Registered as a PartnerSystem. Provisions institutions, users, resources and KPI configuration here; "
       "receives callbacks and notifications.", 40, 430, 280, 150, "external")
    c4(p, "ext_smtp", "SMTP mail server", "External system",
       "Outgoing e-mail (task, KPI, PIP, report and error e-mails).", 120, 760, 240, 110, "external")
    c4(p, "ext_google", "Google OAuth 2.0", "External system",
       "Sign-in with Google (authorisation URL, token exchange, user info).", 420, 760, 240, 110, "external")
    c4(p, "ext_zoom", "Zoom API", "External system",
       "OAuth token helper on Institution; meeting creation helper exists but its call is commented out.",
       720, 760, 240, 110, "external")
    c4(p, "ext_openai", "OpenAI embeddings", "External system",
       "Used only by the load_schema_embeddings management command.", 1020, 760, 240, 110, "external")
    c4(p, "ext_metrics", "Metrics scraper", "External system",
       "Prometheus-format metrics are exposed at /metrics.", 980, 440, 240, 110, "external")

    link(p, "ctx_user_sys", "actor_user", "sys_taskmgt", "uses (HTTPS, via frontend module)")
    link(p, "ctx_operator_sys", "actor_operator", "sys_taskmgt", "administers (/admin)")
    link(p, "ctx_sys_recipient", "sys_taskmgt", "actor_recipient", "e-mails PDF reports", dashed=True,
         extra=side("r", "b"))
    link(p, "ctx_partner_sys", "ext_partner", "sys_taskmgt", "REST calls with X-API-Key",
         extra="exitX=1;exitY=0.3;entryX=0;entryY=0.3;")
    link(p, "ctx_sys_partner", "sys_taskmgt", "ext_partner", "callbacks / notifications (HTTPS + API key)",
         extra="exitX=0;exitY=0.75;entryX=1;entryY=0.75;")
    link(p, "ctx_sys_smtp", "sys_taskmgt", "ext_smtp", "sends e-mail (SMTP/TLS)", extra="exitX=0.15;exitY=1;entryX=0.5;entryY=0;")
    link(p, "ctx_sys_google", "sys_taskmgt", "ext_google", "OAuth code exchange (HTTPS)", extra="exitX=0.4;exitY=1;entryX=0.5;entryY=0;")
    link(p, "ctx_sys_zoom", "sys_taskmgt", "ext_zoom", "HTTPS", dashed=True, extra="exitX=0.65;exitY=1;entryX=0.5;entryY=0;")
    link(p, "ctx_sys_openai", "sys_taskmgt", "ext_openai", "embeddings (CLI only)", dashed=True,
         extra="exitX=0.9;exitY=1;entryX=0.5;entryY=0;")
    link(p, "ctx_metrics_sys", "ext_metrics", "sys_taskmgt", "scrapes /metrics", dashed=True)

    p.inferred("ctx_inferred",
               "• Who scrapes /metrics is not defined in the repo.<br>"
               "• Zoom: no live call path to meeting creation was found.<br>"
               "• Groq, Africa's Talking (SMS) and Microsoft Teams/MSAL are installed or configured "
               "but never called from application code, so they are not drawn.",
               1300, 440, 360, 150)
    d.write(os.path.join(ROOT, "architecture", "01-system-context.drawio"))


# ---------------------------------------------------------------------------
# 02 containers
# ---------------------------------------------------------------------------
def containers():
    d = Diagram()
    p = d.page("Containers")
    p.title("C4 level 2 – Containers", SRC)
    p.legend(C4_LEGEND, 1700, 20)

    c4(p, "actor_user", "Institution user", "Person", "Browser", 40, 250, 200, 90, "actor")
    c4(p, "actor_operator", "Platform operator", "Person", "Browser", 40, 420, 200, 90, "actor")
    c4(p, "ext_partner", "Partner / host platform", "External system",
       "Hosts the frontend module and calls the API server-to-server.", 40, 640, 200, 130, "external")

    p.vertex("boundary", "<b>Task &amp; Performance Management</b> [system boundary]",
             "rounded=1;arcSize=2;whiteSpace=wrap;html=1;dashed=1;dashPattern=8 4;fillColor=none;strokeColor=#1168bd;"
             "verticalAlign=top;align=left;spacingLeft=12;spacingTop=6;fontSize=13;fontColor=#1168bd;container=1;"
             "collapsible=0;", 330, 150, 1040, 760)

    c4(p, "con_frontend", "Frontend module “taskmgt”", "Next.js 15 · React 19 · TypeScript",
       "Mounted in the host platform at /apps/taskmgt. Redux Toolkit, React Query, axios. Own Docker image (node:22-alpine).",
       40, 70, 280, 150, "frontend", parent="boundary")
    c4(p, "con_api", "API application", "Django 5.2 · DRF · Daphne (ASGI) :8000",
       "REST API under /api/*, Django admin, /metrics, server-sent events for notifications, "
       "static files via WhiteNoise, media under /media (DEBUG only). Docker image python:3.10-slim.",
       400, 70, 300, 170, "container", parent="boundary")
    c4(p, "con_worker", "Celery worker", "Celery 5.5 · same code base",
       "Runs ~30 tasks: KPI processing, progress evaluation, e-mails, PDF report generation, "
       "partner callbacks, permission sync. Default queue: productivity_queue.",
       400, 330, 300, 150, "worker", parent="boundary")
    c4(p, "con_beat", "Celery beat", "Celery beat · django-celery-beat DatabaseScheduler",
       "9 periodic schedules declared in core/celery.py (every minute … weekly).",
       40, 330, 280, 150, "worker", parent="boundary")
    c4(p, "con_db", "Relational database", "PostgreSQL",
       f"{sum(1 for t in SNAP['tables'].values() if t['app'] in SNAP['local_apps'])} application tables + framework tables "
       "(sessions, token blacklist, celery beat, auditlog).",
       780, 70, 220, 150, "datastore", parent="boundary",
       shape="shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=12;")
    c4(p, "con_redis", "Redis", "Redis",
       "Celery broker · Channels layer (configured) · notification read-state keys.",
       780, 330, 220, 150, "queue", parent="boundary",
       shape="shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=12;")
    c4(p, "con_media", "Media storage", "Local filesystem (MEDIA_ROOT)",
       "Uploaded attachments, signatures and generated report PDFs (FileSystemStorage).",
       780, 560, 220, 140, "datastore", parent="boundary",
       shape="shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=12;")
    p.note("con_cache_note",
           "<b>Cache:</b> no CACHES setting exists, so Django's default per-process in-memory cache is used "
           "(resource lookup in ResourceMiddleware, partner-system helpers). It is not shared between processes.",
           400, 560, 300, 110, parent="boundary")
    p.inferred("con_inferred",
               "No docker-compose / orchestration config exists. That web and worker share the same MEDIA_ROOT volume, "
               "and how many instances run, is not defined in the repo. The pgvector extension is set up by a shell script only.",
               40, 560, 280, 140, parent="boundary")

    c4(p, "ext_smtp", "SMTP mail server", "External system", "Port 587, STARTTLS", 1450, 300, 200, 90, "external")
    c4(p, "ext_google", "Google OAuth 2.0", "External system", "", 1450, 440, 200, 80, "external")
    c4(p, "ext_zoom", "Zoom API", "External system", "", 1450, 570, 200, 80, "external")
    c4(p, "ext_openai", "OpenAI embeddings", "External system", "management command only", 1450, 700, 200, 90, "external")

    link(p, "c_user_fe", "actor_user", "con_frontend", "HTTPS")
    link(p, "c_fe_api", "con_frontend", "con_api", "JSON/HTTPS · Bearer JWT<br>+ X-Resource-UUID; SSE")
    link(p, "c_operator_api", "actor_operator", "con_api", "HTTPS /admin (session)", extra=side("r", "l") + "entryY=0.8;")
    link(p, "c_partner_api", "ext_partner", "con_api", "JSON/HTTPS · X-API-Key<br>+ user UUID headers",
         extra="exitX=1;exitY=0.3;entryX=0.2;entryY=1;")
    link(p, "c_api_db", "con_api", "con_db", "SQL (Django ORM, psycopg)")
    link(p, "c_api_redis", "con_api", "con_redis", "enqueue tasks · read-state keys", extra=side("r", "t") + "exitY=0.85;")
    link(p, "c_api_media", "con_api", "con_media", "file I/O", dashed=True, extra="exitX=0.95;exitY=1;entryX=0;entryY=0.3;")
    link(p, "c_beat_redis", "con_beat", "con_redis", "enqueue due tasks", extra="exitX=0.5;exitY=1;entryX=0.3;entryY=1;")
    link(p, "c_beat_db", "con_beat", "con_db", "schedule tables", dashed=True, extra="exitX=0.5;exitY=0;entryX=0;entryY=0.85;")
    link(p, "c_redis_worker", "con_redis", "con_worker", "deliver tasks")
    link(p, "c_worker_db", "con_worker", "con_db", "SQL", extra="exitX=1;exitY=0.2;entryX=0.3;entryY=1;")
    link(p, "c_worker_media", "con_worker", "con_media", "write PDFs", extra="exitX=0.8;exitY=1;entryX=0;entryY=0.6;")
    link(p, "c_worker_smtp", "con_worker", "ext_smtp", "SMTP/TLS", extra="exitX=1;exitY=0.4;entryX=0;entryY=0.5;")
    link(p, "c_worker_partner", "con_worker", "ext_partner", "HTTPS callbacks (retry ×5)",
         extra="exitX=0.2;exitY=1;entryX=1;entryY=0.7;")
    link(p, "c_api_google", "con_api", "ext_google", "HTTPS", extra="exitX=1;exitY=0.15;entryX=0.5;entryY=0;" )
    link(p, "c_api_zoom", "con_api", "ext_zoom", "HTTPS", dashed=True, extra="exitX=1;exitY=0.05;entryX=1;entryY=0.5;")
    link(p, "c_api_openai", "con_api", "ext_openai", "CLI: load_schema_embeddings", dashed=True,
         extra="exitX=0.75;exitY=0;entryX=1;entryY=0.5;")
    d.write(os.path.join(ROOT, "architecture", "02-containers.drawio"))


# ---------------------------------------------------------------------------
# 03 components (backend)
# ---------------------------------------------------------------------------
APP_INFO = {
    "users": ("Accounts, profiles, roles, permissions, staff groups, OTP, external identities",
              "views · serializers · services · tasks"),
    "institution": ("Tenants, branches, departments, working days, bank/KYC data, ownership transfer",
                    "views · serializers · services · tasks"),
    "projects": ("Projects, project tasks, statuses, discussions, timesheets, extension requests",
                 "views · serializers · services · task"),
    "tasks": ("Standalone tasks, task groups, statuses, discussions, extension requests",
              "views · serializers · services · task"),
    "performance": ("KPIs, assignments, results, performance reports, PIPs, attention rules, appraisal forms, loyalty",
                    "views · serializers · services · tasks · utils · mixins"),
    "approval": ("Maker-checker engine: documents, levels, approver groups, approvals, approval tasks",
                 "views · serializers · tasks · BaseApprovableModel"),
    "calendar2": ("Calendars, events, occurrences, public holidays", "views · serializers"),
    "communication": ("Notifications (+SSE), notes, announcements, acknowledgements", "views · serializers · notifications"),
    "reports": ("Report schedules, recipients, groups, history, PDF generation", "views · serializers · tasks"),
    "settings": ("System configuration, system days, recycle bin", "views · serializers"),
    "audit": ("Custom AuditLog + django-auditlog", "views · signals · middleware"),
    "system": ("PartnerSystem registry, API-key authentication, outbound partner notifications",
               "authentication · permissions · utils · tasks"),
}
# static import counts between apps (module-level and local imports), see README
IMPORTS = {
    "users": {"projects": 6, "tasks": 1, "utilities": 13, "approval": 3, "institution": 17, "performance": 24, "system": 7, "core": 2, "settings": 1},
    "institution": {"approval": 2, "performance": 7, "settings": 1, "tasks": 1, "users": 13, "utilities": 9, "system": 2, "calendar2": 1},
    "projects": {"approval": 2, "institution": 3, "users": 5, "utilities": 12, "performance": 6, "communication": 1, "core": 11, "tasks": 1, "settings": 1},
    "tasks": {"approval": 2, "system": 3, "users": 7, "utilities": 12, "performance": 13, "core": 15, "communication": 1, "institution": 2, "projects": 1, "settings": 1},
    "performance": {"approval": 5, "institution": 9, "settings": 5, "utilities": 15, "users": 22, "tasks": 4, "projects": 4, "communication": 1, "system": 3},
    "approval": {"users": 4, "utilities": 9, "communication": 7, "institution": 1, "projects": 1, "performance": 7},
    "calendar2": {"approval": 2, "institution": 1, "users": 1, "utilities": 8, "core": 1},
    "communication": {"system": 1, "approval": 2, "users": 2, "utilities": 6, "institution": 1},
    "reports": {"institution": 1, "projects": 1, "users": 5, "utilities": 9},
    "settings": {"approval": 1, "reports": 1, "users": 1, "utilities": 6},
    "audit": {"utilities": 5, "institution": 1, "users": 2},
    "system": {"utilities": 3, "users": 2},
    "utilities": {"settings": 1, "institution": 1, "users": 2},
    "core": {"performance": 1, "institution": 2},
}


def components():
    d = Diagram()
    p = d.page("Backend components")
    p.title("C4 level 3 – Components of the API application (Django backend)", SRC)
    legend = [("container", "Framework / request pipeline component")] + [
        (DOMAIN_COLOURS[a], f"Django app: {a}") for a in SNAP["local_apps"]] + [
        ("worker", "Background execution"), ("datastore", "Data store"), ("queue", "Broker"),
        ("external", "External system")]
    p.legend(legend, 1640, 20, w=280)

    routes = {}
    for r in API["routes"]:
        if r["path"].startswith("/api/") and r.get("drf"):
            seg = r["path"].split("/")[2]
            routes[seg] = routes.get(seg, 0) + 1
    seg_of = {"users": "user", "calendar2": "calendar"}
    tables = {}
    for t in SNAP["tables"].values():
        tables[t["app"]] = tables.get(t["app"], 0) + 1

    # request pipeline ------------------------------------------------------
    y = 150
    c4(p, "cmp_asgi", "ASGI entry", "core/asgi.py · Daphne", "ProtocolTypeRouter – HTTP only", 40, y, 220, 110, "container")
    c4(p, "cmp_middleware", "Middleware chain", "core/settings.py",
       "Prometheus · CORS · <b>ResourceMiddleware</b> (X-Resource-UUID for /api/performance) · Security · WhiteNoise · "
       "Session · CSRF · Auth · crum (current user/request)", 320, y, 360, 110, "container")
    c4(p, "cmp_urls", "URL router", "core/urls.py", "/api/&lt;app&gt;/ → each app's urls.py · /admin · /metrics",
       740, y, 240, 110, "container")
    c4(p, "cmp_auth", "Authentication", "users/authentication.py · system/authentication.py",
       "CrossSystemJWTAuthentication → PartnerSystemAuthentication (X-API-Key) or SimpleJWT. Attaches request.institution.",
       1040, y, 300, 110, "container")
    c4(p, "cmp_perm", "Authorisation", "utilities/permissions.py",
       "IsAuthenticated (default) · MethodPermissionMixin · InstitutionPermission.require → CustomUser.has_permission",
       1040, y + 150, 300, 110, "container")
    link(p, "cmp_e1", "cmp_asgi", "cmp_middleware")
    link(p, "cmp_e2", "cmp_middleware", "cmp_urls")
    link(p, "cmp_e3", "cmp_urls", "cmp_auth", "DRF view dispatch")
    link(p, "cmp_e4", "cmp_auth", "cmp_perm")

    # apps ---------------------------------------------------------------------
    p.vertex("apps_frame", "<b>Django apps</b> – each app follows the same layering: urls → views (APIView) → serializers → "
             "services (where present) → models. Counts: REST routes / tables.",
             "rounded=1;arcSize=2;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#999999;dashed=1;verticalAlign=top;"
             "align=left;spacingLeft=10;spacingTop=4;fontSize=12;container=1;collapsible=0;", 40, 450, 1300, 560)
    for i, app in enumerate(SNAP["local_apps"]):
        fill, stroke = DOMAIN_COLOURS[app]
        desc, layers = APP_INFO[app]
        n_routes = routes.get(seg_of.get(app, app), 0)
        label = (f"<b>{app}</b><br><span style=\"font-size:10px\">{n_routes} routes · {tables.get(app, 0)} tables</span><br>"
                 f"<span style=\"font-size:11px\">{desc}</span><br><span style=\"font-size:10px;color:#555555\"><i>{layers}</i></span>")
        p.vertex(f"app_{app}", label,
                 f"rounded=1;arcSize=8;whiteSpace=wrap;html=1;spacing=6;fillColor={fill};strokeColor={stroke};",
                 20 + (i % 4) * 320, 50 + (i // 4) * 165, 300, 145, parent="apps_frame")
    link(p, "cmp_e5", "cmp_perm", "apps_frame", "handler runs", extra=side("b", "t") + "entryX=0.9;")

    # cross-cutting --------------------------------------------------------------
    y = 1070
    c4(p, "cmp_base", "Shared base models &amp; helpers", "utilities/",
       "SoftDeletableTimeStampedModel (audit columns, base_uuid, soft delete → RecycleBin) · UrlSlugMixin · pagination · "
       "sortable API · helpers (require_current_institution)", 40, y, 300, 130, "container")
    c4(p, "cmp_approvable", "Approval engine", "approval/models.py",
       "BaseApprovableModel: approval_status lifecycle, _trigger_approval, finish_workflow; ApprovalTask mark_* methods.",
       370, y, 300, 130, "container")
    c4(p, "cmp_notify", "Notifications", "communication/notifications.py",
       "add_notification(): Notification row, optional partner callback after commit.", 700, y, 300, 130, "container")
    c4(p, "cmp_partner", "Partner integration", "system/utils.py · system/tasks.py",
       "notify_external_system(_task): endpoint templates from fixtures, API key from PartnerSystem.external_api_key.",
       1030, y, 310, 130, "container")
    link(p, "cmp_e6", "apps_frame", "cmp_base", "inherit / use", extra=side("b", "t") + "exitX=0.12;")
    link(p, "cmp_e7", "apps_frame", "cmp_approvable", "approvable models inherit", extra=side("b", "t") + "exitX=0.37;")
    link(p, "cmp_e8", "apps_frame", "cmp_notify", "add_notification()", extra=side("b", "t") + "exitX=0.62;")
    link(p, "cmp_e9", "apps_frame", "cmp_partner", "notify partner", extra=side("b", "t") + "exitX=0.88;")
    link(p, "cmp_e10", "cmp_approvable", "cmp_notify", "notify approvers")
    link(p, "cmp_e11", "cmp_notify", "cmp_partner", "on_commit → task")

    y = 1280
    c4(p, "cmp_celery", "Celery tasks", "&lt;app&gt;/tasks.py · core/celery.py",
       "Shared tasks per app, enqueued with .delay()/apply_async() from views, serializers, services and models; "
       "beat schedule in core/celery.py.", 40, y, 300, 120, "worker")
    c4(p, "cmp_audit", "Audit trail", "audit/signals.py · django-auditlog",
       "Signal receivers write audit_auditlog; auditlog_logentry from the third-party app.", 370, y, 300, 120, "container")
    c4(p, "cmp_db", "PostgreSQL", "Django ORM", "", 700, y, 300, 120, "datastore",
       shape="shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=12;")
    c4(p, "cmp_redis", "Redis", "broker", "", 1030, y, 150, 120, "queue",
       shape="shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=12;")
    c4(p, "cmp_ext", "Partner platform", "external", "", 1200, y, 140, 120, "external")
    link(p, "cmp_e12", "cmp_base", "cmp_celery", "", dashed=True)
    link(p, "cmp_e13", "cmp_approvable", "cmp_db", "ORM", extra=side("b", "t") + "exitX=0.8;entryX=0.2;")
    link(p, "cmp_e14", "cmp_celery", "cmp_redis", "broker", extra=side("b", "b"))
    link(p, "cmp_e15", "cmp_partner", "cmp_ext", "HTTPS", extra=side("b", "t") + "exitX=0.8;")
    link(p, "cmp_e16", "cmp_audit", "cmp_db", "ORM")
    link(p, "cmp_e17", "cmp_notify", "cmp_db", "ORM", extra=side("b", "t") + "exitX=0.4;")

    p.note("cmp_note",
           "<b>Reading guide</b><br>Arrows show the main request/usage direction. App-to-app coupling is dense and is shown as "
           "an import matrix on the second tab instead of as lines.<br><br>"
           "<b>Layering as found in code:</b> the documented rule is “views/serializers = transport, services = business "
           "rules”. Service modules exist in performance, projects, tasks, users and institution; other apps keep logic in "
           "views, serializers and model methods.", 1400, 580, 420, 230)

    # ---- import matrix ----------------------------------------------------------
    m = d.page("App dependency matrix")
    m.title("Backend – app-to-app import matrix", SRC + " · number of import statements from row app into column app")
    order = SNAP["local_apps"] + ["utilities", "core"]
    cw, ch, x0, y0 = 96, 32, 200, 220
    m.text("mx_hint", "<b>Row imports column.</b> Darker = more import statements. Counted statically from "
           "<i>from X import …</i> / <i>import X</i> lines (migrations excluded). A cycle exists wherever both "
           "(row, col) and (col, row) are filled.", 40, 110, 1200, 50, "fontSize=12;")
    for j, col in enumerate(order):
        fill, stroke = DOMAIN_COLOURS.get(col, ("#ffffff", "#999999"))
        m.vertex(f"mx_col_{col}", f"<b>{col}</b>", f"rounded=0;html=1;fontSize=10;fillColor={fill};strokeColor={stroke};",
                 x0 + j * cw, y0 - ch, cw, ch)
    for i, row in enumerate(order):
        fill, stroke = DOMAIN_COLOURS.get(row, ("#ffffff", "#999999"))
        m.vertex(f"mx_row_{row}", f"<b>{row}</b>", f"rounded=0;html=1;fontSize=11;fillColor={fill};strokeColor={stroke};",
                 x0 - 160, y0 + i * ch, 160, ch)
        for j, col in enumerate(order):
            n = IMPORTS.get(row, {}).get(col, 0)
            if row == col:
                style, val = "fillColor=#cccccc;strokeColor=#dddddd;", ""
            elif n == 0:
                style, val = "fillColor=#ffffff;strokeColor=#dddddd;", ""
            else:
                shade = "#fff2cc" if n < 4 else "#ffd966" if n < 10 else "#f4a261"
                style, val = f"fillColor={shade};strokeColor=#dddddd;", str(n)
            m.vertex(f"mx_{row}_{col}", val, "rounded=0;html=1;fontSize=11;" + style, x0 + j * cw, y0 + i * ch, cw, ch)
    m.legend([(("#fff2cc", "#dddddd"), "1–3 imports"), (("#ffd966", "#dddddd"), "4–9 imports"),
              (("#f4a261", "#dddddd"), "10+ imports"), (("#ffffff", "#dddddd"), "no import")], x0 + len(order) * cw + 40, y0 - ch)
    d.write(os.path.join(ROOT, "architecture", "03-components-backend.drawio"))


# ---------------------------------------------------------------------------
# security / auth + RBAC
# ---------------------------------------------------------------------------
def security():
    d = Diagram()
    p = d.page("Authentication flow")
    p.title("Authentication – how a request becomes (user, institution)", SRC +
            " · users/authentication.py, system/authentication.py, core/middleware.py, core/settings.py")
    step = "rounded=1;arcSize=10;whiteSpace=wrap;html=1;spacing=6;fontSize=11;" + role_style("container")
    dec = "rhombus;whiteSpace=wrap;html=1;fontSize=11;spacing=4;" + role_style("queue")
    ok = "rounded=1;arcSize=40;whiteSpace=wrap;html=1;fontSize=11;" + role_style("datastore")
    bad = "rounded=1;arcSize=40;whiteSpace=wrap;html=1;fontSize=11;fillColor=#f8cecc;strokeColor=#b85450;"
    p.legend([("container", "Processing step"), ("queue", "Decision"), ("datastore", "Request accepted"),
              (("#f8cecc", "#b85450"), "Request rejected")], 1500, 20)

    def S(cid, text, x, y, w=260, h=70, style=step):
        return p.vertex(cid, text, style, x, y, w, h)

    def E(cid, a, b, label="", extra=""):
        return link(p, cid, a, b, label, extra=extra)

    S("a_req", "<b>Incoming HTTP request</b>", 520, 140, 260, 50, ok)
    S("a_mw", "<b>ResourceMiddleware</b><br>path starts with /api/performance and is not in the 3 excluded paths?", 480, 230, 340, 90, dec)
    S("a_mw_hdr", "Look up AppraisalResource by <b>X-Resource-UUID</b> (cached 300 s) → request.current_resource", 900, 240, 300, 70)
    S("a_mw_bad", "400 – header missing or resource invalid", 1280, 250, 240, 50, bad)
    S("a_key", "<b>CrossSystemJWTAuthentication</b><br>X-API-Key header present?", 480, 380, 340, 90, dec)

    # partner branch (left)
    S("a_ps", "PartnerSystem lookup by api_key (is_active)", 60, 390, 300, 70)
    S("a_ps_bad", "401 – invalid or inactive API key", 60, 290, 300, 50, bad)
    S("a_ids", "X-External-User-UUID <b>and</b> X-Internal-User-UUID present?", 60, 520, 300, 90, dec)
    S("a_s2s", "System-to-system call:<br>user = AnonymousUser, auth = PartnerSystem<br>request.is_system_to_system = True", 60, 800, 300, 80, ok)
    S("a_ext", "ExternalIdentity lookup (perac_base_uuid, base_uuid, partner_system, is_active)", 60, 670, 300, 70)
    S("a_ext_bad", "401 – invalid user ID", 420, 680, 200, 50, bad)
    S("a_ext_inst", "Second ExternalIdentity check (not deleted, institution active) → institution = identity.institution", 420, 800, 320, 80)
    S("a_ext_ok", "user = identity.user, auth = PartnerSystem<br>request.institution set", 420, 940, 320, 70, ok)

    # JWT branch (right)
    S("a_jwt", "SimpleJWT: validate <b>Authorization: Bearer</b> access token (HS256, 1 h default; per-institution inactivity lifetime)", 900, 390, 300, 80)
    S("a_jwt_none", "No credentials → unauthenticated;<br>IsAuthenticated then returns 401", 1280, 400, 260, 60, bad)
    S("a_claim", "Token has <b>current_institution</b> claim?", 900, 530, 300, 90, dec)
    S("a_noinst", "Authenticated without institution context (pre-selection token)", 1280, 545, 260, 60, ok)
    S("a_member", "Institution active <b>and</b> (active ProfileInstitution membership <b>or</b> user is institution owner)?", 880, 680, 340, 100, dec)
    S("a_member_bad", "401 – institution access no longer available / membership required", 1280, 700, 260, 60, bad)
    S("a_jwt_ok", "request.institution, request.current_institution, request.profile_institution set", 900, 850, 300, 70, ok)
    S("a_perm", "<b>Authorisation</b> → see “Permission evaluation” tab", 900, 980, 300, 60)

    E("ae1", "a_req", "a_mw")
    E("ae2", "a_mw", "a_mw_hdr", "yes")
    E("ae3", "a_mw_hdr", "a_mw_bad", "not found")
    E("ae4", "a_mw", "a_key", "no")
    E("ae5", "a_mw_hdr", "a_key", "ok", extra=side("b", "r") + "entryY=0.3;")
    E("ae6", "a_key", "a_ps", "yes")
    E("ae7", "a_ps", "a_ps_bad", "not found")
    E("ae8", "a_ps", "a_ids", "found")
    E("ae9", "a_ids", "a_ext", "yes")
    E("ae10", "a_ids", "a_s2s", "no", extra="exitX=0;exitY=0.5;entryX=0;entryY=0.5;")
    E("ae11", "a_ext", "a_ext_bad", "none")
    E("ae12", "a_ext", "a_ext_inst", "found", extra=side("b", "l"))
    E("ae13", "a_ext_inst", "a_ext_ok", "ok")
    E("ae14", "a_key", "a_jwt", "no")
    E("ae15", "a_jwt", "a_jwt_none", "no token")
    E("ae16", "a_jwt", "a_claim", "valid")
    E("ae17", "a_claim", "a_noinst", "no")
    E("ae18", "a_claim", "a_member", "yes")
    E("ae19", "a_member", "a_member_bad", "no")
    E("ae20", "a_member", "a_jwt_ok", "yes")
    E("ae21", "a_jwt_ok", "a_perm")
    E("ae22", "a_ext_ok", "a_perm", "", extra=side("r", "l"))
    p.note("a_note_login",
           "<b>How tokens are obtained</b><br>"
           "• POST /api/user/login/ – identifier may be e-mail, username or phone (MultiAccountAuthBackend). "
           "All previously outstanding refresh tokens of the user are blacklisted on login.<br>"
           "• One institution → tokens with current_institution. Several → 202 + temporary tokens, then "
           "POST /api/user/select-institution/.<br>"
           "• POST /api/user/token/refresh/ – refresh lifetime 2 h, rotation + blacklist.<br>"
           "• Google sign-in: /api/user/auth/google/url/ and /callback/.<br>"
           "• OTP / password reset endpoints are AllowAny.", 1280, 800, 380, 240)
    p.inferred("a_inferred",
               "• Several partner-facing views are declared <i>AllowAny</i> and call PartnerSystemAuthentication "
               "themselves inside the handler; whether every such view enforces the key should be reviewed per view "
               "(see API map).<br>"
               "• /api/user/taskmgt-user-state-data/ is AllowAny but reads request.user.<br>"
               "• GoogleAuthCallbackView reads settings.GOOGLE_AUTH_REDIRECT_URL, which is not defined in core/settings.py.",
               1280, 1080, 380, 190)

    # ---- RBAC model ---------------------------------------------------------
    r = d.page("RBAC model")
    r.title("Roles &amp; permissions – data model", SRC + " · users/models.py, approval/models.py (column-level detail: database/erd-users.drawio)")
    ufill, ustroke = DOMAIN_COLOURS["users"]
    ifill, istroke = DOMAIN_COLOURS["institution"]
    sfill, sstroke = DOMAIN_COLOURS["system"]
    afill, astroke = DOMAIN_COLOURS["approval"]
    r.legend([((ufill, ustroke), "users app"), ((ifill, istroke), "institution app"), ((sfill, sstroke), "system app"),
              ((afill, astroke), "approval app"), ("note", "Behaviour note")], 1500, 20)

    def ent(cid, name, body, x, y, w=250, h=90, colours=(ufill, ustroke)):
        return r.vertex(cid, f"<b>{name}</b><br><span style=\"font-size:10px\">{body}</span>",
                        f"rounded=1;arcSize=8;whiteSpace=wrap;html=1;spacing=6;fillColor={colours[0]};strokeColor={colours[1]};",
                        x, y, w, h)

    def rel(cid, child, parent, label="", one=False, optional=False, extra=""):
        start = "ERzeroToOne" if one else "ERzeroToMany"
        end = "ERzeroToOne" if optional else "ERmandOne"
        return r.edge(cid, label, "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;fontSize=10;labelBackgroundColor=#ffffff;"
                      f"startArrow={start};endArrow={end};startFill=0;endFill=0;startSize=10;endSize=10;strokeColor=#444444;" + extra,
                      source=child, target=parent)

    ent("r_user", "CustomUser", "AUTH_USER_MODEL · email / username / phone login<br>user_type, is_superuser", 80, 160)
    ent("r_profile", "Profile", "one per user", 80, 330)
    ent("r_pi", "ProfileInstitution", "membership of a user in an institution<br>UQ (profile, institution) · work_branch", 80, 500, 250, 100)
    ent("r_inst", "Institution", "tenant · institution_owner → CustomUser<br>owner passes every permission check", 80, 690, 250, 100, (ifill, istroke))
    ent("r_up", "UserPermission", "<b>effective</b> grants<br>UQ (profile_institution, permission)", 440, 500, 250, 100)
    ent("r_perm", "Permission", "permission_code (unique), e.g. can_view_kpis", 800, 500, 250, 100)
    ent("r_cat", "PermissionCategory", "grouping for UI", 1160, 500, 250, 100)
    ent("r_rp", "RolePermission", "role ↔ permission", 800, 330)
    ent("r_role", "Role", "per institution (nullable = global)<br>UQ (name, institution) · approvable", 800, 160)
    ent("r_ur", "UserRole", "user ↔ role · approvable", 440, 160)
    ent("r_sg", "StaffGroup", "per institution · approvable", 1160, 160)
    ent("r_sgr", "StaffGroupRole", "UQ (group, role)", 1160, 330)
    ent("r_sgu", "StaffGroupUser", "UQ (group, user)", 440, 330)
    ent("r_ei", "ExternalIdentity", "maps a user to a partner-system identity<br>UQ (perac_base_uuid, institution, user)", 440, 690, 250, 100)
    ent("r_ps", "PartnerSystem", "api_key (inbound) · external_api_key (outbound) · base_url", 800, 690, 250, 100, (sfill, sstroke))
    ent("r_ag", "ApproverGroup", "may be dynamic: members = users holding a given permission", 1160, 690, 250, 100, (afill, astroke))

    rel("rr1", "r_profile", "r_user", "", one=True)
    rel("rr2", "r_pi", "r_profile")
    rel("rr3", "r_pi", "r_inst")
    rel("rr4", "r_up", "r_pi", "", optional=True)
    rel("rr5", "r_up", "r_perm")
    rel("rr6", "r_perm", "r_cat")
    rel("rr7", "r_rp", "r_perm")
    rel("rr8", "r_rp", "r_role")
    rel("rr9", "r_ur", "r_role")
    rel("rr10", "r_ur", "r_user")
    rel("rr11", "r_sgr", "r_sg")
    rel("rr12", "r_sgr", "r_role", "", extra="exitX=0;exitY=0.3;entryX=1;entryY=0.8;")
    rel("rr13", "r_sgu", "r_sg", "", extra="exitX=1;exitY=0.2;entryX=0;entryY=0.9;")
    rel("rr14", "r_sgu", "r_user", "", extra="exitX=0;exitY=0.5;entryX=1;entryY=0.8;")
    rel("rr15", "r_ei", "r_ps")
    rel("rr16", "r_ei", "r_inst", "", optional=True)
    rel("rr17", "r_ei", "r_user", "", extra="exitX=0.1;exitY=0;entryX=0.9;entryY=1;")
    r.edge("rr18", "dynamic membership by permission code", EDGE + "dashed=1;" + side("t", "r") + "entryY=0.8;",
           source="r_ag", target="r_perm")
    r.note("r_note",
           "<b>How it works</b><br>"
           "1. Roles bundle permissions (RolePermission). Users get roles (UserRole) directly or through staff groups.<br>"
           "2. Role/assignment changes are <b>materialised</b> into UserPermission rows per institution membership by "
           "users/services.py (PermissionSyncService, RoleAssignmentService) and the Celery tasks in users/tasks.py.<br>"
           "3. Checks read only UserPermission: CustomUser.has_permission(code, institution).<br>"
           "4. Role, UserRole, RolePermission and StaffGroup are approvable (approval_status lifecycle).<br>"
           "5. Permission codes are seeded from users/fixtures/permissions.json.", 1500, 250, 400, 280)
    r.inferred("r_inferred",
               "The exact rule for how StaffGroupRole feeds UserPermission was not traced line by line; verify in "
               "users/services.py. Django's built-in groups/user_permissions tables exist (PermissionsMixin) but the "
               "custom tables above are what the API checks.", 1500, 570, 400, 150)

    # ---- permission evaluation ---------------------------------------------
    e = d.page("Permission evaluation")
    e.title("Authorisation – permission evaluation per request", SRC + " · utilities/permissions.py, users/models.py")
    e.legend([("container", "Processing step"), ("queue", "Decision"), ("datastore", "Allowed"),
              (("#f8cecc", "#b85450"), "Denied (403)")], 1300, 20)

    def S2(cid, text, x, y, w=300, h=70, style=step):
        return e.vertex(cid, text, style, x, y, w, h)

    def E2(cid, a, b, label="", extra=""):
        return e.edge(cid, label, EDGE + extra, source=a, target=b)

    S2("p_start", "<b>Authenticated request reaches a DRF view</b>", 420, 140, 300, 50, ok)
    S2("p_default", "permission_classes (default <b>IsAuthenticated</b>; 21 API routes declare AllowAny)", 420, 230, 300, 70)
    S2("p_mixin", "View uses <b>MethodPermissionMixin</b>?<br>(118 routes)", 400, 350, 340, 90, dec)
    S2("p_inline", "No mixin: the handler / service calls InstitutionPermission.require(...) or user.has_permission(...) "
       "itself, or performs no code-level check", 840, 360, 320, 80)
    S2("p_lookup", "method_permissions[HTTP method]<br>(HEAD uses GET; OPTIONS unchecked)", 420, 490, 300, 70)
    S2("p_missing", "Method not declared → 403", 60, 500, 260, 50, bad)
    S2("p_none", "Value is None → no permission needed", 840, 500, 320, 50, ok)
    S2("p_inst", "Current institution on request?", 400, 610, 340, 80, dec)
    S2("p_noinst", "No institution → 403", 60, 625, 260, 50, bad)
    S2("p_owner", "User is institution_owner?", 400, 740, 340, 80, dec)
    S2("p_allow_owner", "Allowed (owner bypass)", 840, 755, 320, 50, ok)
    S2("p_up", "Any of the codes in UserPermission for (user, institution)?<br>deleted rows / deleted permissions excluded", 400, 870, 340, 100, dec)
    S2("p_allow", "Allowed → handler runs (tenant-scoped queries)", 840, 895, 320, 50, ok)
    S2("p_deny", "403 – “You do not have permission to perform this action.”", 60, 895, 260, 50, bad)
    E2("pe1", "p_start", "p_default")
    E2("pe2", "p_default", "p_mixin")
    E2("pe3", "p_mixin", "p_inline", "no")
    E2("pe4", "p_mixin", "p_lookup", "yes")
    E2("pe5", "p_lookup", "p_missing", "missing")
    E2("pe6", "p_lookup", "p_none", "None")
    E2("pe7", "p_lookup", "p_inst", "code(s)")
    E2("pe8", "p_inst", "p_noinst", "no")
    E2("pe9", "p_inst", "p_owner", "yes")
    E2("pe10", "p_owner", "p_allow_owner", "yes")
    E2("pe11", "p_owner", "p_up", "no")
    E2("pe12", "p_up", "p_allow", "yes")
    E2("pe13", "p_up", "p_deny", "no")
    e.note("p_note",
           "<b>Notes</b><br>• A tuple of codes means “any one is enough”.<br>"
           "• Django superusers pass has_perm() (admin site), but has_permission() itself only has the owner bypass.<br>"
           "• The frontend hides pages/controls with the same codes (module.json requiredPermissions); the backend "
           "check is authoritative.", 1260, 330, 360, 190)
    d.write(os.path.join(ROOT, "security", "auth-rbac.drawio"))


if __name__ == "__main__":
    system_context()
    containers()
    components()
    security()
    print("architecture + security diagrams written")
