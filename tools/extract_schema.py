#!/usr/bin/env python
"""Read-only schema extractor.

Loads every Django migration file of the PROJECT REPO into an in-memory
project state (no database connection is opened, nothing is written to the
project) and dumps tables / columns / keys / constraints as JSON.

Usage (run with the project's own interpreter, from OUTSIDE the project repo):

    PYTHONDONTWRITEBYTECODE=1 <project>/backend/.venv/bin/python \
        tools/extract_schema.py <project>/backend database/schema-snapshot.json
"""
import json
import os
import subprocess
import sys

BACKEND, OUT = sys.argv[1], sys.argv[2]
sys.dont_write_bytecode = True
sys.path.insert(0, BACKEND)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django  # noqa: E402

django.setup()

from django.apps import apps as live_apps  # noqa: E402
from django.contrib.contenttypes.fields import GenericForeignKey  # noqa: E402
from django.db import connection  # noqa: E402
from django.db.migrations.loader import MigrationLoader  # noqa: E402

LOCAL_APPS = [
    "users", "institution", "projects", "tasks", "performance", "approval",
    "calendar2", "communication", "reports", "settings", "audit", "system",
]


def db_type(field):
    try:
        t = field.db_type(connection)
    except Exception:  # pragma: no cover - fallback only
        t = None
    return t or field.get_internal_type()


def describe(registry):
    out = {}
    for model in registry.get_models(include_auto_created=True):
        meta = model._meta
        if meta.proxy:
            continue
        cols = []
        for f in meta.local_fields:
            col = {
                "name": f.column,
                "field": f.name,
                "django_type": f.get_internal_type(),
                "db_type": db_type(f),
                "null": bool(f.null),
                "pk": bool(f.primary_key),
                "unique": bool(f.unique) and not f.primary_key,
                "index": bool(f.db_index),
            }
            if f.choices:
                col["choices"] = [str(c[0]) for c in f.flatchoices]
            if f.is_relation and f.remote_field is not None:
                rm = f.remote_field.model
                col["fk"] = {
                    "to": rm._meta.db_table,
                    "to_app": rm._meta.app_label,
                    "to_model": rm.__name__,
                    "to_column": f.target_field.column,
                    "one_to_one": bool(f.one_to_one),
                    "on_delete": getattr(f.remote_field.on_delete, "__name__", "?"),
                }
            cols.append(col)
        constraints = []
        for c in meta.constraints:
            kind = type(c).__name__
            constraints.append({
                "name": c.name,
                "kind": kind,
                "fields": list(getattr(c, "fields", None) or []),
                "condition": str(getattr(c, "condition", None))
                if getattr(c, "condition", None) is not None else None,
            })
        out[meta.db_table] = {
            "app": meta.app_label,
            "model": model.__name__,
            "auto_created": bool(meta.auto_created),
            "columns": cols,
            "unique_together": [list(u) for u in meta.unique_together],
            "constraints": constraints,
            "indexes": [{"name": i.name, "fields": list(i.fields)} for i in meta.indexes],
            "m2m": [
                {
                    "field": f.name,
                    "through": f.remote_field.through._meta.db_table,
                    "to": f.remote_field.model._meta.db_table,
                }
                for f in meta.local_many_to_many
            ],
        }
    return out


loader = MigrationLoader(None, ignore_no_migrations=True)
from_migrations = describe(loader.project_state().apps)
from_models = describe(live_apps)

# Generic foreign keys only exist on the live model classes.
generic = {}
for model in live_apps.get_models():
    for pf in model._meta.private_fields:
        if isinstance(pf, GenericForeignKey):
            generic.setdefault(model._meta.db_table, []).append(
                {"name": pf.name, "ct_field": pf.ct_field, "fk_field": pf.fk_field}
            )

drift = []
for table in sorted(set(from_migrations) | set(from_models)):
    a = from_migrations.get(table)
    b = from_models.get(table)
    if a is None or b is None:
        drift.append({"table": table, "issue": "only in " + ("models" if a is None else "migrations")})
        continue
    ca = {c["name"]: (c["db_type"], c["null"], (c.get("fk") or {}).get("to")) for c in a["columns"]}
    cb = {c["name"]: (c["db_type"], c["null"], (c.get("fk") or {}).get("to")) for c in b["columns"]}
    for name in sorted(set(ca) | set(cb)):
        if ca.get(name) != cb.get(name):
            drift.append({"table": table, "column": name, "migrations": ca.get(name), "models": cb.get(name)})


def git(*args):
    try:
        return subprocess.check_output(["git", "-C", BACKEND, *args], text=True).strip()
    except Exception:
        return None


json.dump(
    {
        "source": {
            "kind": "django migrations (in-memory project state)",
            "commit": git("rev-parse", "HEAD"),
            "db_vendor": connection.vendor,
            "migration_leaf_nodes": sorted(list(k) for k in loader.graph.leaf_nodes()),
        },
        "local_apps": LOCAL_APPS,
        "tables": from_migrations,
        "generic_foreign_keys": generic,
        "drift_migrations_vs_models": drift,
    },
    open(OUT, "w"),
    indent=1,
    sort_keys=True,
)
print(f"{len(from_migrations)} tables written to {OUT}; drift entries: {len(drift)}")
for d in drift:
    print("  drift:", d)
