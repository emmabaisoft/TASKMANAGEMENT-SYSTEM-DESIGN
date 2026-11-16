#!/usr/bin/env python3
"""Generate sequence diagrams (flows/seq-*.drawio) and state machines (flows/state-*.drawio).

    python3 tools/gen_flows.py

Content is hand-modelled from the code paths named in each diagram; only the
layout is programmatic.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from drawio import Diagram, Page, role_style  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = json.load(open(os.path.join(ROOT, "database", "schema-snapshot.json")))
COMMIT = (SNAP["source"]["commit"] or "unknown")[:8]
SRC = f"Derived from the project repo at commit {COMMIT}"

# ---------------------------------------------------------------------------
# sequence diagram helper
# ---------------------------------------------------------------------------
SEQ_LEGEND = [
    ("actor", "Person / client"), ("frontend", "Frontend"), ("container", "API component"),
    ("worker", "Celery worker / beat"), ("datastore", "Data store"), ("queue", "Broker / cache"),
    ("external", "External system"), ("note", "Note"), ("inferred", "Inferred – verify"),
]
COL, HEAD_W, HEAD_H, TOP = 240, 190, 64, 150


def sequence(d: Diagram, name, title, sources, participants, steps):
    p = d.page(name)
    p.title(title, SRC + " · " + sources, w=1300)
    cx = {}
    for i, (pid, label, role) in enumerate(participants):
        x = 60 + i * COL
        cx[pid] = x + HEAD_W / 2
        p.vertex(f"p_{pid}", label, "rounded=1;arcSize=8;whiteSpace=wrap;html=1;fontSize=11;fontStyle=1;" + role_style(role),
                 x, TOP, HEAD_W, HEAD_H)
    right = 60 + len(participants) * COL
    note_x = right + 20
    y = TOP + HEAD_H + 50
    n = 0
    note_bottom = 0
    frames = []
    k = 0
    for step in steps:
        kind = step[0]
        k += 1
        if kind == "msg":
            _, src, dst, label, style = (list(step) + ["sync"])[:5]
            n += 1
            two = label.count("<br>")
            y += 16 * two
            st = {"sync": "endArrow=block;endFill=1;", "async": "endArrow=open;endFill=0;",
                  "return": "endArrow=open;endFill=0;dashed=1;"}[style]
            p.edge(f"m{k}", f"{n}. {label}",
                   "html=1;rounded=0;fontSize=10;verticalAlign=bottom;labelBackgroundColor=#ffffff;strokeColor=#333333;" + st,
                   source_point=(cx[src], y), target_point=(cx[dst], y))
            y += 46
        elif kind == "self":
            _, pid, label = step
            n += 1
            lines = label.count("<br>") + 1
            p.edge(f"m{k}", "", "html=1;rounded=0;endArrow=block;endFill=1;strokeColor=#333333;",
                   source_point=(cx[pid], y), target_point=(cx[pid], y + 26),
                   points=[(cx[pid] + 40, y), (cx[pid] + 40, y + 26)])
            p.text(f"m{k}_tx", f"{n}. {label}", cx[pid] + 46, y - 6, 180, 14 * lines + 10, "fontSize=10;allowOverlap=1;")
            y += max(52, 14 * lines + 30)
        elif kind in ("note", "inferred"):
            _, text = step
            lines = max(2, -(-len(text.replace("<br>", " " * 60)) // 52))
            h = 18 + 14 * lines + (14 if kind == "inferred" else 0)
            ny = max(y - 60, note_bottom + 10)
            (p.inferred if kind == "inferred" else p.note)(f"n{k}", text, note_x, ny, 320, h)
            note_bottom = ny + h
        elif kind == "frame":
            _, label = step
            frames.append((k, label, y - 26))
            y += 22
        elif kind == "end":
            fk, label, fy = frames.pop()
            p.vertex(f"f{fk}", f"<b>{label}</b>",
                     "rounded=0;whiteSpace=wrap;html=1;fillColor=none;dashed=1;strokeColor=#888888;verticalAlign=top;"
                     "align=left;spacingLeft=6;spacingTop=2;fontSize=10;fontColor=#555555;allowOverlap=1;",
                     30, fy, right - 30, y - fy - 10)
            y += 20
    bottom = max(y, note_bottom) + 20
    for pid, _label, _role in participants:
        p.edge(f"life_{pid}", "", "html=1;dashed=1;endArrow=none;strokeColor=#999999;",
               source_point=(cx[pid], TOP + HEAD_H), target_point=(cx[pid], bottom))
    used_roles = {r for _i, _l, r in participants} | {"note", "inferred"}
    p.legend([it for it in SEQ_LEGEND if it[0] in used_roles] +
             [(("#ffffff", "#333333"), "solid ▶ call · open → async · dashed → return"),
              (("#ffffff", "#888888", "dashed=1;"), "alt / opt / loop fragment")],
             note_x + 360, 20, w=300)
    return p


def write(d, name):
    d.write(os.path.join(ROOT, "flows", name))


# ---------------------------------------------------------------------------
# sequences
# ---------------------------------------------------------------------------
def seq_login():
    d = Diagram()
    sequence(
        d, "Login", "Sequence – login, institution selection and authenticated request",
        "users/views.py (LoginView, SelectInstitutionView, CustomTokenRefreshView), users/authentication.py, users/models.py",
        [("fe", "Frontend module<br>(browser)", "frontend"), ("login", "LoginView<br>/api/user/login/", "container"),
         ("backend", "MultiAccountAuthBackend", "container"), ("select", "SelectInstitutionView", "container"),
         ("auth", "CrossSystemJWT-<br>Authentication", "container"), ("db", "PostgreSQL", "datastore")],
        [
            ("msg", "fe", "login", "POST {identifier, password}"),
            ("msg", "login", "backend", "authenticate(username=identifier)"),
            ("msg", "backend", "db", "users by email | username | phone"),
            ("self", "backend", "check_password() on each match"),
            ("msg", "backend", "login", "user or None", "return"),
            ("note", "Invalid credentials → 400 “Invalid Credentials”. The endpoint is AllowAny."),
            ("msg", "login", "db", "blacklist all OutstandingToken of user"),
            ("self", "login", "is_active, is_email_verified,<br>is_password_verified checks"),
            ("msg", "login", "db", "active institutions for user"),
            ("frame", "alt  [0 or 1 institution]"),
            ("msg", "login", "fe", "200 tokens (current_institution, resource_uuid)", "return"),
            ("end",),
            ("frame", "alt  [several institutions]"),
            ("msg", "login", "fe", "202 temporary tokens + institution list", "return"),
            ("msg", "fe", "select", "POST /api/user/select-institution/ (Bearer temp token)"),
            ("msg", "select", "db", "ProfileInstitution membership (is_active)"),
            ("msg", "select", "fe", "200 access + refresh with current_institution claim", "return"),
            ("end",),
            ("note", "Access token lifetime: 1 h by default, or Institution.user_inactivity_time minutes when set. "
                     "Refresh: 2 h, rotated and blacklisted (SIMPLE_JWT)."),
            ("frame", "every later API call"),
            ("msg", "fe", "auth", "request · Authorization: Bearer · X-Resource-UUID"),
            ("msg", "auth", "db", "institution active? membership or owner?"),
            ("msg", "auth", "fe", "view response, or 401 if membership was lost", "return"),
            ("end",),
            ("frame", "opt  [access token expired]"),
            ("msg", "fe", "login", "POST /api/user/token/refresh/ {refresh}"),
            ("msg", "login", "fe", "200 tokens + user + institutions", "return"),
            ("end",),
            ("note", "Steps 17–18 are handled by CustomTokenRefreshView (drawn on the LoginView lifeline to save space). "
                     "It only answers for user_type STAFF."),
        ])
    write(d, "seq-login-and-institution-selection.drawio")


def seq_partner():
    d = Diagram()
    sequence(
        d, "Partner provisioning", "Sequence – partner platform provisions an institution and its users",
        "institution/views.py (TaskMgtActivationView), users/views.py (ExternalSystemsUserCreateView), users/tasks.py, "
        "system/authentication.py, system/tasks.py",
        [("partner", "Partner / host platform", "external"), ("view", "API view", "container"),
         ("pauth", "PartnerSystem-<br>Authentication", "container"), ("redis", "Redis (broker)", "queue"),
         ("worker", "Celery worker", "worker"), ("db", "PostgreSQL", "datastore")],
        [
            ("frame", "1 · activate the module for an institution (synchronous)"),
            ("msg", "partner", "view", "POST /api/institution/task-mgt-activation/<br>X-API-Key + institution payload"),
            ("msg", "view", "pauth", "authenticate(request)"),
            ("msg", "pauth", "db", "PartnerSystem by api_key, is_active"),
            ("msg", "pauth", "view", "(user | None, system) or 401", "return"),
            ("self", "view", "TaskMgtActivationSerializer<br>.is_valid() / .save()"),
            ("msg", "view", "db", "create Institution, owner, memberships …"),
            ("msg", "view", "partner", "201 created · 200 if it already exists", "return"),
            ("end",),
            ("note", "The view is declared AllowAny and authenticates the API key itself. Failures are logged with a "
                     "structured “initial sync failure” report (stage, payload, HTTP status)."),
            ("frame", "2 · create a user (asynchronous)"),
            ("msg", "partner", "view", "POST /api/user/external-user/<br>X-API-Key + user UUID headers"),
            ("msg", "view", "pauth", "authenticate(request)"),
            ("self", "view", "ExternalSystemsUserSerializer<br>.is_valid()"),
            ("msg", "view", "redis", "process_external_system_user_create.delay(...)", "async"),
            ("msg", "view", "partner", "202 accepted (task id)", "return"),
            ("msg", "redis", "worker", "deliver task", "async"),
            ("msg", "worker", "db", "create CustomUser, Profile, ProfileInstitution,<br>ExternalIdentity"),
            ("end",),
            ("note", "The task retries after 60 s on database OperationalError (max 3). "
                     "PATCH /api/user/external-user/update/ follows the same pattern."),
            ("frame", "3 · outbound callback to the partner"),
            ("msg", "worker", "redis", "notify_external_system_task.delay(resource_type, action, payload)", "async"),
            ("msg", "redis", "worker", "deliver task", "async"),
            ("msg", "worker", "db", "ExternalIdentity → PartnerSystem.external_api_key, base_url"),
            ("msg", "worker", "partner", "HTTP request to templated endpoint<br>X-API-Key + user UUID headers (timeout 10 s)"),
            ("msg", "partner", "worker", "response", "return"),
            ("msg", "worker", "redis", "after_notify_duties_task.delay(...) on create", "async"),
            ("end",),
            ("note", "Endpoint templates come from users/fixtures/integration_endpoints.json. Retries: up to 5 with "
                     "exponential backoff (max 60 s) on requests.RequestException."),
            ("inferred", "Which business events trigger step 15 was not enumerated exhaustively; it is called from "
                         "performance, users, tasks and communication code via .delay()."),
        ])
    write(d, "seq-partner-system-provisioning.drawio")


def seq_approval():
    d = Diagram()
    sequence(
        d, "Approval workflow", "Sequence – maker-checker approval of a change",
        "approval/models.py (BaseApprovableModel, ApprovalTask), approval/views.py, communication/notifications.py",
        [("maker", "Maker (user)", "actor"), ("view", "Resource view<br>e.g. KpiDetailView", "container"),
         ("model", "BaseApprovableModel<br>instance", "container"), ("db", "PostgreSQL", "datastore"),
         ("taskview", "ApprovalTask views<br>/api/approval/…", "container"), ("approver", "Approver (user)", "actor")],
        [
            ("msg", "maker", "view", "PATCH resource"),
            ("msg", "view", "model", "approval_status = under_update; save()"),
            ("self", "model", "snapshot original_data"),
            ("msg", "view", "model", "confirm_update()"),
            ("msg", "model", "db", "ApprovalDocument for (institution, model, action)?"),
            ("frame", "alt  [no document configured and no custom logic]"),
            ("self", "model", "approval_status = active<br>finish_workflow(completed)"),
            ("end",),
            ("frame", "alt  [document found]"),
            ("msg", "model", "db", "is_active = False; INSERT Approval (ongoing)"),
            ("msg", "model", "db", "INSERT ApprovalTask per level<br>(level 1 pending, others not_started)"),
            ("msg", "model", "db", "INSERT Notification for each level-1 approver"),
            ("end",),
            ("msg", "view", "maker", "200 – change is pending approval", "return"),
            ("note", "Models with has_custom_logic and no document get an auto-generated one-level document whose "
                     "approvers are a dynamic ApproverGroup = users holding the model's FINAL_APPROVAL_PERMISSION."),
            ("msg", "approver", "taskview", "PATCH approval-tasks/&lt;uuid&gt;/approve/ {comment}"),
            ("msg", "taskview", "db", "task.mark_completed(user): must be pending + approver"),
            ("frame", "alt  [another level remains]"),
            ("msg", "taskview", "db", "next task → pending; notify its approvers"),
            ("end",),
            ("frame", "alt  [last level]"),
            ("msg", "taskview", "db", "Approval → completed"),
            ("msg", "taskview", "model", "finish_workflow(approval)"),
            ("msg", "model", "db", "approval_status = active, is_active = True,<br>original_data = None"),
            ("end",),
            ("msg", "taskview", "approver", "200", "return"),
            ("note", "<b>Reject</b> (…/reject/): task rejected, Approval rejected, other open tasks terminated; "
                     "create → object soft-deleted, update → original_data restored, delete → object stays active.<br>"
                     "<b>Override</b> (/api/approval/override/&lt;uuid&gt;/): an overrider completes the whole approval at once."),
            ("note", "The creator is notified of the outcome through add_notification()."),
        ])
    write(d, "seq-approval-workflow.drawio")


def seq_report():
    d = Diagram()
    sequence(
        d, "Performance report", "Sequence – KPI assignment generation, performance report submission and review",
        "core/celery.py, performance/tasks.py, performance/services.py (KpiAssignmentProcessor, "
        "PerformanceReportSubmissionService, finalize_performance_report, reject_performance_report), performance/utils.py",
        [("beat", "Celery beat", "worker"), ("worker", "Celery worker", "worker"), ("db", "PostgreSQL", "datastore"),
         ("api", "performance views<br>+ services", "container"), ("emp", "Employee", "actor"), ("sup", "Supervisor", "actor")],
        [
            ("frame", "hourly (minute 0)"),
            ("msg", "beat", "worker", "run_kpi_assignment_processor", "async"),
            ("msg", "worker", "db", "activate scheduled PIPs; create Assignments for due windows<br>from KpiAssignmentConfiguration"),
            ("end",),
            ("frame", "daily (23:58)"),
            ("msg", "beat", "worker", "dispatch_next_day_preliminary_requested_reports_task", "async"),
            ("msg", "worker", "db", "generate next day's PerformanceRequestedReportInstance rows (pending)"),
            ("end",),
            ("note", "Other schedules: progress evaluation, hourly progress dispatch and reminder e-mails every 5 min; "
                     "attention-record evaluation hourly."),
            ("msg", "emp", "api", "POST requested-reports/current-required/resolve/"),
            ("msg", "api", "db", "ensure instances for this resource; mark overdue<br>preliminary instances as missed; list current"),
            ("msg", "emp", "api", "POST performance-report-entries/ (values, evidence)"),
            ("msg", "api", "db", "PerformanceReport (draft) + entries"),
            ("msg", "emp", "api", "POST performance-reports/&lt;uuid&gt;/submit/"),
            ("msg", "api", "db", "report + entries → submitted; instance →<br>submitted_on_time | submitted_late (vs due_at)"),
            ("msg", "api", "worker", "on_commit: recompute_kpi_assignment_progress_task,<br>aggregate_preliminary_reports_task", "async"),
            ("msg", "api", "emp", "200", "return"),
            ("msg", "sup", "api", "POST performance-report-entries/&lt;uuid&gt;/action/ (approve | reject)"),
            ("msg", "api", "db", "entry → approved (accepted value) | rejected"),
            ("self", "api", "sync_performance_report_status()"),
            ("frame", "alt  [all active entries approved]"),
            ("msg", "api", "db", "finalize_performance_report(): lock report + entries,<br>create missing Result rows, report → approved"),
            ("end",),
            ("frame", "alt  [all entries rejected]"),
            ("msg", "api", "db", "reject_performance_report(REVIEW_REJECTION): report → rejected"),
            ("msg", "api", "worker", "on_commit: send_performance_report_rejected_email_task", "async"),
            ("end",),
            ("frame", "alt  [mixed]"),
            ("msg", "api", "db", "report → partially_reviewed"),
            ("end",),
            ("msg", "api", "sup", "200", "return"),
            ("note", "Results are created only when every active entry and the report are approved "
                     "(performance/REPORT_LIFECYCLE.md). A whole report can also be approved or rejected with "
                     "POST performance-reports/&lt;uuid&gt;/approve/."),
            ("note", "All /api/performance requests need the X-Resource-UUID header (ResourceMiddleware) to identify "
                     "the acting AppraisalResource."),
        ])
    write(d, "seq-performance-report-submission-and-review.drawio")


def seq_scheduled_report():
    d = Diagram()
    sequence(
        d, "Scheduled report", "Sequence – scheduled report generation and e-mail delivery",
        "core/celery.py, reports/tasks.py, reports/models.py, templates/reports/",
        [("beat", "Celery beat", "worker"), ("redis", "Redis (broker)", "queue"), ("worker", "Celery worker<br>reports/tasks.py", "worker"),
         ("db", "PostgreSQL", "datastore"), ("fs", "Media storage", "datastore"), ("smtp", "SMTP server", "external")],
        [
            ("frame", "loop  [every minute]"),
            ("msg", "beat", "redis", "process_due_schedules", "async"),
            ("msg", "redis", "worker", "deliver", "async"),
            ("msg", "worker", "db", "ReportSchedule: active, not paused,<br>next_run_at ≤ now OR run_immediately"),
            ("msg", "worker", "redis", "process_single_schedule.delay(id) per schedule", "async"),
            ("end",),
            ("msg", "redis", "worker", "process_single_schedule(id)", "async"),
            ("self", "worker", "should_schedule_run_now()"),
            ("msg", "worker", "db", "collect report data (filters_json)"),
            ("self", "worker", "generate_report_pdf():<br>render template → WeasyPrint"),
            ("msg", "worker", "fs", "write PDF file"),
            ("msg", "worker", "db", "INSERT ReportHistory"),
            ("msg", "worker", "db", "collect_recipients(): users, staff groups,<br>report groups, external users"),
            ("frame", "loop  [each recipient]"),
            ("msg", "worker", "smtp", "send_report_email() with PDF attachment"),
            ("msg", "worker", "db", "INSERT ReportHistoryRecipient (sent_successfully)"),
            ("end",),
            ("note", "process_single_schedule retries with exponential backoff (60 s × 2ⁿ) on errors other than AttributeError."),
            ("frame", "loop  [every minute]"),
            ("msg", "beat", "redis", "update_next_run_times", "async"),
            ("msg", "redis", "worker", "deliver", "async"),
            ("msg", "worker", "db", "recompute ReportSchedule.next_run_at"),
            ("end",),
            ("frame", "weekly  [Sunday 02:00]"),
            ("msg", "beat", "redis", "cleanup_old_report_files(days_old=7)", "async"),
            ("msg", "redis", "worker", "deliver", "async"),
            ("msg", "worker", "fs", "delete old PDF files"),
            ("end",),
            ("note", "Schedules are created through /api/reports/schedule/. A schedule with run_immediately can also be "
                     "started by trigger_immediate_schedule."),
        ])
    write(d, "seq-scheduled-report-email.drawio")


def seq_notifications():
    d = Diagram()
    sequence(
        d, "Notifications", "Sequence – notification creation and delivery",
        "communication/notifications.py, communication/views.py, system/tasks.py",
        [("svc", "Any service / model<br>(e.g. approval)", "container"), ("db", "PostgreSQL", "datastore"),
         ("worker", "Celery worker", "worker"), ("partner", "Partner / host platform", "external"),
         ("api", "communication views", "container"), ("redis", "Redis", "queue"), ("fe", "Frontend module", "frontend")],
        [
            ("msg", "svc", "db", "add_notification(): INSERT communication_notification"),
            ("frame", "opt  [notify_external_system=True]"),
            ("msg", "svc", "worker", "on_commit: notify_external_system_task<br>(resource_type=notifications, action=create)", "async"),
            ("msg", "worker", "partner", "HTTP POST notification payload (X-API-Key)"),
            ("end",),
            ("frame", "REST polling"),
            ("msg", "fe", "api", "GET /api/communication/all-notifications/"),
            ("msg", "api", "db", "Notification rows of the user"),
            ("msg", "api", "fe", "200 list", "return"),
            ("end",),
            ("frame", "server-sent events"),
            ("msg", "fe", "api", "GET /api/communication/notifications/sse/"),
            ("msg", "api", "fe", "text/event-stream: “SSE connection established”", "return"),
            ("frame", "loop  [every 0.5 s]"),
            ("msg", "api", "redis", "LRANGE notifications:{user_id}<br>SMEMBERS read_notifications:{user_id}"),
            ("msg", "api", "fe", "data: unread notification(s); heartbeat every 10 s", "return"),
            ("end",),
            ("end",),
            ("msg", "fe", "api", "POST /api/communication/notifications/read/"),
            ("msg", "api", "redis", "SADD read_notifications:{user_id}"),
            ("inferred", "No code path writes the Redis list notifications:{user_id}: the only RPUSH is commented out "
                         "in communication/views.py. As written, the SSE stream can only deliver heartbeats. Confirm "
                         "whether another service fills this list or whether the stream is legacy."),
            ("note", "Channels and a Redis channel layer are configured, but core/asgi.py routes HTTP only "
                     "(no WebSocket consumers)."),
        ])
    write(d, "seq-notification-delivery.drawio")


# ---------------------------------------------------------------------------
# state machine helper
# ---------------------------------------------------------------------------
STATE_LEGEND = [
    (("#dae8fc", "#6c8ebf"), "State (stored value)"),
    (("#d5e8d4", "#82b366"), "Terminal / settled state"),
    (("#ffffff", "#cc0000", "dashed=1;"), "Defined but no transition found – verify"),
    (("#ffe6cc", "#d79b00", "dashed=1;"), "Derived at query time, never stored"),
    ("note", "Note"),
]
SW, SH = 210, 60


def state_page(d: Diagram, name, title, sources, states, transitions, notes=(), legend_xy=(1500, 20)):
    p = d.page(name)
    p.title(title, SRC + " · " + sources, w=1300)
    styles = {
        "normal": "rounded=1;arcSize=30;whiteSpace=wrap;html=1;fontSize=12;fontStyle=1;fillColor=#dae8fc;strokeColor=#6c8ebf;",
        "final": "rounded=1;arcSize=30;whiteSpace=wrap;html=1;fontSize=12;fontStyle=1;fillColor=#d5e8d4;strokeColor=#82b366;",
        "orphan": "rounded=1;arcSize=30;whiteSpace=wrap;html=1;fontSize=12;fontStyle=1;fillColor=#ffffff;strokeColor=#cc0000;"
                  "dashed=1;fontColor=#cc0000;",
        "derived": "rounded=1;arcSize=30;whiteSpace=wrap;html=1;fontSize=12;fontStyle=1;fillColor=#ffe6cc;strokeColor=#d79b00;dashed=1;",
    }
    oy = 80  # keep clear of the title block
    for sid, (label, x, y, kind) in states.items():
        y += oy
        if kind == "initial":
            p.vertex(f"s_{sid}", "", "ellipse;html=1;fillColor=#000000;strokeColor=#000000;", x, y, 30, 30)
        elif kind == "end":
            p.vertex(f"s_{sid}", label, "ellipse;shape=doubleEllipse;html=1;fillColor=#000000;strokeColor=#000000;"
                     "fontColor=#000000;labelPosition=center;verticalLabelPosition=bottom;verticalAlign=top;fontSize=11;",
                     x, y, 34, 34)
        else:
            p.vertex(f"s_{sid}", label, styles[kind], x, y, SW, SH)
    pts = {"l": (0, 0.5), "r": (1, 0.5), "t": (0.5, 0), "b": (0.5, 1)}
    for i, tr in enumerate(transitions):
        src, dst, label = tr[0], tr[1], tr[2]
        route = tr[3] if len(tr) > 3 else ""
        dashed = len(tr) > 4 and tr[4]
        extra = ""
        if route:
            ex, en = route.split(">")

            def pt(spec):
                x, y = pts[spec[0]]
                if len(spec) > 1:  # offset like r+ / r- shifts along the side
                    shift = 0.25 if spec[1] == "+" else -0.25
                    if spec[0] in "lr":
                        y += shift
                    else:
                        x += shift
                return x, y
            (ax, ay), (bx, by) = pt(ex), pt(en)
            extra = f"exitX={ax};exitY={ay};exitDx=0;exitDy=0;entryX={bx};entryY={by};entryDx=0;entryDy=0;"
        p.edge(f"t{i + 1}_{src}_{dst}", label,
               "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;fontSize=10;labelBackgroundColor=#ffffff;endArrow=block;"
               "endFill=1;strokeColor=#444444;" + ("dashed=1;" if dashed else "") + extra,
               source=f"s_{src}", target=f"s_{dst}")
    for i, (kind, text, x, y, w, h) in enumerate(notes):
        (p.inferred if kind == "inferred" else p.note)(f"note{i + 1}", text, x, y + oy, w, h)
    p.legend(STATE_LEGEND, legend_xy[0], legend_xy[1], w=300)
    return p


def state_approval_status():
    d = Diagram()
    n_models = sum(1 for t in SNAP["tables"].values() for c in t["columns"]
                   if c["name"] == "approval_status" and c.get("choices") and "under_creation" in c["choices"])
    state_page(
        d, "approval_status", f"State machine – approval_status of approvable models ({n_models} tables)",
        "approval/models.py (BaseApprovableModel)",
        {
            "init": ("", 80, 315, "initial"),
            "under_creation": ("under_creation", 240, 300, "normal"),
            "active": ("active", 760, 300, "final"),
            "under_update": ("under_update", 1260, 300, "normal"),
            "under_deletion": ("under_deletion", 760, 600, "normal"),
            "deleted": ("soft-deleted<br><span style=\"font-weight:normal;font-size:10px\">deleted_at set · RecycleBin row</span>", 240, 600, "final"),
        },
        [
            ("init", "under_creation", "object created"),
            ("under_creation", "active", "confirm_create() →<br>approved / overridden /<br>no workflow configured"),
            ("under_creation", "deleted", "create rejected"),
            ("active", "under_update", "PATCH: view or serializer sets under_update;<br>save() snapshots original_data", "r->l-"),
            ("under_update", "active", "confirm_update() → approved (keep changes) ·<br>rejected (restore original_data) · no workflow", "l+>r+"),
            ("active", "under_deletion", "DELETE →<br>confirm_delete()", "b->t-"),
            ("under_deletion", "active", "delete rejected", "t+>b+"),
            ("under_update", "under_deletion", "DELETE while under_update", "b>r"),
            ("under_deletion", "deleted", "delete approved / no workflow"),
        ],
        [
            ("note", "<b>While an approval is running</b> for create or update the object has is_active = False. "
                     "An Approval row (ongoing) and one ApprovalTask per level exist; see state-approval-task.drawio.<br><br>"
                     "<b>No workflow configured</b> (no ApprovalDocument for institution + model + action and no custom "
                     "logic): the transition completes immediately.", 240, 760, 520, 150),
            ("inferred", "projects.Task and tasks.StandaloneTask override finish_workflow() and also assign the strings "
                         "“deleted” and “rejected”, which are not in the declared choices. Institution.approval_status "
                         "uses a different value set (pending / approved / rejected / under_review) for which no "
                         "assignments were found in code.", 820, 760, 520, 150),
        ])
    write(d, "state-approval-status.drawio")


def state_approval_task():
    d = Diagram()
    state_page(
        d, "ApprovalTask", "State machine – ApprovalTask.status (one task per approval level)",
        "approval/models.py (ApprovalTask.mark_completed / mark_rejected / mark_overridden)",
        {
            "init": ("", 80, 315, "initial"),
            "not_started": ("not_started", 240, 520, "normal"),
            "pending": ("pending", 240, 300, "normal"),
            "approved": ("approved", 820, 140, "final"),
            "rejected": ("rejected", 820, 300, "final"),
            "overridden": ("overridden", 820, 460, "final"),
            "terminated": ("terminated", 820, 620, "final"),
        },
        [
            ("init", "pending", "level 1 task"),
            ("init", "not_started", "tasks of later levels", "b>l"),
            ("not_started", "pending", "previous level approved"),
            ("pending", "approved", "mark_completed(user)<br>user must be an approver", "t>l"),
            ("pending", "rejected", "mark_rejected(user)"),
            ("pending", "overridden", "mark_overridden(user)<br>user must be an overrider", "r+>l"),
            ("not_started", "terminated", "another task of the approval<br>was rejected or overridden", "r>l"),
            ("pending", "terminated", "", "b+>l-"),
        ],
        [
            ("note", "Every mark_* method requires status = pending and runs in one transaction. "
                     "Approvers and overriders come from ApprovalDocumentLevel (approver groups: static users, roles, or "
                     "dynamic by permission).", 240, 720, 520, 110),
            ("note", "approval/tasks.py defines send_overdue_approval_reminders, but it is not in the code-defined beat "
                     "schedule (it may be registered in the django-celery-beat tables).", 820, 720, 420, 110),
        ])
    state_page(
        d, "Approval", "State machine – Approval.status (one approval per requested change)",
        "approval/models.py (BaseApprovableModel._trigger_approval, ApprovalTask.mark_*)",
        {
            "init": ("", 80, 315, "initial"),
            "ongoing": ("ongoing", 240, 300, "normal"),
            "completed": ("completed", 820, 200, "final"),
            "rejected": ("rejected", 820, 420, "final"),
        },
        [
            ("init", "ongoing", "_trigger_approval(action)"),
            ("ongoing", "completed", "last level approved · any task overridden ·<br>document has no levels", "t>l"),
            ("ongoing", "rejected", "any task rejected", "b>l"),
        ],
        [("note", "On completed / rejected the target object's finish_workflow(approval) is called; "
                  "see state-approval-status.drawio for the effect.", 240, 540, 520, 80)])
    write(d, "state-approval-task.drawio")


def state_performance_report():
    d = Diagram()
    state_page(
        d, "PerformanceReport", "State machine – PerformanceReport.status",
        "performance/services.py (PerformanceReportSubmissionService.submit, finalize_performance_report, "
        "reject_performance_report), performance/utils.py (sync_performance_report_status), performance/models.py",
        {
            "init": ("", 80, 315, "initial"),
            "draft": ("draft", 240, 300, "normal"),
            "submitted": ("submitted", 760, 300, "normal"),
            "partially_reviewed": ("partially_reviewed", 1280, 300, "normal"),
            "approved": ("approved", 1280, 80, "final"),
            "rejected": ("rejected", 1280, 560, "final"),
            "waived": ("waived", 240, 560, "final"),
        },
        [
            ("init", "draft", "report created"),
            ("draft", "submitted", "submit()<br>POST …/submit/", "r->l-"),
            ("submitted", "draft", "recomputed: no active entries left", "l+>r+", True),
            ("submitted", "partially_reviewed", "entries reviewed,<br>statuses mixed", "r->l-"),
            ("partially_reviewed", "submitted", "recomputed: all entries submitted", "l+>r+", True),
            ("submitted", "approved", "all entries approved →<br>finalize_performance_report()<br>creates Result rows", "t>l"),
            ("partially_reviewed", "approved", "last entry approved", "t>b"),
            ("submitted", "rejected", "all entries rejected / reject_performance_report()<br>reason REVIEW_REJECTION or PIP_BYPASS", "b>l"),
            ("partially_reviewed", "rejected", "allowed only if no entry<br>already has a Result", "b>t"),
            ("draft", "waived", "approved PerformanceReportingWaiver<br>.apply_to_reports()", "b>t"),
        ],
        [
            ("note", "<b>sync_performance_report_status()</b> recomputes the status from the entries after each entry "
                     "decision and stops once the report is approved or rejected. Dashed transitions are outcomes of that "
                     "recomputation.<br><br>PIP-bypassed reports cannot be edited or resubmitted; their linked requested "
                     "instances are waived.", 240, 720, 520, 150),
            ("inferred", "Whether a report rejected with REVIEW_REJECTION can be edited and resubmitted (rejected → "
                         "submitted) was not traced; REPORT_LIFECYCLE.md only states that PIP-bypassed reports cannot.",
             820, 720, 460, 110),
        ])
    state_page(
        d, "PerformanceReportEntry", "State machine – PerformanceReportEntry.status",
        "performance/services.py, performance/utils.py (reject_performance_report_entry)",
        {
            "init": ("", 80, 315, "initial"),
            "draft": ("draft", 240, 300, "normal"),
            "submitted": ("submitted", 760, 300, "normal"),
            "approved": ("approved", 1280, 180, "final"),
            "rejected": ("rejected", 1280, 440, "final"),
        },
        [
            ("init", "draft", "entry created"),
            ("draft", "submitted", "report submitted"),
            ("submitted", "approved", "entry action: approve (accepted value recorded) ·<br>report-level approve · override", "t>l"),
            ("submitted", "rejected", "entry action: reject · report rejection · PIP bypass", "b>l"),
        ],
        [("note", "Approving an entry does <b>not</b> publish a Result on its own; Results are created when the whole "
                  "report is finalised. Approval queues recompute_kpi_assignment_progress_task after commit.",
          240, 560, 520, 100)])
    write(d, "state-performance-report.drawio")


def state_requested_instance():
    d = Diagram()
    state_page(
        d, "RequestedReportInstance", "State machine – PerformanceRequestedReportInstance.status",
        "performance/services.py, performance/models.py, performance/views.py (ResolveCurrentRequiredRequestedReportView)",
        {
            "init": ("", 80, 315, "initial"),
            "pending": ("pending", 240, 300, "normal"),
            "on_time": ("submitted_on_time", 820, 120, "final"),
            "late": ("submitted_late", 820, 300, "final"),
            "missed": ("missed", 820, 480, "normal"),
            "waived": ("waived", 1340, 300, "final"),
            "cancelled": ("cancelled", 240, 560, "orphan"),
        },
        [
            ("init", "pending", "generated for a<br>reporting window"),
            ("pending", "on_time", "report submitted,<br>submitted_at ≤ due_at", "t>l"),
            ("pending", "late", "report submitted,<br>submitted_at &gt; due_at"),
            ("pending", "missed", "due_at &lt; now (preliminary type);<br>applied lazily when the employee<br>resolves current required reports", "b+>l"),
            ("pending", "waived", "", "t+>t"),
            ("on_time", "waived", "", "r>l-"),
            ("late", "waived", "approved reporting waiver ·<br>PIP bypass · PIP decision pending"),
            ("missed", "waived", "", "r>l+"),
        ],
        [
            ("note", "An instance can also be <b>created</b> already waived when its report was bypassed earlier "
                     "(waiver inherited). waiver_reason records APPROVED_REPORTING_WAIVER, PIP_BYPASS or "
                     "PIP_DECISION_PENDING.", 820, 640, 460, 110),
            ("inferred", "• No assignment of <b>cancelled</b> was found.<br>• reconcile_suspension_obligations and "
                         "_reconcile_preliminary_requested_report_instance reference pending and waived together; a "
                         "waived → pending reversal after a PIP decision may exist – verify.<br>• Whether a missed "
                         "instance can still become submitted_late was not traced.", 240, 700, 520, 160),
        ])
    write(d, "state-requested-report-instance.drawio")


def state_pip():
    d = Diagram()
    state_page(
        d, "PIP", "State machine – PerformanceImprovementPlan.status",
        "performance/services.py (PIPService, PIPReviewService, PIPLifecycleService), performance/models.py",
        {
            "init": ("", 80, 315, "initial"),
            "scheduled": ("SCHEDULED", 240, 120, "normal"),
            "active": ("ACTIVE", 760, 300, "normal"),
            "final_due": ("FINAL_REVIEW_DUE", 760, 80, "derived"),
            "decision": ("DECISION_PENDING", 1280, 300, "normal"),
            "closed": ("CLOSED", 1280, 600, "final"),
        },
        [
            ("init", "scheduled", "created with start_at in the future", "t>l"),
            ("init", "active", "created with start_at reached<br>(manual, or automated from an attention record)"),
            ("scheduled", "active", "activate_scheduled_pips()<br>hourly KPI processor", "r>l-"),
            ("active", "final_due", "end_at passed and final review not completed", "t>b", True),
            ("active", "decision", "complete_pip_review()<br>on the final review", "r->l-"),
            ("decision", "active", "resolution EXTEND_PIP<br>(new end_at)", "l+>r+"),
            ("decision", "closed", "resolution END_PIP"),
            ("active", "closed", "cancel_performance_improvement_plan()", "b>l"),
        ],
        [
            ("note", "<b>Side effects</b><br>• Creation: linked attention records → actioned, manual concerns → consumed; "
                     "pending reports may be bypassed (rejected with PIP_BYPASS).<br>• DECISION_PENDING suspends ordinary "
                     "reporting obligations.<br>• Close/cancel deactivates PIP-owned KPI configurations and queues "
                     "reconcile_performance_after_pip_resolution.<br>• Cancel: attention records → dismissed, concerns → active.",
             240, 740, 560, 170),
            ("note", "PIP also carries approval_status (BaseApprovableModel). Whether scheduled PIPs can be cancelled the "
                     "same way as active ones is implied by the service but should be verified.", 860, 740, 420, 110),
        ])
    state_page(
        d, "PIPReview", "State machine – PIPReview.status and PIPReviewRequirementAssessment.status",
        "performance/services.py (PIPReviewService), performance/models.py",
        {
            "init": ("", 80, 215, "initial"),
            "scheduled": ("SCHEDULED", 240, 200, "normal"),
            "completed": ("COMPLETED", 820, 120, "final"),
            "cancelled": ("CANCELLED", 820, 300, "final"),
            "init2": ("", 80, 535, "initial"),
            "prepared": ("PREPARED", 240, 520, "normal"),
            "confirmed": ("CONFIRMED", 820, 520, "final"),
        },
        [
            ("init", "scheduled", "created from PIPReviewSchedule /<br>reschedule_pip_reviews()"),
            ("scheduled", "completed", "complete_pip_review()<br>outcome + reason recorded", "t>l"),
            ("scheduled", "cancelled", "cancel_pip_review()", "b>l"),
            ("init2", "prepared", "ensure_due_review_assessments()"),
            ("prepared", "confirmed", "confirm_pip_review_assessment()"),
        ],
        [("note", "Completing the review flagged is_final moves the PIP to DECISION_PENDING. The lower machine is the "
                  "per-requirement assessment inside a review.", 240, 660, 520, 80)])
    write(d, "state-performance-improvement-plan.drawio")


def state_attention():
    d = Diagram()
    state_page(
        d, "AttentionRecord", "State machine – PerformanceAttentionRecord.review_status",
        "performance/services.py (PerformanceAttentionEvaluationService, PIPService), performance/views.py",
        {
            "init": ("", 80, 315, "initial"),
            "pending": ("pending", 240, 300, "normal"),
            "actioned": ("actioned", 820, 160, "final"),
            "dismissed": ("dismissed", 820, 440, "final"),
            "under_review": ("under_review", 240, 560, "orphan"),
            "closed": ("closed", 520, 560, "orphan"),
        },
        [
            ("init", "pending", "signal raised by<br>rule evaluation"),
            ("pending", "actioned", "PIP created from the record<br>(create_active_pip)", "t>l"),
            ("pending", "dismissed", "reviewer dismisses<br>(review note required)", "b>l"),
            ("actioned", "dismissed", "PIP cancelled"),
        ],
        [
            ("note", "Records are created or reused by get_or_create_attention_record() while "
                     "evaluate_kpi_attention_records_task (hourly) and attendance evaluation raise "
                     "PerformanceAttentionSignal rows.", 820, 600, 460, 100),
            ("inferred", "under_review and closed are declared choices. review_attention_record() has a branch for "
                         "closed, but no caller that passes under_review or closed was found.", 240, 700, 480, 100),
        ])
    state_page(
        d, "ManualConcern", "State machine – ManualPerformanceConcern.status",
        "performance/services.py (PIPService)",
        {
            "init": ("", 80, 215, "initial"),
            "active": ("active", 240, 200, "normal"),
            "consumed": ("consumed", 820, 200, "final"),
            "resolved": ("resolved", 240, 420, "orphan"),
        },
        [
            ("init", "active", "concern recorded"),
            ("active", "consumed", "included in a new PIP", "r->l-"),
            ("consumed", "active", "PIP cancelled", "l+>r+"),
        ],
        [("inferred", "No assignment of <b>resolved</b> was found in services, views or serializers.", 520, 420, 420, 70)])
    write(d, "state-attention-record.drawio")


if __name__ == "__main__":
    seq_login()
    seq_partner()
    seq_approval()
    seq_report()
    seq_scheduled_report()
    seq_notifications()
    state_approval_status()
    state_approval_task()
    state_performance_report()
    state_requested_instance()
    state_pip()
    state_attention()
    print("flow diagrams written")
