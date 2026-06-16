"""
Practice Lab test suite.

All tests mock the Claude service functions so no real Anthropic API calls are made.
A temporary SQLite database is used; the real database.db is never touched.
"""

import json
import os
import sys
import pytest

from unittest.mock import patch, MagicMock
from werkzeug.security import generate_password_hash

# ---------------------------------------------------------------------------
# Path setup — allow imports from the project root
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_db(tmp_path):
    """Return the path to a fresh temporary database file."""
    return str(tmp_path / "test.db")


@pytest.fixture
def client(test_db):
    """Flask test client backed by a fresh temporary database."""
    import app as app_module

    original_db = app_module.DB_PATH
    app_module.DB_PATH = test_db
    app_module.init_db()
    app_module.app.config["TESTING"] = True
    app_module.app.config["WTF_CSRF_ENABLED"] = False

    with app_module.app.test_client() as c:
        yield c

    app_module.DB_PATH = original_db


def _create_user(test_db, username, password, role):
    """Insert a user directly into the test database."""
    import app as app_module
    original_db = app_module.DB_PATH
    app_module.DB_PATH = test_db
    conn = app_module.get_db()
    conn.execute(
        "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
        (username, generate_password_hash(password), role),
    )
    conn.commit()
    conn.close()
    app_module.DB_PATH = original_db


