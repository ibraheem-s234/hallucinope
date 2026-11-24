"""Tests for the web server: the API payload, the page files, and error handling.

The server runs on a random free port inside the test, with a small dataset of
real figures (Saudi Arabia 1960 from the 2026-11-24 World Bank download).
"""

import json
import threading
import urllib.error
import urllib.request
from datetime import date

import pytest

from hallucinope.data import worldbank
from hallucinope.data.models import Country, PopulationData, Series
from hallucinope.data.population import Population
from hallucinope.web.server import MAX_TEXT, Checker, serve


@pytest.fixture(scope="module")
def checker():
    s = Series(Country("SAU", "SA", "Saudi Arabia"))
    s.figures[1960] = worldbank.make_figure("SAU", 1960, 2_435_403, date(2026, 11, 24))
    return Checker(Population(PopulationData({"SAU": s}), None))


@pytest.fixture(scope="module")
def base_url(checker):
    httpd = serve(checker, port=0)                 # 0 = any free port
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def get(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never via a proxy
    try:
        with opener.open(url, timeout=5) as r:
            return r.status, r.headers.get("Content-Type"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read()


def post(url, payload):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


TEXT = "Saudi Arabia had 4.1 million people in 1960. It was 20 °C (68 °F). Prices rose 12%."


def test_payload_has_everything_the_page_needs(checker):
    p = checker.check(TEXT)
    assert p["text"] == TEXT
    pop, conv = p["claims"]
    assert (pop["verdict"], pop["kind"], pop["text"]) == ("wrong", "population", "4.1 million")
    assert TEXT[pop["start"]:pop["end"]] == "4.1 million"
    assert pop["detail"].startswith("Saudi Arabia's population is 2,435,403")
    assert pop["figure"]["year"] == 1960 and "worldbank.org" in pop["figure"]["url"]
    assert (conv["verdict"], conv["conversion"]["expected"]) == ("correct", 68)
    assert p["counts"] == {"correct": 1, "wrong": 1, "unconfirmed": 0, "cant_verify": 0}
    assert [u["text"] for u in p["unchecked"]] == ["12%"]


def test_conversion_mark_includes_the_closing_bracket(checker):
    conv = checker.check(TEXT)["claims"][1]
    assert conv["text"] == "20 °C (68 °F)" and TEXT[conv["start"]:conv["end"]] == conv["text"]


@pytest.mark.parametrize("path, kind", [("/", "text/html"), ("/static/style.css", "text/css"),
                                        ("/static/app.js", "text/javascript"),
                                        ("/static/samples.js", "text/javascript")])
def test_page_files_are_served(base_url, path, kind):
    status, content_type, body = get(base_url + path)
    assert status == 200 and content_type.startswith(kind) and body


@pytest.mark.parametrize("path", ["/../pyproject.toml", "/static/../server.py", "/etc/passwd"])
def test_nothing_else_is_served(base_url, path):
    assert get(base_url + path)[0] == 404


def test_check_over_http(base_url):
    status, data = post(base_url + "/api/check", {"text": TEXT})
    assert status == 200 and data["claims"][0]["verdict"] == "wrong"


@pytest.mark.parametrize("payload, status", [
    ({"text": "   "}, 400),
    ({"nothing": 1}, 400),
    (b"not json", 400),
    ({"text": "x" * (MAX_TEXT + 1)}, 413),
])
def test_bad_requests_get_clear_errors(base_url, payload, status):
    code, data = post(base_url + "/api/check", payload)
    assert code == status and data["error"]


def test_server_only_listens_locally(checker):
    httpd = serve(checker, port=0)
    try:
        assert httpd.server_address[0] == "127.0.0.1"
    finally:
        httpd.server_close()
