"""The request middleware in main.py and the request-id helpers it uses:
the backend's X-Request-Id is kept (and echoed back) when it looks safe,
replaced otherwise, and tags every log line written during the request."""

import logging

from fastapi.testclient import TestClient

from app.logging_setup import RequestIdFilter, request_id_from, request_id_var
from app.main import app

client = TestClient(app)


def test_safe_incoming_request_id_is_echoed():
    response = client.get("/health", headers={"X-Request-Id": "abc-123"})
    assert response.headers["X-Request-Id"] == "abc-123"


def test_missing_request_id_gets_a_fresh_one():
    response = client.get("/health")
    assert len(response.headers["X-Request-Id"]) == 36


def test_unsafe_request_ids_are_replaced():
    assert len(request_id_from("bad id\nforged line")) == 36
    assert len(request_id_from("x" * 65)) == 36
    assert request_id_from("ok_1.2-3") == "ok_1.2-3"


def test_log_records_carry_the_current_request_id():
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "msg", None, None)
    token = request_id_var.set("req-9")
    try:
        RequestIdFilter().filter(record)
    finally:
        request_id_var.reset(token)
    assert record.request_id == "req-9"