def _login(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


def _insert_scenario(test_db, generated_by, answer_key_content="SECRET_ANSWER_KEY"):
    """Insert a practice scenario directly and return its id."""
    import app as app_module
    original_db = app_module.DB_PATH
    app_module.DB_PATH = test_db
    conn = app_module.get_db()
    cursor = conn.execute(
        """INSERT INTO practice_scenarios
               (title, description, category, priority, difficulty,
                answer_key_json, generated_by, created_at,
                generation_input_tokens, generation_output_tokens, generation_cost_usd)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "Test Printer Issue",
            "The printer in Room 3 is offline.",
            "Printers",
            "medium",
            "Beginner",
            json.dumps({"grading_notes": answer_key_content, "likely_causes": [answer_key_content]}),
            generated_by,
            "2026-01-01 10:00:00",
            100,
            200,
            0.000001,
        ),
    )
    conn.commit()
    scenario_id = cursor.lastrowid
    conn.close()
    app_module.DB_PATH = original_db
    return scenario_id


def _insert_attempt(test_db, scenario_id, admin_username, final_score=80, raw_score=80):
    """Insert a graded attempt directly and return its id."""
    import app as app_module
    original_db = app_module.DB_PATH
    app_module.DB_PATH = test_db
    conn = app_module.get_db()
    cursor = conn.execute(
        """INSERT INTO practice_attempts
               (scenario_id, admin_username, response_text,
                raw_score, final_score, letter_grade, passed, score_cap_reason,
                category_scores_json, feedback_json,
                grading_input_tokens, grading_output_tokens, grading_cost_usd,
                submitted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            scenario_id,
            admin_username,
            "My response text here for grading.",
            raw_score,
            final_score,
            "B",
            1 if final_score >= 70 else 0,
            None,
            json.dumps({"technical_accuracy": 28, "troubleshooting_process": 16,
                        "security_and_safety": 12, "completeness_and_escalation": 8,
                        "professionalism_and_empathy": 8, "clarity_and_actionability": 8}),
            json.dumps({"category_feedback": {}, "flags": {}, "strengths": [],
                        "technical_errors": [], "missing_items": [],
                        "security_concerns": [], "improvement_steps": [],
                        "improved_example_response": ""}),
            500,
            700,
            0.000004,
            "2026-01-01 10:05:00",
        ),
    )
    conn.commit()
    attempt_id = cursor.lastrowid
    conn.close()
    app_module.DB_PATH = original_db
    return attempt_id


# ---------------------------------------------------------------------------
# 1. Normal users cannot access Practice Lab routes
# ---------------------------------------------------------------------------

def test_normal_user_cannot_access_practice(client, test_db):
    _create_user(test_db, "regularuser", "pass", "user")
    _login(client, "regularuser", "pass")
    rv = client.get("/admin/practice")
    # Should redirect away (to login), not return 200
    assert rv.status_code in (302, 403)


# ---------------------------------------------------------------------------
# 2. Logged-out users are redirected
# ---------------------------------------------------------------------------

def test_logged_out_redirected_from_practice(client):
    rv = client.get("/admin/practice")
    assert rv.status_code == 302
    assert b"login" in rv.headers["Location"].lower().encode()


# ---------------------------------------------------------------------------
# 3. Admins can access the Practice Lab
# ---------------------------------------------------------------------------

def test_admin_can_access_practice(client, test_db):
    _create_user(test_db, "admin1", "pass", "admin")
    _login(client, "admin1", "pass")
    rv = client.get("/admin/practice")
    assert rv.status_code == 200
    assert b"Practice Lab" in rv.data


# ---------------------------------------------------------------------------
# 4. Missing API key does not crash the application
# ---------------------------------------------------------------------------

def test_missing_api_key_does_not_crash(client, test_db):
    _create_user(test_db, "admin2", "pass", "admin")
    _login(client, "admin2", "pass")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
        rv = client.get("/admin/practice")
    assert rv.status_code == 200
    assert b"API Key Not Configured" in rv.data


# ---------------------------------------------------------------------------
# 5. Invalid category is rejected before any API call
# ---------------------------------------------------------------------------

def test_invalid_category_rejected(client, test_db):
    _create_user(test_db, "admin3", "pass", "admin")
    _login(client, "admin3", "pass")
    with patch("services.claude_practice.generate_practice_scenario") as mock_gen:
        rv = client.post(
            "/admin/practice/generate",
            data={"category": "INVALID_CATEGORY", "difficulty": "Beginner"},
            follow_redirects=True,
        )
    mock_gen.assert_not_called()
    assert rv.status_code == 200


# ---------------------------------------------------------------------------
# 6. Invalid difficulty is rejected before any API call
# ---------------------------------------------------------------------------

def test_invalid_difficulty_rejected(client, test_db):
    _create_user(test_db, "admin4", "pass", "admin")
    _login(client, "admin4", "pass")
    with patch("services.claude_practice.generate_practice_scenario") as mock_gen:
        rv = client.post(
            "/admin/practice/generate",
            data={"category": "Networking", "difficulty": "INVALID"},
            follow_redirects=True,
        )
    mock_gen.assert_not_called()
    assert rv.status_code == 200


# ---------------------------------------------------------------------------
# 7. Empty responses are rejected
# ---------------------------------------------------------------------------

def test_empty_response_rejected(client, test_db):
    _create_user(test_db, "admin5", "pass", "admin")
    _login(client, "admin5", "pass")
    scenario_id = _insert_scenario(test_db, "admin5")
    with patch("services.claude_practice.grade_practice_response") as mock_grade:
        rv = client.post(
            f"/admin/practice/scenario/{scenario_id}/submit",
            data={"response_text": ""},
            follow_redirects=True,
        )
    mock_grade.assert_not_called()
    assert rv.status_code == 200


# ---------------------------------------------------------------------------
# 8. Responses over the character limit are rejected
# ---------------------------------------------------------------------------

def test_over_limit_response_rejected(client, test_db):
    _create_user(test_db, "admin6", "pass", "admin")
    _login(client, "admin6", "pass")
    scenario_id = _insert_scenario(test_db, "admin6")
    long_text = "A" * 6000
    with patch.dict(os.environ, {"PRACTICE_MAX_RESPONSE_CHARS": "5000"}):
        with patch("services.claude_practice.grade_practice_response") as mock_grade:
            rv = client.post(
                f"/admin/practice/scenario/{scenario_id}/submit",
                data={"response_text": long_text},
                follow_redirects=True,
            )
    mock_grade.assert_not_called()
    assert rv.status_code == 200


# ---------------------------------------------------------------------------
# 9. Successful generation inserts exactly one scenario
# ---------------------------------------------------------------------------

def test_successful_generation_inserts_one_scenario(client, test_db):
    import app as app_module

    _create_user(test_db, "admin7", "pass", "admin")
    _login(client, "admin7", "pass")

    mock_result = {
        "ticket": {
            "title": "VPN not connecting",
            "description": "User cannot connect to VPN.",
            "category": "Networking",
            "priority": "high",
            "difficulty": "Beginner",
        },
        "answer_key": {"grading_notes": "Check firewall", "likely_causes": []},
        "input_tokens": 200,
        "output_tokens": 400,
        "cost_usd": 0.000002,
    }

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("services.claude_practice.generate_practice_scenario", return_value=mock_result):
            rv = client.post(
                "/admin/practice/generate",
                data={"category": "Networking", "difficulty": "Beginner"},
            )

    # Should redirect to the scenario page
    assert rv.status_code == 302

    original_db = app_module.DB_PATH
    app_module.DB_PATH = test_db
    conn = app_module.get_db()
    count = conn.execute("SELECT COUNT(*) FROM practice_scenarios").fetchone()[0]
    conn.close()
    app_module.DB_PATH = original_db

    assert count == 1


# ---------------------------------------------------------------------------
# 10. Hidden answer key is NOT present in pre-submission HTML
# ---------------------------------------------------------------------------

def test_answer_key_not_in_presub_html(client, test_db):
    _create_user(test_db, "admin8", "pass", "admin")
    _login(client, "admin8", "pass")
    # The answer key contains a distinctive marker
    scenario_id = _insert_scenario(test_db, "admin8", answer_key_content="SECRET_ANSWER_KEY_CONTENT")
    rv = client.get(f"/admin/practice/scenario/{scenario_id}")
    assert rv.status_code == 200
    assert b"SECRET_ANSWER_KEY_CONTENT" not in rv.data


# ---------------------------------------------------------------------------
# 11. Successful grading inserts exactly one attempt
# ---------------------------------------------------------------------------

def test_successful_grading_inserts_one_attempt(client, test_db):
    import app as app_module

    _create_user(test_db, "admin9", "pass", "admin")
    _login(client, "admin9", "pass")
    scenario_id = _insert_scenario(test_db, "admin9")

    mock_grading = {
        "category_scores": {
            "technical_accuracy": 30, "troubleshooting_process": 16,
            "security_and_safety": 12, "completeness_and_escalation": 8,
            "professionalism_and_empathy": 8, "clarity_and_actionability": 8,
        },
        "category_feedback": {
            "technical_accuracy": "Good.", "troubleshooting_process": "OK.",
            "security_and_safety": "Fine.", "completeness_and_escalation": "OK.",
            "professionalism_and_empathy": "Good.", "clarity_and_actionability": "OK.",
        },
        "flags": {
            "requests_or_exposes_credentials": False,
            "dangerous_or_insecure_guidance": False,
            "fundamentally_incorrect_resolution": False,
            "no_meaningful_troubleshooting": False,
        },
        "raw_score": 82,
        "final_score": 82,
        "cap_reason": None,
        "letter_grade": "B",
        "passed": True,
        "strengths": ["Good diagnosis"],
        "technical_errors": [],
        "missing_items": [],
        "security_concerns": [],
        "improvement_steps": [],
        "improved_example_response": "A better response.",
        "input_tokens": 500,
        "output_tokens": 700,
        "cost_usd": 0.000004,
    }

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("services.claude_practice.grade_practice_response", return_value=mock_grading):
            rv = client.post(
                f"/admin/practice/scenario/{scenario_id}/submit",
                data={"response_text": "I would check the printer queue and restart the spooler service."},
            )

    assert rv.status_code == 302

    original_db = app_module.DB_PATH
    app_module.DB_PATH = test_db
    conn = app_module.get_db()
    count = conn.execute("SELECT COUNT(*) FROM practice_attempts").fetchone()[0]
    conn.close()
    app_module.DB_PATH = original_db

    assert count == 1


# ---------------------------------------------------------------------------
# 12–17. Score cap logic (pure unit tests — no HTTP needed)
# ---------------------------------------------------------------------------

from services.claude_practice import apply_score_caps, calculate_letter_grade, calculate_api_cost

NO_FLAGS = {
    "requests_or_exposes_credentials": False,
    "dangerous_or_insecure_guidance": False,
    "fundamentally_incorrect_resolution": False,
    "no_meaningful_troubleshooting": False,
}


def test_no_cap_when_no_flags():
    score, reason = apply_score_caps(85, NO_FLAGS)
    assert score  == 85
    assert reason is None


def test_credential_cap():
    flags = {**NO_FLAGS, "requests_or_exposes_credentials": True}
    score, reason = apply_score_caps(80, flags)
    assert score <= 39
    assert reason is not None


def test_dangerous_guidance_cap():
    flags = {**NO_FLAGS, "dangerous_or_insecure_guidance": True}
    score, reason = apply_score_caps(75, flags)
    assert score <= 39
    assert reason is not None


def test_fundamentally_incorrect_cap():
    flags = {**NO_FLAGS, "fundamentally_incorrect_resolution": True}
    score, reason = apply_score_caps(90, flags)
    assert score <= 59
    assert reason is not None


def test_no_troubleshooting_cap():
    flags = {**NO_FLAGS, "no_meaningful_troubleshooting": True}
    score, reason = apply_score_caps(88, flags)
    assert score <= 69
    assert reason is not None


def test_lowest_cap_wins():
    # Both credential cap (39) and no-troubleshooting cap (69) apply → use 39
    flags = {
        "requests_or_exposes_credentials": True,
        "dangerous_or_insecure_guidance": False,
        "fundamentally_incorrect_resolution": False,
        "no_meaningful_troubleshooting": True,
    }
    score, reason = apply_score_caps(95, flags)
    assert score <= 39


# ---------------------------------------------------------------------------
# 18. Letter grade mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("score,expected", [
    (100, "A+"), (97, "A+"),
    (96,  "A"),  (93, "A"),
    (92,  "A-"), (90, "A-"),
    (89,  "B+"), (87, "B+"),
    (86,  "B"),  (83, "B"),
    (82,  "B-"), (80, "B-"),
    (79,  "C+"), (77, "C+"),
    (76,  "C"),  (73, "C"),
    (72,  "C-"), (70, "C-"),
    (69,  "D"),  (60, "D"),
    (59,  "F"),  (0,  "F"),
])
def test_letter_grades(score, expected):
    assert calculate_letter_grade(score) == expected


