#!/usr/bin/env python
"""Read-only API extractor: walks the Django URL resolver of the PROJECT REPO.

    PYTHONDONTWRITEBYTECODE=1 <project>/backend/.venv/bin/python \
        tools/extract_api.py <project>/backend api/api-snapshot.json

For every route it records the view, the HTTP methods the view implements, the
DRF authentication/permission classes, permission codes found in the view
source, and the models the view (or the serializers it names) references.
The model list is a static heuristic, not a trace of executed queries.
"""
import inspect
import json
import os
import re
import sys

BACKEND, OUT = sys.argv[1], sys.argv[2]
sys.dont_write_bytecode = True
sys.path.insert(0, BACKEND)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django  # noqa: E402

django.setup()

from django.apps import apps  # noqa: E402
from django.urls import URLPattern, URLResolver, get_resolver  # noqa: E402
from rest_framework.settings import api_settings  # noqa: E402

MODELS = {m.__name__: m._meta.db_table for m in apps.get_models()}
HTTP = ["get", "post", "put", "patch", "delete"]
PERM_RE = re.compile(r"[\"'](can_[a-z0-9_]+)[\"']")
WORD_RE = re.compile(r"\b[A-Z][A-Za-z0-9]+\b")


def source_of(obj):
    try:
        return inspect.getsource(obj)
    except Exception:
        return ""


def models_in(src, module, depth=1):
    """Models the view source names, limited to names bound in the view's module."""
    found = set()
    for word in set(WORD_RE.findall(src)):
        bound = getattr(module, word, None) if module is not None else None
        if not inspect.isclass(bound):
            continue
        if word in MODELS and getattr(getattr(bound, "_meta", None), "db_table", None) == MODELS[word]:
            found.add(word)
        elif depth and bound.__name__.endswith("Serializer"):
            model = getattr(getattr(bound, "Meta", None), "model", None)
            if model is not None and model.__name__ in MODELS:
                found.add(model.__name__)
    return found


def walk(patterns, prefix=""):
    for p in patterns:
        route = prefix + str(p.pattern)
        if isinstance(p, URLResolver):
            yield from walk(p.url_patterns, route)
        elif isinstance(p, URLPattern):
            yield route, p


routes = []
for route, p in walk(get_resolver().url_patterns):
    cb = p.callback
    cls = getattr(cb, "view_class", None) or getattr(cb, "cls", None)
    entry = {"path": "/" + route.lstrip("^").rstrip("$"), "name": p.name}
    if cls is None:
        entry.update({"view": getattr(cb, "__name__", str(cb)), "module": getattr(cb, "__module__", ""),
                      "methods": [], "drf": False})
        routes.append(entry)
        continue
    module = sys.modules.get(cls.__module__)
    src = source_of(cls)
    drf = hasattr(cls, "permission_classes")
    methods = [m.upper() for m in HTTP if callable(getattr(cls, m, None))]
    actions = getattr(cb, "actions", None)
    if actions:
        methods = [m.upper() for m in actions]
    mp = getattr(cls, "method_permissions", None)
    entry.update({
        "view": cls.__name__,
        "module": cls.__module__,
        "drf": drf,
        "methods": methods,
        "authentication": [c.__name__ for c in getattr(cls, "authentication_classes", [])] if drf else [],
        "permission_classes": [c.__name__ for c in getattr(cls, "permission_classes", [])] if drf else [],
        "method_permissions": {k: (list(v) if isinstance(v, (tuple, list)) else v) for k, v in mp.items()} if isinstance(mp, dict) else None,
        "permission_codes": sorted(set(PERM_RE.findall(src))),
        "throttle_scope": getattr(cls, "throttle_scope", None),
        "models": sorted(models_in(src, module)),
        "tables": sorted(MODELS[m] for m in models_in(src, module)),
        "source_lines": len(src.splitlines()),
    })
    routes.append(entry)

json.dump({
    "defaults": {
        "authentication": [c.__name__ for c in api_settings.DEFAULT_AUTHENTICATION_CLASSES],
        "permission_classes": [c.__name__ for c in api_settings.DEFAULT_PERMISSION_CLASSES],
    },
    "routes": routes,
}, open(OUT, "w"), indent=1, sort_keys=True)
print(len(routes), "routes written to", OUT)
