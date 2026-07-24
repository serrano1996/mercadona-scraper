import requests
import responses

from http_client import HttpClient

URL = "https://tienda.mercadona.es/api/example/"


def _client() -> HttpClient:
    return HttpClient(session=requests.Session())


# --------------------------------------------------------------------- #
# Happy path — 2xx returns the response, for all three verbs
# --------------------------------------------------------------------- #


@responses.activate
def test_get_returns_response_on_2xx():
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    r = _client().get(URL)

    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert len(responses.calls) == 1


@responses.activate
def test_post_returns_response_on_2xx():
    responses.add(responses.POST, URL, json={"ok": True}, status=201)

    r = _client().post(URL, json={"a": 1})

    assert r.status_code == 201
    assert len(responses.calls) == 1


@responses.activate
def test_put_returns_response_on_2xx():
    responses.add(responses.PUT, URL, json={"ok": True}, status=200)

    r = _client().put(URL, json={"a": 1})

    assert r.status_code == 200
    assert len(responses.calls) == 1


# --------------------------------------------------------------------- #
# HTTPError (4xx/5xx) is NOT retried — raised immediately
# --------------------------------------------------------------------- #


@responses.activate
def test_get_raises_immediately_on_http_error_no_retry():
    responses.add(responses.GET, URL, json={"error": "nope"}, status=500)

    try:
        _client().get(URL, retries=3)
        raise AssertionError("expected HTTPError")
    except requests.HTTPError:
        pass

    assert len(responses.calls) == 1


@responses.activate
def test_post_raises_immediately_on_http_error_no_retry():
    responses.add(responses.POST, URL, json={"error": "nope"}, status=404)

    try:
        _client().post(URL, retries=3)
        raise AssertionError("expected HTTPError")
    except requests.HTTPError:
        pass

    assert len(responses.calls) == 1


@responses.activate
def test_put_raises_on_http_error_regression_previously_silently_returned(monkeypatch):
    """Regression test: put() must raise on 4xx/5xx exactly like get/post.

    Prior to a recent fix, put() did not call raise_for_status() inside the
    try block the same way, and silently returned the error response instead
    of raising. This pins the fixed (correct) behavior.
    """
    responses.add(responses.PUT, URL, json={"error": "nope"}, status=500)

    try:
        _client().put(URL, retries=3)
        raise AssertionError("expected HTTPError, put() must not swallow 5xx errors")
    except requests.HTTPError:
        pass

    assert len(responses.calls) == 1


# --------------------------------------------------------------------- #
# Timeout / ConnectionError ARE retried up to `retries`, with backoff
# --------------------------------------------------------------------- #


@responses.activate
def test_get_retries_on_connection_error_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr("http_client.time.sleep", lambda s: sleeps.append(s))

    responses.add(responses.GET, URL, body=requests.exceptions.ConnectionError())
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    r = _client().get(URL, retries=3)

    assert r.json() == {"ok": True}
    assert len(responses.calls) == 2
    assert sleeps == [2]


@responses.activate
def test_get_retries_on_timeout_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr("http_client.time.sleep", lambda s: sleeps.append(s))

    responses.add(responses.GET, URL, body=requests.exceptions.Timeout())
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    r = _client().get(URL, retries=3)

    assert r.json() == {"ok": True}
    assert len(responses.calls) == 2
    assert sleeps == [2]


@responses.activate
def test_get_exhausts_retries_and_raises_connection_error(monkeypatch):
    sleeps = []
    monkeypatch.setattr("http_client.time.sleep", lambda s: sleeps.append(s))

    responses.add(responses.GET, URL, body=requests.exceptions.ConnectionError())
    responses.add(responses.GET, URL, body=requests.exceptions.ConnectionError())
    responses.add(responses.GET, URL, body=requests.exceptions.ConnectionError())

    try:
        _client().get(URL, retries=3)
        raise AssertionError("expected ConnectionError after exhausting retries")
    except requests.ConnectionError as exc:
        assert "3 intentos" in str(exc)

    assert len(responses.calls) == 3
    # backoff sleeps happen between attempt 1->2 and 2->3, not after the last attempt
    assert sleeps == [2, 4]


@responses.activate
def test_post_exhausts_retries_and_raises_connection_error(monkeypatch):
    monkeypatch.setattr("http_client.time.sleep", lambda s: None)

    responses.add(responses.POST, URL, body=requests.exceptions.Timeout())
    responses.add(responses.POST, URL, body=requests.exceptions.Timeout())

    try:
        _client().post(URL, retries=2)
        raise AssertionError("expected ConnectionError after exhausting retries")
    except requests.ConnectionError as exc:
        assert "2 intentos" in str(exc)

    assert len(responses.calls) == 2


@responses.activate
def test_put_retries_on_connection_error_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr("http_client.time.sleep", lambda s: sleeps.append(s))

    responses.add(responses.PUT, URL, body=requests.exceptions.ConnectionError())
    responses.add(responses.PUT, URL, json={"ok": True}, status=200)

    r = _client().put(URL, retries=3)

    assert r.json() == {"ok": True}
    assert len(responses.calls) == 2
    assert sleeps == [2]


@responses.activate
def test_put_exhausts_retries_and_raises_connection_error(monkeypatch):
    monkeypatch.setattr("http_client.time.sleep", lambda s: None)

    responses.add(responses.PUT, URL, body=requests.exceptions.ConnectionError())
    responses.add(responses.PUT, URL, body=requests.exceptions.ConnectionError())
    responses.add(responses.PUT, URL, body=requests.exceptions.ConnectionError())

    try:
        _client().put(URL, retries=3)
        raise AssertionError("expected ConnectionError after exhausting retries")
    except requests.ConnectionError as exc:
        assert "3 intentos" in str(exc)

    assert len(responses.calls) == 3