# ---------------------------------------------------------------------------
# 19. Pass/fail is based on the final capped score
# ---------------------------------------------------------------------------

def test_pass_at_70():
    flags = {**NO_FLAGS}
    final, _ = apply_score_caps(70, flags)
    assert final >= 70  # pass

def test_fail_at_69():
    flags = {**NO_FLAGS}
    final, _ = apply_score_caps(69, flags)
    assert final < 70  # fail

def test_capped_score_causes_fail():
    # Raw 80 but capped to 39 → fail
    flags = {**NO_FLAGS, "requests_or_exposes_credentials": True}
    final, _ = apply_score_caps(80, flags)
    assert final < 70


# ---------------------------------------------------------------------------
# 20. Cost calculation
# ---------------------------------------------------------------------------

def test_cost_calculation():
    with patch.dict(os.environ, {
        "CLAUDE_INPUT_COST_PER_MILLION": "1.00",
        "CLAUDE_OUTPUT_COST_PER_MILLION": "5.00",
    }):
        cost = calculate_api_cost(1_000_000, 1_000_000)
    assert abs(cost - 6.0) < 1e-9

def test_cost_zero_tokens():
    cost = calculate_api_cost(0, 0)
    assert cost == 0.0

def test_cost_small_request():
    with patch.dict(os.environ, {
        "CLAUDE_INPUT_COST_PER_MILLION": "1.00",
        "CLAUDE_OUTPUT_COST_PER_MILLION": "5.00",
    }):
        cost = calculate_api_cost(500, 300)
    expected = (500 / 1_000_000 * 1.0) + (300 / 1_000_000 * 5.0)
    assert abs(cost - expected) < 1e-12


