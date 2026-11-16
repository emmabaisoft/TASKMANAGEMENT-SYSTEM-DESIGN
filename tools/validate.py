#!/usr/bin/env python3
"""Validate every .drawio file in this repo.

    python3 tools/validate.py

Checks
  1. XML is well-formed and has the mxfile > diagram > mxGraphModel > root shape,
     with cells "0" and "1", unique ids, valid parents and valid edge endpoints.
  2. No two sibling shapes overlap (same parent, both visible).
  3. ERD <-> schema-snapshot.json: every table, column and drawn FK of the
     snapshot is present, and nothing is drawn that the snapshot does not have
     (apart from the explicitly "Inferred" pgvector table).
"""
from __future__ import annotations

import glob
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT_FK_COLUMNS = {"created_by_id", "updated_by_id"}
INFERRED_TABLES = {"sql_knowledge1"}
errors: list[str] = []
warnings: list[str] = []


def err(msg):
    errors.append(msg)


def check_file(path):
    rel = os.path.relpath(path, ROOT)
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        err(f"{rel}: not well-formed XML: {exc}")
        return []
    if root.tag != "mxfile":
        err(f"{rel}: root element is {root.tag}, expected mxfile")
    pages = []
    for diagram in root.findall("diagram"):
        name = diagram.get("name")
        model = diagram.find("mxGraphModel")
        if model is None or model.find("root") is None:
            err(f"{rel}[{name}]: missing mxGraphModel/root (compressed diagram?)")
            continue
        cells = model.find("root").findall("mxCell")
        ids = defaultdict(int)
        for c in cells:
            ids[c.get("id")] += 1
        for cid, n in ids.items():
            if n > 1:
                err(f"{rel}[{name}]: duplicate id {cid}")
        if "0" not in ids or "1" not in ids:
            err(f"{rel}[{name}]: cells 0/1 missing")
        by_id = {c.get("id"): c for c in cells}
        if by_id.get("1") is not None and by_id["1"].get("parent") != "0":
            err(f"{rel}[{name}]: cell 1 must have parent 0")
        for c in cells:
            cid = c.get("id")
            if cid == "0":
                continue
            if c.get("parent") not in by_id:
                err(f"{rel}[{name}]: {cid} has unknown parent {c.get('parent')}")
            if c.get("edge") == "1":
                for end in ("source", "target"):
                    ref = c.get(end)
                    if ref is not None and ref not in by_id:
                        err(f"{rel}[{name}]: edge {cid} {end} {ref} does not exist")
                if c.get("source") is None or c.get("target") is None:
                    geo = c.find("mxGeometry")
                    pts = {p.get("as") for p in geo.findall("mxPoint")} if geo is not None else set()
                    if c.get("source") is None and "sourcePoint" not in pts:
                        err(f"{rel}[{name}]: edge {cid} has no source")
                    if c.get("target") is None and "targetPoint" not in pts:
                        err(f"{rel}[{name}]: edge {cid} has no target")
        # sibling overlap
        siblings = defaultdict(list)
        for c in cells:
            if c.get("vertex") != "1" or c.get("visible") == "0":
                continue
            style = c.get("style") or ""
            if "edgeLabel" in style or "allowOverlap=1" in style:
                continue
            g = c.find("mxGeometry")
            if g is None or g.get("relative") == "1":
                continue
            box = (float(g.get("x") or 0), float(g.get("y") or 0), float(g.get("width") or 0), float(g.get("height") or 0))
            siblings[c.get("parent")].append((c.get("id"), box))
        for parent, items in siblings.items():
            items.sort(key=lambda it: it[1][0])
            for i, (ida, a) in enumerate(items):
                for idb, b in items[i + 1:]:
                    if b[0] >= a[0] + a[2] - 0.5:
                        break
                    if a[1] < b[1] + b[3] - 0.5 and b[1] < a[1] + a[3] - 0.5:
                        err(f"{rel}[{name}]: shapes overlap: {ida} / {idb}")
        text = " ".join((c.get("value") or "") for c in cells)
        if "Last generated" not in text:
            err(f"{rel}[{name}]: no 'Last generated' date")
        if by_id.get("title") is None:
            err(f"{rel}[{name}]: no title cell")
        pages.append((rel, name, by_id))
    if not pages:
        err(f"{rel}: no pages")
    return pages


