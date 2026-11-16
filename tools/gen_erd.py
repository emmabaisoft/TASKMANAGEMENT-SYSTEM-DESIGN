#!/usr/bin/env python3
"""Generate every ERD .drawio file from database/schema-snapshot.json.

    python3 tools/gen_erd.py

Outputs
    database/erd-full.drawio        overview (keys only) + framework tables tab
    database/erd-<domain>.drawio    one file per Django app, all columns
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from drawio import DOMAIN_COLOURS, Diagram, Page  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = json.load(open(os.path.join(ROOT, "database", "schema-snapshot.json")))
TABLES = SNAP["tables"]
LOCAL_APPS = SNAP["local_apps"]
GENERIC = SNAP["generic_foreign_keys"]
COMMIT = (SNAP["source"]["commit"] or "unknown")[:8]
SOURCE_LINE = f"Source: Django migrations of the project repo at commit {COMMIT} (PostgreSQL types as Django emits them)"

AUDIT_FK_COLUMNS = {"created_by_id", "updated_by_id"}
ROW_H = 20
HEAD_H = 40
KEY_W = 54
CHAR_W = 6.4

# Table that exists only in a shell script, not in migrations.
PGVECTOR_TABLE = {
    "name": "sql_knowledge1",
    "columns": [
        ("id", "text", False, True), ("name", "text", True, False), ("content", "text", False, False),
        ("embedding", "vector(1536)", False, False), ("meta_data", "jsonb", True, False),
        ("filters", "jsonb", True, False), ("usage", "jsonb", True, False), ("content_hash", "text", True, False),
    ],
}

# ---------------------------------------------------------------------------
# Performance sub-areas (first matching rule wins)
# ---------------------------------------------------------------------------
PERF_AREAS = [
    ("PIP", "Performance improvement plans", r"^(PIP|PerformanceImprovementPlan)"),
    ("Attendance", "Attendance evaluation", r"^Attendance"),
    ("Attention", "Attention records & intervention rules",
     r"^(PerformanceAttention|PerformanceInterventionRule|ManualPerformanceConcern|.*UnderperformanceRuleConfiguration"
     r"|SustainedLowPerformanceRuleConfiguration|PerformanceDeteriorationRuleConfiguration|PerformanceTrackingConfiguration)"),
    ("Free reports", "Free-form reports", r"^FreeReport"),
    ("Appraisal forms", "Appraisal forms & cycles", r"^(AppraisalCycle|AppraisalForm|AppraisalMultiSelectResponse|AppraisalQuestionResponse)"),
    ("Loyalty", "Loyalty points", r"^Loyalty"),
    ("Reports", "Performance reports, requested reports, waivers & work achievements",
     r"^(PerformanceReport|PerformanceReportingWaiver|PerformanceRequestedReport|WorkAchievement|KpiRequestedReportSchedule)"),
    ("Assignments", "Assignments, results & measurements",
     r"^(Assignment|GroupPerformanceMeasurement|ResourcePerformance|Result|JudgmentBasedAssessment|KpiPerformanceBalance"
     r"|KpiAssignmentProgressEvaluation|KpiHourlyScheduleCursor)"),
    ("KPI configuration", "KPIs, assignment configuration, periods & bands",
     r"^(Kpi|AppraisalResourceKpiTargetAmendment|PerformanceConfiguration|PerformanceClassificationBand|PerformancePeriod"
     r"|PerformanceAssessmentSchedule|ResourceKpi)"),
    ("Resources", "Appraisal resources, groups, shifts & work scopes",
     r"^(AppraisableResourceType|AppraisalResource|ResourceMembership|ResourceShift|PerformanceShift|PerformanceGroup"
     r"|PerformanceWorkScope|EmployeeWorkdaySnapshot)"),
]
PERF_ORDER = ["Resources", "KPI configuration", "Assignments", "Reports", "Free reports", "Attention",
              "Attendance", "PIP", "Appraisal forms", "Loyalty"]


def perf_area(model: str) -> str:
    for key, _label, pattern in PERF_AREAS:
        if re.search(pattern, model):
            return key
    raise SystemExit(f"performance model {model} is not assigned to a sub-area")


PERF_LABEL = {k: label for k, label, _ in PERF_AREAS}


def domain_of(table: str) -> str:
    app = TABLES[table]["app"]
    return app if app in LOCAL_APPS else "framework"


def file_of(table: str) -> str:
    d = domain_of(table)
    return "erd-full.drawio (Framework tab)" if d == "framework" else f"erd-{d}.drawio"


def short_type(t: str) -> str:
    return (t.replace("timestamp with time zone", "timestamptz")
             .replace("numeric(", "numeric(").replace(", ", ","))


def pk_column(table: str) -> dict:
    return next(c for c in TABLES[table]["columns"] if c["pk"])


def drawn_fks(table: str):
    """FK columns that get an edge (audit FKs are listed but not drawn)."""
    for c in TABLES[table]["columns"]:
        if "fk" in c and c["name"] not in AUDIT_FK_COLUMNS:
            yield c


def unique_sets(table: str):
    t = TABLES[table]
    by_field = {c["field"]: c["name"] for c in t["columns"]}
    out = []
    for u in t["unique_together"]:
        out.append(("UQ", "(" + ", ".join(by_field.get(f, f) for f in u) + ")"))
    for c in t["constraints"]:
        if c["kind"] == "UniqueConstraint":
            body = "(" + ", ".join(by_field.get(f, f) for f in c["fields"]) + ")" if c["fields"] else c["name"]
            if c["condition"]:
                body += " – partial (conditional)"
            out.append(("UQ", body))
        elif c["kind"] == "CheckConstraint":
            out.append(("CK", c["name"]))
    for i in t["indexes"]:
        out.append(("IX", "(" + ", ".join(by_field.get(f.lstrip("-"), f) for f in i["fields"]) + ")"))
    return out


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------
class TableBox:
    """Pre-computed size and row list of one table (full, keys-only or stub)."""

    def __init__(self, table: str, mode: str):
        self.table = table
        self.mode = mode  # full | keys | stub
        t = TABLES[table]
        generic_fk_fields = {g["fk_field"] for g in GENERIC.get(table, [])}
        self.rows = []  # (id_suffix, key, name, type, is_pk)
        for c in t["columns"]:
            is_fk = "fk" in c
            if mode == "stub" and not c["pk"]:
                continue
            if mode == "keys" and not (c["pk"] or (is_fk and c["name"] not in AUDIT_FK_COLUMNS)):
                continue
            marks = []
            if c["pk"]:
                marks.append("PK")
            if is_fk:
                marks.append("FK")
            if c["field"] in generic_fk_fields:
                marks.append("GFK")
            if c["unique"] and not (is_fk and c["fk"]["one_to_one"] and c["pk"]):
                marks.append("UQ")
            elif c["index"] and not is_fk and not c["pk"]:
                marks.append("IX")
            typ = short_type(c["db_type"]) + (" NULL" if c["null"] else " NOT NULL")
            if c.get("choices"):
                typ += " ⟨enum⟩"
            self.rows.append((c["name"], ",".join(marks), c["name"], typ, c["pk"]))
        self.extra = unique_sets(table) if mode == "full" else []
        name_len = max([len(r[2]) for r in self.rows] + [12])
        type_len = max([len(r[3]) for r in self.rows] + [10])
        self.name_w = math.ceil((name_len * CHAR_W + 14) / 10) * 10
        self.type_w = math.ceil((type_len * CHAR_W + 14) / 10) * 10
        if mode != "full":
            self.type_w = min(self.type_w, 150)
        title_len = max(len(table), len(t["model"]) + 14)
        min_w = math.ceil((title_len * 7.2 + 20) / 10) * 10
        if KEY_W + self.name_w + self.type_w < min_w:
            self.name_w += min_w - (KEY_W + self.name_w + self.type_w)
        self.w = KEY_W + self.name_w + self.type_w
        span = self.name_w + self.type_w
        self.extra_h = [ROW_H * max(1, math.ceil(len(text) * CHAR_W / (span - 10))) for _k, text in self.extra]
        self.h = HEAD_H + ROW_H * len(self.rows) + sum(self.extra_h)

    def draw(self, page: Page, x: float, y: float, parent: str = "1"):
        t = TABLES[self.table]
        domain = domain_of(self.table)
        fill, stroke = DOMAIN_COLOURS[domain]
        prefix = "stub" if self.mode == "stub" else "tbl"
        colp = "stubcol" if self.mode == "stub" else "col"
        tid = f"{prefix}_{self.table}"
        sub = t["model"] + (" · join table" if t["auto_created"] else "")
        if self.mode == "stub":
            sub = f"→ {file_of(self.table)}"
        title = f"{self.table}<br><span style=\"font-weight:normal;font-size:10px\"><i>{sub}</i></span>"
        style = ("shape=table;startSize=%d;container=1;collapsible=1;childLayout=tableLayout;fixedRows=1;"
                 "rowLines=0;fontStyle=1;align=center;resizeLast=1;html=1;whiteSpace=wrap;fontSize=12;"
                 "fillColor=%s;strokeColor=%s;swimlaneFillColor=#ffffff;" % (HEAD_H, fill, stroke))
        if self.mode == "stub":
            style += "dashed=1;dashPattern=6 4;fontColor=#555555;"
        page.vertex(tid, title, style, x, y, self.w, self.h, parent=parent)
        row_style = ("shape=tableRow;horizontal=0;startSize=0;swimlaneHead=0;swimlaneBody=0;fillColor=none;"
                     "collapsible=0;dropTarget=0;points=[[0,0.5],[1,0.5]];portConstraint=eastwest;"
                     "top=0;left=0;right=0;bottom=%d;strokeColor=%s;")
        cell_style = ("shape=partialRectangle;connectable=0;fillColor=none;top=0;left=0;bottom=0;right=0;"
                      "overflow=hidden;html=1;whiteSpace=wrap;fontSize=11;%s")
        cy = HEAD_H
        for col, key, name, typ, is_pk in self.rows:
            rid = f"{colp}_{self.table}_{col}"
            page.vertex(rid, "", row_style % (1 if is_pk else 0, stroke), 0, cy, self.w, ROW_H, parent=tid)
            page.vertex(rid + "__k", key, cell_style % "fontStyle=1;fontSize=9;", 0, 0, KEY_W, ROW_H, parent=rid)
            page.vertex(rid + "__n", name,
                        cell_style % ("align=left;spacingLeft=6;" + ("fontStyle=5;" if is_pk else "")),
                        KEY_W, 0, self.name_w, ROW_H, parent=rid)
            page.vertex(rid + "__t", typ, cell_style % "align=left;spacingLeft=6;fontColor=#555555;",
                        KEY_W + self.name_w, 0, self.type_w, ROW_H, parent=rid)
            cy += ROW_H
        for i, ((kind, text), h) in enumerate(zip(self.extra, self.extra_h)):
            rid = f"con_{self.table}_{i}"
            page.vertex(rid, "", row_style % (0, stroke), 0, cy, self.w, h, parent=tid)
            page.vertex(rid + "__k", kind, cell_style % "fontStyle=1;fontSize=9;fontColor=#7a4a00;", 0, 0, KEY_W, h,
                        parent=rid)
            page.vertex(rid + "__n", text,
                        cell_style % "align=left;spacingLeft=6;fontStyle=2;fontColor=#7a4a00;colspan=2;rowspan=1;",
                        KEY_W, 0, self.name_w + self.type_w, h, parent=rid, alt_width=self.name_w)
            page.vertex(rid + "__t", "", cell_style % "", KEY_W + self.name_w, 0, self.type_w, h, parent=rid,
                        extra_attrs='visible="0"')
            cy += h
        return tid


def draw_edges(page: Page, tables_on_page: set[str], stubs: set[str]):
    for table in sorted(tables_on_page):
        for c in drawn_fks(table):
            target = c["fk"]["to"]
            if target in tables_on_page:
                tgt = f"col_{target}_{pk_column(target)['name']}"
            elif target in stubs:
                tgt = f"stubcol_{target}_{pk_column(target)['name']}"
            else:
                raise SystemExit(f"no target for {table}.{c['name']} -> {target}")
            start = "ERzeroToOne" if c["fk"]["one_to_one"] else "ERzeroToMany"
            end = "ERzeroToOne" if c["null"] else "ERmandOne"
            _fill, stroke = DOMAIN_COLOURS[domain_of(table)]
            style = ("edgeStyle=entityRelationEdgeStyle;html=1;rounded=1;fontSize=10;endFill=0;startFill=0;"
                     f"startArrow={start};endArrow={end};startSize=10;endSize=10;strokeColor={stroke};")
            page.edge(f"fk_{table}_{c['name']}", "", style, source=f"col_{table}_{c['name']}", target=tgt)


def order_tables(tables: list[str]) -> list[str]:
    """Order tables so that FK-related ones end up close to each other."""
    tset = set(tables)
    adj = defaultdict(set)
    for t in tables:
        for c in drawn_fks(t):
            o = c["fk"]["to"]
            if o in tset and o != t:
                adj[t].add(o)
                adj[o].add(t)
    seen, out = set(), []
    for start in sorted(tables, key=lambda t: (-len(adj[t]), t)):
        if start in seen:
            continue
        queue = [start]
        seen.add(start)
        while queue:
            cur = queue.pop(0)
            out.append(cur)
            for nb in sorted(adj[cur] - seen, key=lambda t: (-len(adj[t]), t)):
                seen.add(nb)
                queue.append(nb)
    return out


def column_layout(boxes: list[TableBox], ncols: int, gap_x: int, gap_y: int):
    """Sequentially fill `ncols` columns. Returns ({table: (x, y)}, width, height)."""
    total = sum(b.h + gap_y for b in boxes)
    target = max(total / ncols, max(b.h for b in boxes) + gap_y)
    cols, cur, cur_h = [], [], 0
    for b in boxes:
        if cur and cur_h + b.h > target * 1.08 and len(cols) < ncols - 1:
            cols.append(cur)
            cur, cur_h = [], 0
        cur.append(b)
        cur_h += b.h + gap_y
    if cur:
        cols.append(cur)
    pos, x, height = {}, 0, 0
    for col in cols:
        w = max(b.w for b in col)
        y = 0
        for b in col:
            pos[b.table] = (x, y)
            y += b.h + gap_y
        height = max(height, y - gap_y)
        x += w + gap_x
    return pos, x - gap_x, height


def enum_lines(tables: list[str]) -> list[str]:
    groups = defaultdict(list)
    for t in tables:
        for c in TABLES[t]["columns"]:
            if c.get("choices"):
                groups[" | ".join(c["choices"])].append(f"{t}.{c['name']}")
    lines = []
    for values, cols in sorted(groups.items(), key=lambda kv: kv[1][0]):
        lines.append("<b>" + ", ".join(cols) + "</b>: " + values)
    return lines


def erd_legend(page: Page, x: float, y: float, domains: list[str], keys_only: bool):
    """ERD legend: notation text + crow's-foot samples + domain colours."""
    w = 560
    notation = [
        "<b>PK</b> primary key · <b>FK</b> foreign key · <b>UQ</b> unique · <b>IX</b> indexed (non-FK)",
        "<b>GFK</b> object-id half of a generic (polymorphic) FK – target table varies per row",
        "<b>⟨enum⟩</b> column restricted to choices (listed in the Enums box)",
        "Italic brown rows: composite <b>UQ</b> / <b>CK</b> check / <b>IX</b> index constraints",
        "Dashed grey-titled table = reference stub; full definition is in the file named in it",
        "<b>created_by_id / updated_by_id</b> are FKs to users_customuser on almost every table. "
        "They are listed as FK columns but their lines are NOT drawn.",
    ]
    if keys_only:
        notation.insert(0, "<b>Keys only:</b> this page shows PK and FK columns; see erd-&lt;domain&gt;.drawio for all columns")
    samples = [
        ("ERzeroToMany", "ERmandOne", "many rows → exactly one parent (NOT NULL FK)"),
        ("ERzeroToMany", "ERzeroToOne", "many rows → zero or one parent (nullable FK)"),
        ("ERzeroToOne", "ERmandOne", "one-to-one (unique FK), parent required"),
        ("ERzeroToOne", "ERzeroToOne", "one-to-one (unique FK), parent optional"),
    ]
    text_h = 20 * len(notation) + 24
    h = 34 + text_h + 24 * len(samples) + 14 + 24 * math.ceil(len(domains) / 3) + 16
    page.vertex("legend", "<b>Legend</b>",
                "rounded=0;whiteSpace=wrap;html=1;verticalAlign=top;align=left;spacingLeft=8;fillColor=#ffffff;"
                "strokeColor=#999999;container=1;collapsible=0;", x, y, w, h)
    page.text("legend_notation", "<br>".join(notation), 8, 26, w - 16, text_h, "fontSize=11;", parent="legend")
    cy = 30 + text_h
    for i, (start, end, label) in enumerate(samples):
        page.edge(f"legend_edge_{i}", "",
                  f"html=1;endFill=0;startFill=0;startArrow={start};endArrow={end};startSize=10;endSize=10;"
                  "strokeColor=#333333;", parent="legend",
                  source_point=(16, cy + 10), target_point=(126, cy + 10))
        page.text(f"legend_edge_tx_{i}", label, 140, cy, w - 150, 20, "fontSize=11;", parent="legend")
        cy += 24
    cy += 8
    for i, d in enumerate(domains):
        fill, stroke = DOMAIN_COLOURS[d]
        cx = 12 + (i % 3) * 180
        ry = cy + (i // 3) * 24
        page.vertex(f"legend_dom_{d}", d, f"rounded=1;html=1;fontSize=11;fillColor={fill};strokeColor={stroke};",
                    cx, ry, 160, 18, parent="legend")
    return w, h


def build_page(page: Page, title: str, tables: list[str], mode: str = "full", groups=None):
    """groups: optional list of (group_id, label, domain, [tables]) drawn as coloured containers."""
    tset = set(tables)
    stub_names = sorted({c["fk"]["to"] for t in tables for c in drawn_fks(t)} - tset)
    page.title(title, SOURCE_LINE, w=1000)
    domains = sorted({domain_of(t) for t in tables} | {domain_of(t) for t in stub_names},
                     key=lambda d: (LOCAL_APPS + ["framework"]).index(d))
    _lw, lh = erd_legend(page, 1100, 20, domains, mode == "keys")
    top = 20 + lh + 50
    left = 40

    # reference stubs: one column on the far left
    stubs = [TableBox(t, "stub") for t in stub_names]
    stub_w = 0
    if stubs:
        page.text("stub_heading", "<b>Referenced tables defined elsewhere</b>", left, top - 30, 320, 24, "fontSize=12;")
        sy = top
        for b in stubs:
            b.draw(page, left, sy)
            sy += b.h + 30
        stub_w = max(b.w for b in stubs) + 200
    x0 = left + stub_w
    bottom = top

    if groups is None:
        boxes = [TableBox(t, mode) for t in order_tables(tables)]
        ncols = max(2, min(8, round(math.sqrt(len(boxes) * 0.9))))
        pos, _w, h = column_layout(boxes, ncols, 160, 50)
        for b in boxes:
            px, py = pos[b.table]
            b.draw(page, x0 + px, top + py)
        bottom = top + h
    else:
        # shelf-pack coloured domain containers
        pad, head = 30, 44
        laid = []
        for gid, label, domain, gtables in groups:
            boxes = [TableBox(t, mode) for t in order_tables(gtables)]
            ncols = max(1, min(7, round(math.sqrt(len(boxes) * 1.1))))
            pos, w, h = column_layout(boxes, ncols, 110, 36)
            laid.append((gid, label, domain, boxes, pos, w + 2 * pad, h + head + pad))
        max_row_w = 9000
        gx, gy, row_h = x0, top, 0
        for gid, label, domain, boxes, pos, w, h in laid:
            if gx > x0 and gx + w > x0 + max_row_w:
                gx, gy, row_h = x0, gy + row_h + 90, 0
            fill, stroke = DOMAIN_COLOURS[domain]
            page.vertex(gid, f"<b>{label}</b>",
                        "rounded=1;arcSize=2;whiteSpace=wrap;html=1;verticalAlign=top;align=left;spacingLeft=12;"
                        f"spacingTop=6;fontSize=18;container=1;collapsible=0;fillColor={fill};strokeColor={stroke};"
                        "opacity=45;dashed=0;", gx, gy, w, h)
            for b in boxes:
                px, py = pos[b.table]
                b.draw(page, pad + px, head + py, parent=gid)
            gx += w + 140
            row_h = max(row_h, h)
        bottom = gy + row_h

    draw_edges(page, tset, set(stub_names))

    lines = enum_lines(tables) if mode == "full" else []
    if lines:
        est = sum(max(1, math.ceil(len(re.sub(r"<[^>]+>", "", ln)) / 190)) for ln in lines)
        page.vertex("enums", "<b>Enums (Django choices – enforced in application code, stored as plain columns)</b><br>"
                    + "<br>".join(lines),
                    "rounded=0;whiteSpace=wrap;html=1;align=left;verticalAlign=top;spacing=10;fontSize=11;"
                    "fillColor=#fffde7;strokeColor=#bfa900;", x0, bottom + 80, 1300, 40 + 17 * est)
    return x0, bottom + (120 + 17 * 0 if not lines else 160 + 17 * est)


def main():
    out_dir = os.path.join(ROOT, "database")
    by_domain = defaultdict(list)
    for t in sorted(TABLES):
        by_domain[domain_of(t)].append(t)
    perf_by_area = defaultdict(list)
    for t in by_domain["performance"]:
        perf_by_area[perf_area(TABLES[t]["model"])].append(t)

    # ---- per-domain files --------------------------------------------------
    for domain in LOCAL_APPS:
        d = Diagram()
        if domain == "performance":
            for area in PERF_ORDER:
                build_page(d.page(area), f"ERD – performance / {PERF_LABEL[area]}", perf_by_area[area])
        else:
            build_page(d.page(domain), f"ERD – {domain}", by_domain[domain])
        d.write(os.path.join(out_dir, f"erd-{domain}.drawio"))

    # ---- full overview -----------------------------------------------------
    d = Diagram()
    groups = []
    for domain in LOCAL_APPS:
        if domain == "performance":
            for area in PERF_ORDER:
                groups.append((f"grp_performance_{area.lower().replace(' ', '_')}",
                               f"performance · {PERF_LABEL[area]}", "performance", perf_by_area[area]))
        else:
            groups.append((f"grp_{domain}", domain, domain, by_domain[domain]))
    app_tables = [t for dom in LOCAL_APPS for t in by_domain[dom]]
    build_page(d.page("Overview (keys only)"), "ERD – full overview, all application tables (keys only)",
               app_tables, mode="keys", groups=groups)

    fw = d.page("Framework tables")
    fx, fbottom = build_page(fw, "ERD – Django / third-party framework tables (keys only)", by_domain["framework"],
                             mode="keys")
    # pgvector table that lives outside migrations
    cols = PGVECTOR_TABLE["columns"]
    name = PGVECTOR_TABLE["name"]
    w, y0, x = 330, fbottom, fx
    fw.vertex(f"tbl_{name}", f"{name}<br><span style=\"font-weight:normal;font-size:10px\"><i>pgvector knowledge table</i></span>",
              "shape=table;startSize=40;container=1;collapsible=1;childLayout=tableLayout;fixedRows=1;rowLines=0;"
              "fontStyle=1;align=center;resizeLast=1;html=1;whiteSpace=wrap;fontSize=12;fillColor=#ffffff;"
              "strokeColor=#cc0000;dashed=1;swimlaneFillColor=#ffffff;", x, y0, w, 40 + 20 * len(cols))
    for i, (cname, ctype, null, pk) in enumerate(cols):
        rid = f"col_{name}_{cname}"
        fw.vertex(rid, "", "shape=tableRow;horizontal=0;startSize=0;swimlaneHead=0;swimlaneBody=0;fillColor=none;"
                  "collapsible=0;dropTarget=0;points=[[0,0.5],[1,0.5]];portConstraint=eastwest;top=0;left=0;right=0;"
                  f"bottom={1 if pk else 0};strokeColor=#cc0000;", 0, 40 + 20 * i, w, 20, parent=f"tbl_{name}")
        cs = ("shape=partialRectangle;connectable=0;fillColor=none;top=0;left=0;bottom=0;right=0;overflow=hidden;"
              "html=1;whiteSpace=wrap;fontSize=11;")
        fw.vertex(rid + "__k", "PK" if pk else "", cs + "fontStyle=1;fontSize=9;", 0, 0, 54, 20, parent=rid)
        fw.vertex(rid + "__n", cname, cs + "align=left;spacingLeft=6;", 54, 0, 130, 20, parent=rid)
        fw.vertex(rid + "__t", ctype + (" NULL" if null else " NOT NULL"), cs + "align=left;spacingLeft=6;fontColor=#555555;",
                  184, 0, 146, 20, parent=rid)
    fw.inferred("inferred_pgvector",
                "This table is NOT in any migration. It is created by <i>backend/setup_pgvector.sh</i> "
                "(default name from the script) and filled by the <i>load_schema_embeddings</i> management command. "
                "Whether it exists in a given environment must be checked.", x + w + 30, y0, 330, 120)
    d.write(os.path.join(out_dir, "erd-full.drawio"))
    print("ERD files written to", out_dir)


if __name__ == "__main__":
    main()