# ---------------------------------------------------------------------------
# 21. API failure does not insert a partial record
# ---------------------------------------------------------------------------

def test_api_failure_no_partial_scenario(client, test_db):
    import app as app_module
    from services.claude_practice import PracticeLabAPIError

    _create_user(test_db, "admin10", "pass", "admin")
    _login(client, "admin10", "pass")

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("services.claude_practice.generate_practice_scenario",
                   side_effect=PracticeLabAPIError("connection failed")):
            client.post(
                "/admin/practice/generate",
                data={"category": "Networking", "difficulty": "Beginner"},
                follow_redirects=True,
            )

    original_db = app_module.DB_PATH
    app_module.DB_PATH = test_db
    conn = app_module.get_db()
    count = conn.execute("SELECT COUNT(*) FROM practice_scenarios").fetchone()[0]
    conn.close()
    app_module.DB_PATH = original_db

    assert count == 0


def test_api_failure_no_partial_attempt(client, test_db):
    import app as app_module
    from services.claude_practice import PracticeLabAPIError

    _create_user(test_db, "admin11", "pass", "admin")
    _login(client, "admin11", "pass")
    scenario_id = _insert_scenario(test_db, "admin11")

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("services.claude_practice.grade_practice_response",
                   side_effect=PracticeLabAPIError("timeout")):
            client.post(
                f"/admin/practice/scenario/{scenario_id}/submit",
                data={"response_text": "Check the printer drivers and restart the spooler."},
                follow_redirects=True,
            )

    original_db = app_module.DB_PATH
    app_module.DB_PATH = test_db
    conn = app_module.get_db()
    count = conn.execute("SELECT COUNT(*) FROM practice_attempts").fetchone()[0]
    conn.close()
    app_module.DB_PATH = original_db

    assert count == 0


