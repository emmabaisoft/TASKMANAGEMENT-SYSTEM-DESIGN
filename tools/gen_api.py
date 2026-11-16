#!/usr/bin/env python3
"""Generate api/api-overview.drawio from api/api-snapshot.json.

    python3 tools/gen_api.py
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from drawio import DOMAIN_COLOURS, Diagram  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = json.load(open(os.path.join(ROOT, "database", "schema-snapshot.json")))
API = json.load(open(os.path.join(ROOT, "api", "api-snapshot.json")))
COMMIT = (SNAP["source"]["commit"] or "unknown")[:8]
SRC = f"Derived from the URL resolver of the project repo at commit {COMMIT} (tools/extract_api.py)"

SEGMENT_APP = {"user": "users", "calendar": "calendar2"}
METHOD_COLOUR = {"GET": "#2e7d32", "POST": "#1565c0", "PATCH": "#e65100", "PUT": "#e65100", "DELETE": "#c62828"}
# checks that live outside the view source and were confirmed by reading the code
MANUAL_AUTH = {
    "/api/institution/ownership-transfer/": ("partner", "AllowAny · API key required by serializer"),
}
COLS = [("Method", 120), ("Path (relative to the app prefix)", 400), ("Authentication", 190),
        ("Permission codes", 360), ("Main tables referenced", 400)]
WIDTH = sum(w for _n, w in COLS)
AUTH_FILL = {"auth": "#ffffff", "public": "#f8cecc", "partner": "#e6e6e6"}


def app_of(route):
    seg = route["path"].split("/")[2]
    return SEGMENT_APP.get(seg, seg)


def auth_of(route):
    if route["path"] in MANUAL_AUTH:
        return MANUAL_AUTH[route["path"]]
    public = "AllowAny" in route["permission_classes"]
    if route["partner_key_in_handler"] and public:
        return "partner", "AllowAny · API key checked in view"
    if public:
        return "public", "Public (AllowAny)"
    if route["partner_key_in_handler"]:
        return "partner", "JWT or API key · system-aware"
    return "auth", "JWT or partner API key"


def perm_of(route):
    mp = route["method_permissions"]
    if mp:
        parts = []
        for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            if method in mp:
                v = mp[method]
                v = "—" if v is None else (" | ".join(v) if isinstance(v, list) else v)
                parts.append(f"{method}: {v}")
        return "<br>".join(parts), len(parts)
    codes = route["permission_codes"]
    if codes:
        shown = codes[:4] + ([f"+{len(codes) - 4} more"] if len(codes) > 4 else [])
        return "in handler: " + ", ".join(shown), 1
    if route["inline_permission_check"]:
        return "in handler (code not literal)", 1
    return "<span style=\"color:#999999\">none found in view</span>", 1


def tables_of(route):
    t = route["tables"]
    if not t:
        return "<span style=\"color:#999999\">via serializer / service</span>"
    return ", ".join(t[:5]) + (f" +{len(t) - 5}" if len(t) > 5 else "")


def plain_len(html):
    return len(re.sub(r"<[^>]+>", "", html))


def main():
    routes = [r for r in API["routes"] if r["path"].startswith("/api/") and r.get("drf")
              and r["path"].split("/")[2] not in ("schema", "docs")]
    by_app = defaultdict(list)
    for r in routes:
        by_app[app_of(r)].append(r)

    d = Diagram()

    # ---- index page --------------------------------------------------------
    p = d.page("Index")
    p.title("API map – overview", SRC, w=1100)
    p.legend([(("#ffffff", "#999999"), "Authenticated: JWT (user) or X-API-Key (partner system)"),
              (("#e6e6e6", "#666666"), "Partner-system endpoint (API key enforced in view/serializer)"),
              (("#f8cecc", "#b85450"), "Public (AllowAny, no key check found in view)"),
              ("note", "Note"), ("inferred", "Inferred – verify")], 1240, 20, w=420)
    head = ["App / URL prefix", "Routes", "Public", "Partner", "MethodPermissionMixin", "Check in handler", "No check found in view"]
    widths = [300, 90, 90, 90, 190, 160, 200]
    x0, y0, rh = 40, 240, 30
    x = x0
    for h, w in zip(head, widths):
        p.vertex(f"ix_h_{head.index(h)}", f"<b>{h}</b>", "rounded=0;html=1;whiteSpace=wrap;fontSize=11;fillColor=#333333;"
                 "fontColor=#ffffff;strokeColor=#333333;", x, y0, w, rh)
        x += w
    order = [a for a in SNAP["local_apps"] if a in by_app]
    totals = [0] * 6
    for i, app in enumerate(order + ["TOTAL"]):
        if app == "TOTAL":
            vals, label, fill, stroke = totals, "<b>Total</b>", "#eeeeee", "#999999"
        else:
            rs = by_app[app]
            kinds = [auth_of(r)[0] for r in rs]
            mp = sum(1 for r in rs if r["method_permissions"])
            inline = sum(1 for r in rs if not r["method_permissions"] and (r["permission_codes"] or r["inline_permission_check"]))
            none = sum(1 for r, k in zip(rs, kinds) if k == "auth" and not r["method_permissions"]
                       and not r["permission_codes"] and not r["inline_permission_check"])
            vals = [len(rs), kinds.count("public"), kinds.count("partner"), mp, inline, none]
            totals = [a + b for a, b in zip(totals, vals)]
            seg = {v: k for k, v in SEGMENT_APP.items()}.get(app, app)
            label = f"<b>{app}</b> · /api/{seg}/"
            fill, stroke = DOMAIN_COLOURS[app]
        y = y0 + rh * (i + 1)
        x = x0
        for j, (v, w) in enumerate(zip([label] + [str(v) for v in vals], widths)):
            p.vertex(f"ix_{app}_{j}", v, f"rounded=0;html=1;whiteSpace=wrap;fontSize=11;fillColor={fill if j == 0 else '#ffffff'};"
                     f"strokeColor={stroke if j == 0 else '#cccccc'};" + ("align=left;spacingLeft=8;" if j == 0 else ""),
                     x, y, w, rh)
            x += w
    ny = y0 + rh * (len(order) + 3)
    p.note("ix_note_other",
           "<b>Routes outside /api/&lt;app&gt;/</b><br>"
           "• /admin/ – Django admin (session login, staff only)<br>"
           "• /metrics – Prometheus metrics (django-prometheus), no authentication in code<br>"
           "• / and /login – institution.views.home<br>"
           "• /api/schema/, /api/docs/ – OpenAPI + Swagger UI, only when DEBUG is on<br>"
           "• /media/&lt;path&gt; – uploaded files, served by Django only when DEBUG is on<br><br>"
           "<b>Headers</b><br>Authorization: Bearer &lt;access token&gt; · X-Resource-UUID (required for almost all "
           "/api/performance routes) · X-API-Key, X-External-User-UUID, X-Internal-User-UUID (partner systems).",
           40, ny, 620, 230)
    p.inferred("ix_inferred",
               "• <b>Permission codes</b> are read from each view class (method_permissions or literal “can_…” strings). "
               "Checks made inside serializers or services are not visible here, so “none found in view” means "
               "<i>verify</i>, not <i>unprotected</i>.<br>"
               "• <b>Main tables</b> are the models named in the view (and the serializers it names). It is a static "
               "reading, not a trace of executed queries.<br>"
               "• Every authenticated route is additionally tenant-scoped through request.institution.",
               700, ny, 620, 200)

    # ---- one page per app ------------------------------------------------------
    for app in order:
        seg = {v: k for k, v in SEGMENT_APP.items()}.get(app, app)
        prefix = f"/api/{seg}/"
        fill, stroke = DOMAIN_COLOURS[app]
        p = d.page(app)
        p.title(f"API map – {app} ({prefix})", SRC, w=1100)
        p.legend([(("#ffffff", "#999999"), "Authenticated: JWT or partner API key"),
                  (("#e6e6e6", "#666666"), "Partner-system endpoint"),
                  (("#f8cecc", "#b85450"), "Public (AllowAny)"),
                  ((fill, stroke), "Resource group")], 1240, 20, w=320)
        groups = defaultdict(list)
        for r in by_app[app]:
            rel = r["path"][len(prefix):] if r["path"].startswith(prefix) else r["path"]
            first = rel.split("/")[0] if rel and not rel.startswith("<") else "(root)"
            groups[first].append((rel or "(root)", r))
        # build row list
        rows = []
        for gname in sorted(groups):
            rows.append(("group", gname, None))
            for rel, r in sorted(groups[gname], key=lambda it: it[0]):
                rows.append(("route", rel, r))
        # split into column blocks
        block_limit = 2400
        bx, by, top = 40, 0, 220
        block = 0

        def header(bx_, top_, block_):
            x_ = bx_
            for j, (name, w) in enumerate(COLS):
                p.vertex(f"h_{block_}_{j}", f"<b>{name}</b>", "rounded=0;html=1;whiteSpace=wrap;fontSize=11;"
                         "fillColor=#333333;fontColor=#ffffff;strokeColor=#333333;", x_, top_, w, 28)
                x_ += w

        header(bx, top, block)
        y = top + 28
        for i, (kind, name, r) in enumerate(rows):
            if kind == "group":
                if y - top > block_limit:
                    block += 1
                    bx += WIDTH + 80
                    header(bx, top, block)
                    y = top + 28
                p.vertex(f"g_{i}", f"<b>{name}</b>", f"rounded=0;html=1;whiteSpace=wrap;fontSize=11;align=left;spacingLeft=8;"
                         f"fillColor={fill};strokeColor={stroke};", bx, y, WIDTH, 24)
                y += 24
                continue
            akind, atext = auth_of(r)
            ptext, plines = perm_of(r)
            methods = " ".join(f"<b style=\"color:{METHOD_COLOUR.get(m, '#333333')}\">{m}</b>" for m in r["methods"])
            cells = [methods, name.replace("<", "&lt;").replace(">", "&gt;"), atext, ptext, tables_of(r)]
            lines = 1
            for (cname, w), text in zip(COLS, cells):
                per_line = max(8, int((w - 12) / 5.6))
                n = plines if cname == "Permission codes" and plines > 1 else math.ceil(max(1, plain_len(text)) / per_line)
                if cname == "Permission codes" and plines > 1:
                    n = sum(math.ceil(max(1, plain_len(part)) / per_line) for part in text.split("<br>"))
                lines = max(lines, n)
            h = max(24, 13 * lines + 8)
            x = bx
            for j, ((cname, w), text) in enumerate(zip(COLS, cells)):
                cell_fill = AUTH_FILL[akind] if j == 2 else "#ffffff"
                p.vertex(f"r_{i}_{j}", text, "rounded=0;html=1;whiteSpace=wrap;fontSize=10;align=left;spacingLeft=6;"
                         f"verticalAlign=middle;fillColor={cell_fill};strokeColor=#cccccc;", x, y, w, h)
                x += w
            y += h
    d.write(os.path.join(ROOT, "api", "api-overview.drawio"))
    print(f"api map written: {len(routes)} routes on {len(order)} app pages")


if __name__ == "__main__":
    main()
