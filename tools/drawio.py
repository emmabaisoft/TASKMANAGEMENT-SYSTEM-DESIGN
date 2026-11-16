"""Tiny helper for writing uncompressed draw.io (diagrams.net) XML files.

Only the standard library is used. Every cell gets an explicit, stable id so
that the generated files diff cleanly in git.
"""
from __future__ import annotations

import datetime
import os
from xml.sax.saxutils import quoteattr

GENERATED_ON = os.environ.get("DIAGRAM_DATE") or datetime.date.today().isoformat()

# ---------------------------------------------------------------------------
# Shared colour scheme (fill, stroke) - used by every diagram in this repo.
# ---------------------------------------------------------------------------
DOMAIN_COLOURS = {
    "users": ("#dae8fc", "#6c8ebf"),
    "institution": ("#d5e8d4", "#82b366"),
    "projects": ("#ffe6cc", "#d79b00"),
    "tasks": ("#fff2cc", "#d6b656"),
    "performance": ("#e1d5e7", "#9673a6"),
    "approval": ("#f8cecc", "#b85450"),
    "calendar2": ("#b0e3e6", "#0e8088"),
    "communication": ("#ffcce6", "#cc6699"),
    "reports": ("#d0cee2", "#56517e"),
    "settings": ("#e6e6e6", "#666666"),
    "audit": ("#fad9d5", "#ae4132"),
    "system": ("#bac8d3", "#23445d"),
    "framework": ("#f5f5f5", "#999999"),
}

ROLE_COLOURS = {
    "actor": ("#08427b", "#073b6f", "#ffffff"),
    "system": ("#1168bd", "#0b4884", "#ffffff"),
    "container": ("#dae8fc", "#6c8ebf", "#000000"),
    "component": ("#dae8fc", "#6c8ebf", "#000000"),
    "worker": ("#e1d5e7", "#9673a6", "#000000"),
    "datastore": ("#d5e8d4", "#82b366", "#000000"),
    "queue": ("#ffe6cc", "#d79b00", "#000000"),
    "external": ("#e6e6e6", "#666666", "#000000"),
    "frontend": ("#fff2cc", "#d6b656", "#000000"),
    "note": ("#fffde7", "#bfa900", "#000000"),
    "inferred": ("#ffffff", "#cc0000", "#cc0000"),
}


def role_style(role: str, extra: str = "") -> str:
    fill, stroke, font = ROLE_COLOURS[role]
    return f"fillColor={fill};strokeColor={stroke};fontColor={font};{extra}"


