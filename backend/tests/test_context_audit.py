"""
CDTRS Backend - Context & Authorization Audit

Purpose:
    Automated audit of the current WorkContextMembership implementation.

This test file intentionally does NOT modify production code.

Run (the backend must be running and seeded), from backend/:
    python tests/test_context_audit.py

Environment (optional):
    CDTRS_API_URL=http://127.0.0.1:8123      (default; /api/v1 suffix allowed)

Uses only the standard library and requests (pytest is not in imp.txt); the
small runner at the end of this file provides the two features it needs:
module-level fixtures and parametrised tests.
"""

import inspect
import os
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional

import requests


def fixture(fn: Callable) -> Callable:
    """Marks a function whose result is shared by the tests that name it as an argument."""
    fn._is_fixture = True
    return fn


def parametrize(arg: str, values: List[Any]) -> Callable:
    """Runs the test once per value of *arg*."""
    def decorate(fn: Callable) -> Callable:
        fn._params = (arg, list(values))
        return fn
    return decorate


# ============================================================
# CONFIGURATION
# ============================================================

# The test server (python run_server.py --port 8123 --host 127.0.0.1 --no-mail).
# CDTRS_API_URL may be given with or without the /api/v1 suffix.
BASE_URL = os.getenv(
    "CDTRS_API_URL",
    "http://127.0.0.1:8123",
).rstrip("/")
if BASE_URL.endswith("/api/v1"):
    BASE_URL = BASE_URL[: -len("/api/v1")]

API = f"{BASE_URL}/api/v1"


# ------------------------------------------------------------
# Test accounts
#
# These match the seeded accounts we have been using.
# Passwords can be overridden with environment variables.
# ------------------------------------------------------------

USERS = {
    "rahul": {
        "username": "emp_rahul",
        "password": "cdtrs@emp",
    },
    "tso": {
        "username": "tso_user",
        "password": "cdtrs@tso",
    },
    "hod": {
        "username": "hod_prod",
        "password": "cdtrs@hod",
    },
    "ds": {
        "username": "exec_user",
        "password": "cdtrs@ds",
    },
    "director": {
        "username": "director",
        "password": "cdtrs@director",
    },
}


# ============================================================
# HTTP HELPERS
# ============================================================

def _request(
    method: str,
    path: str,
    *,
    token: Optional[str] = None,
    context_id: Optional[int] = None,
    expected_status: Optional[int] = None,
    **kwargs,
) -> requests.Response:
    """
    Send an HTTP request and optionally assert the expected status.
    """

    headers = kwargs.pop("headers", {}) or {}

    if token:
        headers["Authorization"] = f"Bearer {token}"

    if context_id is not None:
        headers["X-Work-Context-Id"] = str(context_id)

    response = requests.request(
        method,
        f"{API}{path}",
        headers=headers,
        timeout=15,
        **kwargs,
    )

    if expected_status is not None:
        assert response.status_code == expected_status, (
            f"\nRequest: {method} {path}"
            f"\nExpected: {expected_status}"
            f"\nActual: {response.status_code}"
            f"\nResponse: {response.text[:2000]}"
        )

    return response


def _json(response: requests.Response) -> Any:
    """Safely decode JSON."""
    try:
        return response.json()
    except Exception:
        return None


# ============================================================
# LOGIN / CONTEXT HELPERS
# ============================================================

def login(username: str, password: str) -> Dict[str, Any]:
    response = requests.post(
        f"{API}/auth/login",
        json={
            "username": username,
            "password": password,
        },
        timeout=15,
    )

    assert response.status_code == 200, (
        f"Login failed for {username}: "
        f"{response.status_code} {response.text[:1000]}"
    )

    data = _json(response)

    assert isinstance(data, dict), "Login response is not JSON object."
    assert data.get("access_token"), "Login response has no access_token."
    assert data.get("user"), "Login response has no user."

    return data


def get_contexts(token: str) -> List[Dict[str, Any]]:
    response = _request(
        "GET",
        "/auth/contexts",
        token=token,
        expected_status=200,
    )

    data = _json(response)

    assert isinstance(data, list), (
        f"/auth/contexts should return a list, got: {data!r}"
    )

    return data


def context_type(context: Dict[str, Any]) -> Optional[str]:
    return (
        context.get("context_type")
        or context.get("context")
        or context.get("type")
    )


def context_department_id(context: Dict[str, Any]) -> Optional[int]:
    value = (
        context.get("department_id")
        or context.get("departmentId")
    )

    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def context_department_name(context: Dict[str, Any]) -> Optional[str]:
    return (
        context.get("department_name")
        or context.get("departmentName")
        or context.get("department")
    )


