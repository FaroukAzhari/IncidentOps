"""Check frontend truthfulness with actual workflow traces; no browser dependency."""

from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from incidentops.api import create_app
from incidentops.config import Settings
from incidentops.demo import SCENARIOS


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.scripts = []
        self.tree = {"tag": "document", "attrs": {}, "children": [], "text": ""}
        self.stack = [self.tree]

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "script":
            self.scripts.append(attrs["src"])
        element = {"tag": tag, "attrs": attrs, "children": [], "text": ""}
        self.stack[-1]["children"].append(element)
        if tag not in {"input", "meta", "link", "br", "hr", "img"}:
            self.stack.append(element)

    def handle_endtag(self, tag):
        if len(self.stack) > 1:
            self.stack.pop()

    def handle_data(self, data):
        self.stack[-1]["text"] += data


def test_presentation_assets_and_element_references():
    static = Path("incidentops/static")
    page = Page()
    page.feed((static / "index.html").read_text(encoding="utf-8"))
    assert len(page.ids) == len(set(page.ids)), "Duplicate DOM IDs break dynamic rendering"
    with TestClient(create_app(Settings())) as client:
        for script in page.scripts:
            assert client.get(script).status_code == 200
    for path in static.iterdir():
        if path.suffix not in {".html", ".css", ".js"}:
            continue
        content = path.read_text(encoding="utf-8")
        # All UI symbols are ASCII entities/JS escapes, avoiding Windows pipe loss.
        assert content.isascii(), f"Unexpected non-ASCII bytes in {path}"
        if path.suffix == ".js":
            for element in re.findall(r"\$\(['\"]([a-z][a-z0-9-]*)['\"]\)", content):
                assert element in page.ids, f"Missing UI element {element} in {path}"


def test_frontend_rules_against_all_seven_real_api_results():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Optional frontend rule tests use an existing Node installation")
    results = []
    with TestClient(create_app(Settings())) as client:
        for scenario in SCENARIOS:
            response = client.post("/api/incidents", json={"report": "Investigate current observations", "scenario": scenario})
            assert response.status_code == 200
            result = response.json()
            assert client.get(f"/api/incidents/{result['thread_id']}").json() == result
            results.append(result)
    completed = subprocess.run([node, "tests/presentation_checks.cjs"], input=json.dumps(results),
                               text=True, capture_output=True, timeout=15)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    page = Page()
    page.feed(Path("incidentops/static/index.html").read_text(encoding="utf-8"))
    dom = subprocess.run([node, "tests/presentation_dom_checks.cjs"],
                         input=json.dumps({"results": results, "tree": page.tree}),
                         text=True, capture_output=True, timeout=15)
    assert dom.returncode == 0, dom.stdout + dom.stderr