def check_erd(all_pages):
    snap = json.load(open(os.path.join(ROOT, "database", "schema-snapshot.json")))
    tables, local = snap["tables"], set(snap["local_apps"])
    full_cols = defaultdict(set)      # table -> columns seen on a full-detail page
    overview_tables = set()
    drawn_edges = set()
    for rel, name, by_id in all_pages:
        if not rel.startswith("database/"):
            continue
        keys_only = rel.endswith("erd-full.drawio")
        for cid, c in by_id.items():
            if cid.startswith("tbl_"):
                t = cid[4:]
                if t not in tables and t not in INFERRED_TABLES:
                    err(f"{rel}[{name}]: table {t} is drawn but not in the schema snapshot")
                if keys_only:
                    overview_tables.add(t)
                else:
                    full_cols[t]  # touch
            elif cid.startswith("col_") and not cid.endswith(("__k", "__n", "__t")):
                parent = c.get("parent")
                t = parent[4:]
                col = cid[len("col_" + t + "_"):]
                if t in INFERRED_TABLES:
                    continue
                known = {x["name"] for x in tables.get(t, {"columns": []})["columns"]}
                if col not in known:
                    err(f"{rel}[{name}]: column {t}.{col} is drawn but not in the schema snapshot")
                if not keys_only:
                    full_cols[t].add(col)
            elif cid.startswith("fk_"):
                src = c.get("source")
                row = by_id[src]
                t = row.get("parent")[4:]
                col = src[len("col_" + t + "_"):]
                tgt_table = by_id[c.get("target")].get("parent").split("_", 1)[1]
                spec = next((x for x in tables[t]["columns"] if x["name"] == col), None)
                if not spec or "fk" not in spec or spec["fk"]["to"] != tgt_table:
                    err(f"{rel}[{name}]: edge {cid} does not match a FK in the snapshot")
                else:
                    style = c.get("style")
                    want_start = "ERzeroToOne" if spec["fk"]["one_to_one"] else "ERzeroToMany"
                    want_end = "ERzeroToOne" if spec["null"] else "ERmandOne"
                    if f"startArrow={want_start};" not in style or f"endArrow={want_end};" not in style:
                        err(f"{rel}[{name}]: edge {cid} has wrong cardinality markers")
                    if not keys_only:
                        drawn_edges.add((t, col))
    for t, spec in tables.items():
        is_local = spec["app"] in local
        if t not in overview_tables:
            err(f"table {t} missing from erd-full.drawio")
        if not is_local:
            continue
        if t not in full_cols:
            err(f"table {t} missing from the per-domain ERDs")
            continue
        missing = {c["name"] for c in spec["columns"]} - full_cols[t]
        if missing:
            err(f"table {t}: columns missing from per-domain ERD: {sorted(missing)}")
        for c in spec["columns"]:
            if "fk" in c and c["name"] not in AUDIT_FK_COLUMNS and (t, c["name"]) not in drawn_edges:
                err(f"FK {t}.{c['name']} -> {c['fk']['to']} has no edge in the per-domain ERDs")
    n_fk = sum(1 for s in tables.values() if s["app"] in local for c in s["columns"]
               if "fk" in c and c["name"] not in AUDIT_FK_COLUMNS)
    print(f"ERD cross-check: {len(tables)} tables in snapshot, "
          f"{sum(1 for s in tables.values() if s['app'] in local)} application tables with all columns, "
          f"{n_fk} non-audit FKs drawn")
    for d in snap.get("drift_migrations_vs_models", []):
        warnings.append(f"migrations vs models drift: {d}")


def main():
    files = sorted(glob.glob(os.path.join(ROOT, "**", "*.drawio"), recursive=True))
    pages = []
    for f in files:
        pages.extend(check_file(f))
    check_erd(pages)
    print(f"{len(files)} files, {len(pages)} pages checked")
    for w in warnings:
        print("WARNING:", w)
    for e in errors[:80]:
        print("ERROR:", e)
    if errors:
        print(f"{len(errors)} error(s)")
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