class Page:
    def __init__(self, name: str, page_id: str):
        self.name = name
        self.page_id = page_id
        self.cells: list[str] = []
        self.ids: set[str] = set()

    def _register(self, cell_id: str) -> None:
        if cell_id in self.ids:
            raise ValueError(f"duplicate cell id {cell_id!r} on page {self.name!r}")
        self.ids.add(cell_id)

    def vertex(self, cell_id, value, style, x, y, w, h, parent="1", extra_attrs="", alt_width=None):
        self._register(cell_id)
        alt = f'<mxRectangle width="{alt_width:g}" height="{h:g}" as="alternateBounds"/>' if alt_width else ""
        self.cells.append(
            f'<mxCell id={quoteattr(cell_id)} value={quoteattr(value)} style={quoteattr(style)} '
            f'vertex="1" parent={quoteattr(parent)}{(" " + extra_attrs) if extra_attrs else ""}>'
            f'<mxGeometry x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" as="geometry">{alt}</mxGeometry></mxCell>'
        )
        return cell_id

    def edge(self, cell_id, value, style, source=None, target=None, parent="1", points=None,
             source_point=None, target_point=None, label_x=None):
        self._register(cell_id)
        attrs = ""
        if source:
            attrs += f" source={quoteattr(source)}"
        if target:
            attrs += f" target={quoteattr(target)}"
        inner = ""
        if source_point:
            inner += f'<mxPoint x="{source_point[0]:g}" y="{source_point[1]:g}" as="sourcePoint"/>'
        if target_point:
            inner += f'<mxPoint x="{target_point[0]:g}" y="{target_point[1]:g}" as="targetPoint"/>'
        if points:
            inner += '<Array as="points">' + "".join(
                f'<mxPoint x="{px:g}" y="{py:g}"/>' for px, py in points
            ) + "</Array>"
        geo_attrs = ' relative="1"'
        if label_x is not None:
            geo_attrs = f' x="{label_x:g}" relative="1"'
        self.cells.append(
            f'<mxCell id={quoteattr(cell_id)} value={quoteattr(value)} style={quoteattr(style)} '
            f'edge="1" parent={quoteattr(parent)}{attrs}>'
            f'<mxGeometry{geo_attrs} as="geometry">{inner}</mxGeometry></mxCell>'
        )
        return cell_id

    # -- conveniences -------------------------------------------------------
    def text(self, cell_id, value, x, y, w, h, extra="", parent="1"):
        style = ("text;html=1;whiteSpace=wrap;align=left;verticalAlign=top;"
                 "strokeColor=none;fillColor=none;" + extra)
        return self.vertex(cell_id, value, style, x, y, w, h, parent=parent)

    def title(self, title, subtitle="", x=40, y=20, w=900):
        self.text("title", f"<b>{title}</b>", x, y, w, 36, "fontSize=24;")
        sub = f"Last generated: {GENERATED_ON}"
        if subtitle:
            sub += f"<br>{subtitle}"
        self.text("title_meta", sub, x, y + 40, w, 50, "fontSize=12;fontColor=#555555;")

    def box(self, cell_id, value, x, y, w, h, role="container", extra="", parent="1"):
        style = "rounded=1;whiteSpace=wrap;html=1;arcSize=8;" + role_style(role, extra)
        return self.vertex(cell_id, value, style, x, y, w, h, parent=parent)

    def note(self, cell_id, value, x, y, w, h, parent="1"):
        style = ("shape=note;size=14;whiteSpace=wrap;html=1;align=left;verticalAlign=top;"
                 "spacing=8;fontSize=11;" + role_style("note"))
        return self.vertex(cell_id, value, style, x, y, w, h, parent=parent)

    def inferred(self, cell_id, value, x, y, w, h, parent="1"):
        style = ("shape=note;size=14;whiteSpace=wrap;html=1;align=left;verticalAlign=top;"
                 "spacing=8;fontSize=11;dashed=1;" + role_style("inferred"))
        return self.vertex(cell_id, "<b>Inferred – verify</b><br>" + value, style, x, y, w, h, parent=parent)

    def legend(self, items, x, y, w=260, title="Legend"):
        """items: list of (role_or_(fill,stroke,font), label)."""
        h = 34 + 28 * len(items)
        self.vertex("legend", f"<b>{title}</b>",
                    "rounded=0;whiteSpace=wrap;html=1;verticalAlign=top;align=left;spacingLeft=8;"
                    "fillColor=#ffffff;strokeColor=#999999;container=1;collapsible=0;",
                    x, y, w, h)
        for i, (role, label) in enumerate(items):
            if isinstance(role, str):
                fill, stroke, _font = ROLE_COLOURS[role]
                dashed = "dashed=1;" if role == "inferred" else ""
            else:
                fill, stroke = role[0], role[1]
                dashed = role[2] if len(role) > 2 else ""
            self.vertex(f"legend_sw_{i}", "",
                        f"rounded=1;html=1;fillColor={fill};strokeColor={stroke};{dashed}",
                        10, 32 + 28 * i, 28, 18, parent="legend")
            self.vertex(f"legend_tx_{i}", label,
                        "text;html=1;align=left;verticalAlign=middle;strokeColor=none;fillColor=none;fontSize=11;",
                        46, 30 + 28 * i, w - 54, 22, parent="legend")
        return h

    def xml(self) -> str:
        body = "".join(self.cells)
        return (
            f'<diagram id={quoteattr(self.page_id)} name={quoteattr(self.name)}>'
            '<mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" '
            'arrows="1" fold="1" page="0" pageScale="1" pageWidth="1654" pageHeight="1169" math="0" shadow="0">'
            f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>{body}</root></mxGraphModel></diagram>'
        )


class Diagram:
    def __init__(self):
        self.pages: list[Page] = []

    def page(self, name: str) -> Page:
        page_id = "page_" + "".join(ch if ch.isalnum() else "_" for ch in name.lower())
        p = Page(name, page_id)
        self.pages.append(p)
        return p

    def write(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               f'<mxfile host="app.diagrams.net" agent="tools/drawio.py" version="24.0.0" compressed="false">\n'
               + "\n".join(p.xml().replace("<mxCell", "\n<mxCell") for p in self.pages)
               + "\n</mxfile>\n")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(xml)