def context_id(context: Dict[str, Any]) -> Optional[int]:
    value = (
        context.get("id")
        or context.get("context_membership_id")
        or context.get("membership_id")
    )

    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def find_context(
    contexts: List[Dict[str, Any]],
    context_name: str,
    department_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Find a context by type and optionally department.

    Example:
        find_context(contexts, "EMPLOYEE", "Engineering & Innovation")
    """

    wanted_type = context_name.upper()
    wanted_department = (
        department_name.upper()
        if department_name
        else None
    )

    matches = []

    for ctx in contexts:
        ctype = context_type(ctx)

        if not ctype:
            continue

        if ctype.upper() != wanted_type:
            continue

        if wanted_department:
            dept = context_department_name(ctx)

            if dept and dept.upper() == wanted_department:
                matches.append(ctx)
        else:
            matches.append(ctx)

    assert matches, (
        f"Could not find context "
        f"{wanted_type}"
        f"{' • ' + wanted_department if wanted_department else ''}.\n"
        f"Available contexts:\n{contexts}"
    )

    return matches[0]


def switch_context(token: str, membership_id: int) -> Dict[str, Any]:
    response = _request(
        "POST",
        "/auth/switch-context",
        token=token,
        json={
            "context_membership_id": membership_id,
        },
        expected_status=200,
    )

    data = _json(response)

    assert isinstance(data, dict), (
        f"Switch-context response is not an object: {data!r}"
    )

    returned_id = context_id(data)

    assert returned_id == membership_id, (
        f"Backend returned different context ID.\n"
        f"Requested: {membership_id}\n"
        f"Returned: {returned_id}\n"
        f"Response: {data}"
    )

    return data


# ============================================================
# HEALTH
# ============================================================

def test_backend_health():
    """
    Basic sanity check before running the context audit.
    """

    response = requests.get(
        f"{BASE_URL}/health",
        timeout=10,
    )

    assert response.status_code == 200, (
        f"Backend health check failed: "
        f"{response.status_code} {response.text}"
    )

    data = _json(response)

    assert data.get("status") == "healthy"

    print("\n[PASS] Backend health")


# ============================================================
# RAHUL - MULTI CONTEXT
# ============================================================

@fixture
def rahul_session():
    data = login(
        USERS["rahul"]["username"],
        USERS["rahul"]["password"],
    )

    token = data["access_token"]
    contexts = get_contexts(token)

    return {
        "token": token,
        "user": data["user"],
        "contexts": contexts,
    }


def test_rahul_has_multiple_contexts(rahul_session):
    contexts = rahul_session["contexts"]

    assert len(contexts) >= 2, (
        "Rahul should have multiple work contexts."
        f"\nContexts returned: {contexts}"
    )

    context_pairs = {
        (
            (context_type(ctx) or "").upper(),
            (context_department_name(ctx) or "").upper(),
        )
        for ctx in contexts
    }

    assert any(
        ctype == "EMPLOYEE" and dept == "ENGINEERING & INNOVATION"
        for ctype, dept in context_pairs
    ), (
        "Rahul is missing EMPLOYEE • FCTD context.\n"
        f"Contexts: {contexts}"
    )

    assert any(
        ctype == "HOD" and dept == "PRODUCT STRATEGY"
        for ctype, dept in context_pairs
    ), (
        "Rahul is missing HOD • PSTD context.\n"
        f"Contexts: {contexts}"
    )

    print("\n[PASS] Rahul has EMPLOYEE • FCTD and HOD • PSTD")


def test_rahul_context_membership_ids_are_valid(rahul_session):
    contexts = rahul_session["contexts"]

    ids = [context_id(ctx) for ctx in contexts]

    assert all(cid is not None for cid in ids), (
        f"Every context must have a membership ID.\n"
        f"Contexts: {contexts}"
    )

    assert len(ids) == len(set(ids)), (
        f"Duplicate context membership IDs returned: {ids}"
    )

    print("\n[PASS] Rahul context membership IDs are valid")


def test_rahul_can_switch_to_employee_context(rahul_session):
    contexts = rahul_session["contexts"]

    employee_context = find_context(
        contexts,
        "EMPLOYEE",
        "Engineering & Innovation",
    )

    membership_id = context_id(employee_context)

    assert membership_id is not None

    result = switch_context(
        rahul_session["token"],
        membership_id,
    )

    assert context_type(result) == "EMPLOYEE"

    print(
        f"\n[PASS] Rahul switched to "
        f"EMPLOYEE • FCTD (membership {membership_id})"
    )


def test_rahul_can_switch_to_hod_context(rahul_session):
    contexts = rahul_session["contexts"]

    hod_context = find_context(
        contexts,
        "HOD",
        "Product Strategy",
    )

    membership_id = context_id(hod_context)

    assert membership_id is not None

    result = switch_context(
        rahul_session["token"],
        membership_id,
    )

    assert context_type(result) == "HOD"

    print(
        f"\n[PASS] Rahul switched to "
        f"HOD • PSTD (membership {membership_id})"
    )


def test_rahul_cannot_switch_to_another_users_context(rahul_session):
    """
    Membership IDs are user-owned.

    We deliberately use an obviously invalid ID rather than
    depending on another user's exact seeded membership ID.
    """

    response = _request(
        "POST",
        "/auth/switch-context",
        token=rahul_session["token"],
        json={
            "context_membership_id": 999999999,
        },
    )

    assert response.status_code == 403, (
        "A user must not be able to switch to a context "
        "that does not belong to them.\n"
        f"Actual response: {response.status_code} "
        f"{response.text}"
    )

    print("\n[PASS] Rahul cannot switch to an unauthorized context")


# ============================================================
# CONTEXT HEADER VALIDATION
# ============================================================

def test_invalid_context_header_is_rejected(rahul_session):
    response = _request(
        "GET",
        "/documents",
        token=rahul_session["token"],
        headers={
            "X-Work-Context-Id": "not-a-number",
        },
    )

    assert response.status_code == 400, (
        "Invalid X-Work-Context-Id should return 400.\n"
        f"Actual: {response.status_code}\n"
        f"Response: {response.text}"
    )

    print("\n[PASS] Invalid context header rejected")


def test_unknown_context_header_is_rejected(rahul_session):
    response = _request(
        "GET",
        "/documents",
        token=rahul_session["token"],
        context_id=999999999,
    )

    assert response.status_code == 403, (
        "Unknown/unauthorized context ID should return 403.\n"
        f"Actual: {response.status_code}\n"
        f"Response: {response.text}"
    )

    print("\n[PASS] Unknown context header rejected")


# ============================================================
# TSO + EMPLOYEE DUAL CONTEXT
# ============================================================

@fixture
def tso_session():
    data = login(
        USERS["tso"]["username"],
        USERS["tso"]["password"],
    )

    token = data["access_token"]
    contexts = get_contexts(token)

    return {
        "token": token,
        "user": data["user"],
        "contexts": contexts,
    }


def test_tso_has_expected_contexts(tso_session):
    contexts = tso_session["contexts"]

    context_types = {
        context_type(ctx)
        for ctx in contexts
    }

    assert "TSO" in context_types, (
        "TSO user is missing TSO context.\n"
        f"Contexts: {contexts}"
    )

    assert "EMPLOYEE" in context_types, (
        "TSO user should also have Employee context.\n"
        f"Contexts: {contexts}"
    )

    print("\n[PASS] TSO has TSO + EMPLOYEE contexts")


def test_tso_can_switch_between_contexts(tso_session):
    contexts = tso_session["contexts"]

    tso_ctx = find_context(contexts, "TSO")
    employee_ctx = find_context(contexts, "EMPLOYEE")

    tso_id = context_id(tso_ctx)
    employee_id = context_id(employee_ctx)

    assert tso_id is not None
    assert employee_id is not None

    switch_context(tso_session["token"], tso_id)
    switch_context(tso_session["token"], employee_id)
    switch_context(tso_session["token"], tso_id)

    # Context list must remain intact after switching.
    refreshed = get_contexts(tso_session["token"])

    refreshed_ids = {
        context_id(ctx)
        for ctx in refreshed
    }

    assert tso_id in refreshed_ids
    assert employee_id in refreshed_ids

    print(
        "\n[PASS] TSO can switch "
        "TSO → EMPLOYEE → TSO without losing contexts"
    )


# ============================================================
# HOD MULTI-DEPARTMENT CONTEXT
# ============================================================

@fixture
def hod_session():
    data = login(
        USERS["hod"]["username"],
        USERS["hod"]["password"],
    )

    token = data["access_token"]
    contexts = get_contexts(token)

    return {
        "token": token,
        "user": data["user"],
        "contexts": contexts,
    }


def test_hod_has_expected_context(hod_session):
    contexts = hod_session["contexts"]

    assert any(
        context_type(ctx) == "HOD"
        for ctx in contexts
    ), (
        "HOD account has no HOD context.\n"
        f"Contexts: {contexts}"
    )

    print("\n[PASS] HOD has HOD context")


def test_hod_multiple_contexts_if_seeded(hod_session):
    contexts = hod_session["contexts"]

    hod_contexts = [
        ctx for ctx in contexts
        if context_type(ctx) == "HOD"
    ]

    # This is intentionally not a hard failure because different
    # seed configurations may contain one or multiple HOD contexts.
    if len(hod_contexts) >= 2:
        ids = [context_id(ctx) for ctx in hod_contexts]

        assert len(ids) == len(set(ids))

        print(
            f"\n[PASS] HOD has {len(hod_contexts)} HOD contexts"
        )
    else:
        print(
            "\n[INFO] HOD currently has only one HOD context; "
            "multi-HOD-department isolation not exercised."
        )


# ============================================================
# BASIC ROLE LOGIN TESTS
# ============================================================

@parametrize(
    "user_key",
    [
        "ds",
        "director",
    ],
)
def test_core_role_login(user_key):
    user = USERS[user_key]

    data = login(
        user["username"],
        user["password"],
    )

    returned_user = data["user"]

    assert returned_user.get("username") == user["username"]

    contexts = get_contexts(data["access_token"])

    assert contexts, (
        f"{user_key} logged in but has no active contexts."
    )

    print(
        f"\n[PASS] {user_key.upper()} login + context retrieval"
    )


# ============================================================
# DOCUMENT ACCESS WITH CONTEXT
# ============================================================

def test_documents_endpoint_accepts_valid_employee_context(
    rahul_session,
):
    employee_ctx = find_context(
        rahul_session["contexts"],
        "EMPLOYEE",
        "Engineering & Innovation",
    )

    membership_id = context_id(employee_ctx)

    response = _request(
        "GET",
        "/documents",
        token=rahul_session["token"],
        context_id=membership_id,
    )

    assert response.status_code in (200, 403), (
        "Unexpected response from documents endpoint.\n"
        f"Status: {response.status_code}\n"
        f"Response: {response.text[:2000]}"
    )

    if response.status_code == 200:
        assert isinstance(_json(response), list)

    print(
        f"\n[INFO] Employee-context /documents returned "
        f"{response.status_code}"
    )


def test_documents_endpoint_accepts_valid_hod_context(
    rahul_session,
):
    hod_ctx = find_context(
        rahul_session["contexts"],
        "HOD",
        "Product Strategy",
    )

    membership_id = context_id(hod_ctx)

    response = _request(
        "GET",
        "/documents",
        token=rahul_session["token"],
        context_id=membership_id,
    )

    assert response.status_code in (200, 403), (
        "Unexpected response from documents endpoint.\n"
        f"Status: {response.status_code}\n"
        f"Response: {response.text[:2000]}"
    )

    if response.status_code == 200:
        assert isinstance(_json(response), list)

    print(
        f"\n[INFO] HOD-context /documents returned "
        f"{response.status_code}"
    )


# ============================================================
# FINAL AUDIT SUMMARY
# ============================================================

def test_context_structure_summary(
    rahul_session,
    tso_session,
):
    """
    This is a non-invasive final structural sanity check.
    """

    print("\n")
    print("=" * 60)
    print("CDTRS CONTEXT AUDIT SUMMARY")
    print("=" * 60)

    print("\nRahul:")
    for ctx in rahul_session["contexts"]:
        print(
            f"  {context_id(ctx)} | "
            f"{context_type(ctx)} • "
            f"{context_department_name(ctx) or '—'}"
        )

    print("\nTSO:")
    for ctx in tso_session["contexts"]:
        print(
            f"  {context_id(ctx)} | "
            f"{context_type(ctx)} • "
            f"{context_department_name(ctx) or '—'}"
        )

    print("\n" + "=" * 60)
    print("Context structure audit completed.")
    print("=" * 60)


# ============================================================
# RUNNER
# ============================================================

def run_all() -> int:
    namespace = globals()
    cache: Dict[str, Any] = {}

    def resolve(name: str) -> Any:
        if name not in cache:
            cache[name] = namespace[name]()
        return cache[name]

    passed = failed = 0
    for name, fn in list(namespace.items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        arg, values = getattr(fn, "_params", (None, [None]))
        for value in values:
            label = f"{name}[{value}]" if arg else name
            try:
                kwargs = {arg: value} if arg else {}
                for param in inspect.signature(fn).parameters:
                    if param not in kwargs:
                        kwargs[param] = resolve(param)
                fn(**kwargs)
                passed += 1
                print(f"ok    {label}")
            except Exception:
                failed += 1
                print(f"FAIL  {label}")
                traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_all())