# ---------------------------------------------------------------------------
# 22. One admin cannot view another admin's scenario or result
# ---------------------------------------------------------------------------

def test_cross_admin_scenario_blocked(client, test_db):
    _create_user(test_db, "adminA", "pass", "admin")
    _create_user(test_db, "adminB", "pass", "admin")
    scenario_id = _insert_scenario(test_db, "adminA")

    _login(client, "adminB", "pass")
    rv = client.get(f"/admin/practice/scenario/{scenario_id}")
    assert rv.status_code == 403


def test_cross_admin_result_blocked(client, test_db):
    _create_user(test_db, "adminC", "pass", "admin")
    _create_user(test_db, "adminD", "pass", "admin")
    scenario_id = _insert_scenario(test_db, "adminC")
    attempt_id  = _insert_attempt(test_db, scenario_id, "adminC")

    _login(client, "adminD", "pass")
    rv = client.get(f"/admin/practice/result/{attempt_id}")
    assert rv.status_code == 403


# ---------------------------------------------------------------------------
# 23. GET result page does not trigger another grading call
# ---------------------------------------------------------------------------

def test_result_get_does_not_call_api(client, test_db):
    _create_user(test_db, "admin12", "pass", "admin")
    _login(client, "admin12", "pass")
    scenario_id = _insert_scenario(test_db, "admin12")
    attempt_id  = _insert_attempt(test_db, scenario_id, "admin12")

    with patch("services.claude_practice.grade_practice_response") as mock_grade:
        rv = client.get(f"/admin/practice/result/{attempt_id}")

    assert rv.status_code == 200
    mock_grade.assert_not_called()


# ---------------------------------------------------------------------------
# 24. Existing routes still work
# ---------------------------------------------------------------------------

def test_login_still_works(client, test_db):
    _create_user(test_db, "alice", "pass", "user")
    rv = client.post("/login", data={"username": "alice", "password": "pass"})
    assert rv.status_code == 302


def test_dashboard_still_works(client, test_db):
    _create_user(test_db, "bob", "pass", "user")
    _login(client, "bob", "pass")
    rv = client.get("/dashboard")
    assert rv.status_code == 200


def test_admin_dashboard_still_works(client, test_db):
    _create_user(test_db, "carol", "pass", "admin")
    _login(client, "carol", "pass")
    rv = client.get("/admin")
    assert rv.status_code == 200
    # Practice Lab link should be present
    assert b"Practice Lab" in rv.data


def test_submit_ticket_still_works(client, test_db):
    _create_user(test_db, "dave", "pass", "user")
    _login(client, "dave", "pass")
    rv = client.post(
        "/submit",
        data={"title": "My keyboard broke", "description": "Keys stopped working.", "priority": "low"},
        follow_redirects=True,
    )
    assert rv.status_code == 200


def test_admin_tickets_still_works(client, test_db):
    _create_user(test_db, "eve", "pass", "admin")
    _login(client, "eve", "pass")
    rv = client.get("/admin/tickets")
    assert rv.status_code == 200


# ---------------------------------------------------------------------------
# 25–32. Grading pipeline validation (unit + integration)
# ---------------------------------------------------------------------------

from services.claude_practice import _validate_category_scores, PracticeLabResponseError

_FULL_SCORES = {
    "technical_accuracy":          28,
    "troubleshooting_process":     15,
    "security_and_safety":         12,
    "completeness_and_escalation":  8,
    "professionalism_and_empathy":  9,
    "clarity_and_actionability":    7,
}


def test_validate_scores_valid_integers_correct_sum():
    """Valid integer scores produce the correct clamped values and correct total."""
    result = _validate_category_scores(_FULL_SCORES)
    assert result["technical_accuracy"] == 28
    assert result["troubleshooting_process"] == 15
    assert sum(result.values()) == 79   # 28+15+12+8+9+7


def test_validate_scores_empty_dict_raises():
    """Empty dict must raise PracticeLabResponseError — never silently return zeros."""
    with pytest.raises(PracticeLabResponseError, match="missing the category_scores"):
        _validate_category_scores({})


def test_validate_scores_missing_one_field_raises():
    """A response missing a single required key must raise, naming the missing field."""
    incomplete = {k: v for k, v in _FULL_SCORES.items() if k != "security_and_safety"}
    with pytest.raises(PracticeLabResponseError, match="security_and_safety"):
        _validate_category_scores(incomplete)


def test_validate_scores_wrong_field_names_raises():
    """camelCase or otherwise renamed keys must raise — not silently default to 0."""
    wrong_names = {
        "technicalAccuracy":          28,
        "troubleshootingProcess":     15,
        "securityAndSafety":          12,
        "completenessAndEscalation":   8,
        "professionalismAndEmpathy":   9,
        "clarityAndActionability":     7,
    }
    with pytest.raises(PracticeLabResponseError):
        _validate_category_scores(wrong_names)


def test_validate_scores_string_fraction_parsed():
    """Strings like '28/35' are parsed by extracting the leading integer."""
    string_scores = {k: f"{v}/100" for k, v in _FULL_SCORES.items()}
    result = _validate_category_scores(string_scores)
    assert result["technical_accuracy"] == 28
    assert result["troubleshooting_process"] == 15
    assert sum(result.values()) == 79


def test_validate_scores_over_max_clamped():
    """Scores that exceed the per-category maximum are clamped, not rejected."""
    over_max = dict(_FULL_SCORES)
    over_max["technical_accuracy"] = 40   # max is 35
    over_max["troubleshooting_process"] = 25  # max is 20
    result = _validate_category_scores(over_max)
    assert result["technical_accuracy"] == 35
    assert result["troubleshooting_process"] == 20


def test_total_score_matches_sum_of_categories():
    """Python's sum of individual category scores must equal what the route stores as raw_score."""
    result = _validate_category_scores(_FULL_SCORES)
    assert sum(result.values()) == sum(_FULL_SCORES.values())


def test_category_scores_db_round_trip(client, test_db):
    """All six category scores survive a save-to-DB and read-back cycle unchanged."""
    import app as app_module

    _create_user(test_db, "admin_rt", "pass", "admin")
    _login(client, "admin_rt", "pass")
    scenario_id = _insert_scenario(test_db, "admin_rt")

    expected_scores = dict(_FULL_SCORES)
    mock_grading = {
        "category_scores": expected_scores,
        "category_feedback": {k: "OK." for k in expected_scores},
        "flags": {
            "requests_or_exposes_credentials":    False,
            "dangerous_or_insecure_guidance":     False,
            "fundamentally_incorrect_resolution": False,
            "no_meaningful_troubleshooting":      False,
        },
        "raw_score":   sum(expected_scores.values()),
        "final_score": sum(expected_scores.values()),
        "cap_reason":  None,
        "letter_grade": "C+",
        "passed": True,
        "strengths": [],
        "technical_errors": [],
        "missing_items": [],
        "security_concerns": [],
        "improvement_steps": [],
        "improved_example_response": "",
        "input_tokens": 500,
        "output_tokens": 700,
        "cost_usd": 0.000004,
    }

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("services.claude_practice.grade_practice_response", return_value=mock_grading):
            rv = client.post(
                f"/admin/practice/scenario/{scenario_id}/submit",
                data={"response_text": "Check the printer queue and restart the spooler service."},
            )

    assert rv.status_code == 302

    original_db = app_module.DB_PATH
    app_module.DB_PATH = test_db
    conn = app_module.get_db()
    row = conn.execute(
        "SELECT category_scores_json FROM practice_attempts ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    app_module.DB_PATH = original_db

    saved = json.loads(row["category_scores_json"])
    assert saved == expected_scores


# ---------------------------------------------------------------------------
# 33–35. Employee name pool and deque-backed picker
# ---------------------------------------------------------------------------

from services.claude_practice import (
    EMPLOYEE_NAME_POOL, _pick_employee_name, _recent_names,
)


def test_pick_name_returns_pool_member():
    """Every call must return a name from the defined pool."""
    for _ in range(20):
        assert _pick_employee_name() in EMPLOYEE_NAME_POOL


def test_consecutive_picks_never_repeat():
    """Two consecutive picks must not return the same name."""
    _recent_names.clear()
    first = _pick_employee_name()
    second = _pick_employee_name()
    assert first != second, f"Got '{first}' twice in a row"


def test_name_not_reused_within_window():
    """A name must not reappear within the 10-pick recent window."""
    _recent_names.clear()
    # Draw half the pool; with maxlen=10 each name should be excluded once picked
    history = [_pick_employee_name() for _ in range(min(10, len(EMPLOYEE_NAME_POOL)))]
    for i, name in enumerate(history):
        earlier = history[:i]
        assert name not in earlier, (
            f"'{name}' reused within {i} picks (full history: {history})"
        )


# ---------------------------------------------------------------------------
# 36–50. Grading pipeline resilience: special characters, JSON extraction, retry
# ---------------------------------------------------------------------------

from services.claude_practice import _extract_json, grade_practice_response

# Shared fixtures for unit-level grading tests
_PUBLIC_TICKET_STUB = {
    "title":       "Printer offline",
    "description": "The printer in Room 3 is offline.",
    "category":    "Printers",
    "priority":    "medium",
    "difficulty":  "Beginner",
}
_ANSWER_KEY_STUB = {
    "grading_notes": "Check the print spooler.",
    "likely_causes": ["Paper jam", "Driver issue"],
}

_VALID_GRADING_PAYLOAD = {
    "category_scores": {
        "technical_accuracy":          28,
        "troubleshooting_process":     15,
        "security_and_safety":         12,
        "completeness_and_escalation":  8,
        "professionalism_and_empathy":  9,
        "clarity_and_actionability":    7,
    },
    "category_feedback": {k: "OK." for k in [
        "technical_accuracy", "troubleshooting_process", "security_and_safety",
        "completeness_and_escalation", "professionalism_and_empathy", "clarity_and_actionability",
    ]},
    "flags": {
        "requests_or_exposes_credentials":    False,
        "dangerous_or_insecure_guidance":     False,
        "fundamentally_incorrect_resolution": False,
        "no_meaningful_troubleshooting":      False,
    },
    "strengths":                 ["Correct diagnosis"],
    "technical_errors":          [],
    "missing_items":             [],
    "security_concerns":         [],
    "improvement_steps":         [],
    "improved_example_response": "A better response.",
}
_VALID_GRADING_JSON = json.dumps(_VALID_GRADING_PAYLOAD)


def _make_mock_client(response_text, stop_reason="end_turn",
                      input_tokens=500, output_tokens=700):
    """Return a mock Anthropic client whose messages.create returns the given text."""
    content_block = MagicMock()
    content_block.text = response_text

    mock_resp = MagicMock()
    mock_resp.content = [content_block]
    mock_resp.stop_reason = stop_reason
    mock_resp.usage.input_tokens  = input_tokens
    mock_resp.usage.output_tokens = output_tokens

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_resp
    return mock_client


# ── _extract_json unit tests ────────────────────────────────────────────────

def test_extract_json_plain():
    """Plain JSON is returned unchanged."""
    result = _extract_json(_VALID_GRADING_JSON)
    assert json.loads(result)["category_scores"]["technical_accuracy"] == 28


def test_extract_json_from_code_fence():
    """JSON inside a ```json fence is extracted correctly."""
    fenced = f"```json\n{_VALID_GRADING_JSON}\n```"
    result = _extract_json(fenced)
    assert json.loads(result)["category_scores"]["technical_accuracy"] == 28


def test_extract_json_fence_after_preamble():
    """Preamble text before a ```json fence is stripped."""
    text = f"Here is my evaluation:\n\n```json\n{_VALID_GRADING_JSON}\n```\n"
    result = _extract_json(text)
    assert json.loads(result)["category_scores"]["technical_accuracy"] == 28


def test_extract_json_bare_brace_after_preamble():
    """Preamble text before a bare JSON object is stripped."""
    text = f"Sure, here is the grading:\n\n{_VALID_GRADING_JSON}"
    result = _extract_json(text)
    assert json.loads(result)["category_scores"]["technical_accuracy"] == 28


def test_extract_json_fence_no_language_tag():
    """Code fence without a language tag (``` only) is handled."""
    fenced = f"```\n{_VALID_GRADING_JSON}\n```"
    result = _extract_json(fenced)
    assert json.loads(result)["category_scores"]["technical_accuracy"] == 28


# ── Special-character inputs ─────────────────────────────────────────────────

@pytest.mark.parametrize("special_response", [
    "Simple plain text response about checking the printer queue.",
    "Response with\nmultiple\nlines\nof text.",
    "# Heading\n## Subheading\n**Bold** and *italic* and ~~strikethrough~~.",
    'Response with "double quotes" in the text.',
    'Braces everywhere: {key: value} and {{double}} and {"json": true}.',
    "Backslashes: C:\\Users\\Admin\\file.txt and \\n escaped newline.",
    "```python\nprint('hello world')\n```\nThis is a code block.",
    ':::writing{variant="chat_message" id="58314"}\nSome AI-generated content here.',
    (
        'Mixed: "quotes", {braces}, \\backslash\\, \ttab\n newline, '
        ':::writing{variant="chat_message" id="99999"} end.'
    ),
])
def test_special_chars_in_response_text_do_not_crash(special_response):
    """
    grade_practice_response must accept any text content without crashing.
    Special characters in the trainee response are serialised by the SDK — they
    cannot corrupt the API request.  The mock returns valid grading JSON.
    """
    mock_client = _make_mock_client(_VALID_GRADING_JSON)
    with patch("services.claude_practice.get_anthropic_client", return_value=mock_client):
        result = grade_practice_response(
            _PUBLIC_TICKET_STUB, _ANSWER_KEY_STUB, special_response
        )
    assert result["raw_score"] == 79      # 28+15+12+8+9+7
    assert result["letter_grade"] is not None
    assert result["input_tokens"] == 500


# ── Retry logic ──────────────────────────────────────────────────────────────

def test_grading_retries_once_on_malformed_json():
    """If the first response is invalid JSON, grade_practice_response retries exactly once."""
    call_results = [
        _make_mock_client("not JSON at all — this will break json.loads"),
        _make_mock_client(_VALID_GRADING_JSON),
    ]
    call_index = [0]

    def side_effect(**kwargs):
        resp = call_results[call_index[0]].messages.create.return_value
        call_index[0] += 1
        return resp

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = side_effect

    with patch("services.claude_practice.get_anthropic_client", return_value=mock_client):
        result = grade_practice_response(
            _PUBLIC_TICKET_STUB, _ANSWER_KEY_STUB, "A normal response."
        )

    assert mock_client.messages.create.call_count == 2
    assert result["raw_score"] == 79


def test_grading_raises_after_two_failures():
    """If both the initial call and the retry return invalid JSON, raise PracticeLabResponseError."""
    from services.claude_practice import PracticeLabResponseError

    mock_client = _make_mock_client("still not JSON")
    with patch("services.claude_practice.get_anthropic_client", return_value=mock_client):
        with pytest.raises(PracticeLabResponseError, match="invalid JSON"):
            grade_practice_response(
                _PUBLIC_TICKET_STUB, _ANSWER_KEY_STUB, "A response."
            )

    assert mock_client.messages.create.call_count == 2


def test_grading_retry_accumulates_token_cost():
    """Token counts from both the initial call and the retry are summed."""
    call_results = [
        _make_mock_client("bad json", input_tokens=300, output_tokens=100),
        _make_mock_client(_VALID_GRADING_JSON, input_tokens=400, output_tokens=600),
    ]
    call_index = [0]

    def side_effect(**kwargs):
        resp = call_results[call_index[0]].messages.create.return_value
        call_index[0] += 1
        return resp

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = side_effect

    with patch("services.claude_practice.get_anthropic_client", return_value=mock_client):
        result = grade_practice_response(
            _PUBLIC_TICKET_STUB, _ANSWER_KEY_STUB, "A response."
        )

    assert result["input_tokens"]  == 700   # 300 + 400
    assert result["output_tokens"] == 700   # 100 + 600


# ── Truncated output ─────────────────────────────────────────────────────────

def test_grading_raises_on_truncated_output():
    """A response cut off by max_tokens raises PracticeLabResponseError before JSON parse."""
    from services.claude_practice import PracticeLabResponseError

    mock_client = _make_mock_client(
        '{"category_scores": {"technical_accuracy": 25',   # truncated mid-JSON
        stop_reason="max_tokens",
    )
    with patch("services.claude_practice.get_anthropic_client", return_value=mock_client):
        with pytest.raises(PracticeLabResponseError, match="cut off"):
            grade_practice_response(
                _PUBLIC_TICKET_STUB, _ANSWER_KEY_STUB, "A response."
            )
