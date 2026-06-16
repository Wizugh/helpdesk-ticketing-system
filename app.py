import json
import os
from datetime import datetime

# Load .env file before anything reads os.environ (harmless when vars already set by Docker)
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, flash, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3

# Defaults to database.db for local development.
# Set DATABASE_PATH in the environment to redirect to a Docker volume.
DB_PATH = os.environ.get('DATABASE_PATH', 'database.db')


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-only-key-change-in-production')


# ---------------------------------------------------------------------------
# Database Helpers
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    # row_factory lets us access columns by name, e.g. row['title'],
    # instead of by numeric index like row[1]
    conn.row_factory = sqlite3.Row
    # Enforce referential integrity for foreign keys used by practice tables
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables on first run if they do not already exist."""
    conn = get_db()

    # ── Core helpdesk tables ─────────────────────────────────────────────────

    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT    UNIQUE NOT NULL,
            password TEXT    NOT NULL,
            role     TEXT    NOT NULL DEFAULT 'user'
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT    NOT NULL,
            description TEXT    NOT NULL,
            priority    TEXT    NOT NULL DEFAULT 'low',
            status      TEXT    NOT NULL DEFAULT 'open',
            created_by  TEXT    NOT NULL,
            date        TEXT    NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            author    TEXT    NOT NULL,
            body      TEXT    NOT NULL,
            date      TEXT    NOT NULL,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id)
        )
    ''')

    # ── Practice Lab tables ──────────────────────────────────────────────────
    # These are completely isolated from the real helpdesk tables above.

    conn.execute('''
        CREATE TABLE IF NOT EXISTS practice_scenarios (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            title                    TEXT    NOT NULL,
            description              TEXT    NOT NULL,
            category                 TEXT    NOT NULL,
            priority                 TEXT    NOT NULL,
            difficulty               TEXT    NOT NULL,
            answer_key_json          TEXT    NOT NULL,
            generated_by             TEXT    NOT NULL,
            created_at               TEXT    NOT NULL,
            generation_input_tokens  INTEGER NOT NULL DEFAULT 0,
            generation_output_tokens INTEGER NOT NULL DEFAULT 0,
            generation_cost_usd      REAL    NOT NULL DEFAULT 0
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS practice_attempts (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_id          INTEGER NOT NULL,
            admin_username       TEXT    NOT NULL,
            response_text        TEXT    NOT NULL,
            raw_score            INTEGER NOT NULL,
            final_score          INTEGER NOT NULL,
            letter_grade         TEXT    NOT NULL,
            passed               INTEGER NOT NULL,
            score_cap_reason     TEXT,
            category_scores_json TEXT    NOT NULL,
            feedback_json        TEXT    NOT NULL,
            grading_input_tokens  INTEGER NOT NULL DEFAULT 0,
            grading_output_tokens INTEGER NOT NULL DEFAULT 0,
            grading_cost_usd     REAL    NOT NULL DEFAULT 0,
            submitted_at         TEXT    NOT NULL,
            FOREIGN KEY (scenario_id) REFERENCES practice_scenarios(id)
        )
    ''')

    # Indexes that speed up the per-admin queries used in the Practice Lab
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_scenarios_generated_by '
        'ON practice_scenarios (generated_by)'
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_scenarios_created '
        'ON practice_scenarios (created_at)'
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_attempts_admin '
        'ON practice_attempts (admin_username)'
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_attempts_scenario '
        'ON practice_attempts (scenario_id)'
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_attempts_submitted '
        'ON practice_attempts (submitted_at)'
    )

    conn.commit()
    conn.close()


def migrate_db():
    """Add columns introduced after the initial schema.

    ALTER TABLE raises an error if the column already exists, so we catch
    and ignore that — it is the expected outcome on every run after the first.
    """
    conn = get_db()
    try:
        conn.execute('ALTER TABLE tickets ADD COLUMN assigned_to TEXT DEFAULT NULL')
        conn.commit()
    except Exception:
        pass
    conn.close()


# Run once at startup to ensure the database and schema are ready
init_db()
migrate_db()


# ---------------------------------------------------------------------------
# Practice Lab Helpers
# ---------------------------------------------------------------------------

def admin_is_authenticated():
    """Return True when the current session belongs to a logged-in admin."""
    return session.get('role') == 'admin' and 'user' in session


def get_public_scenario(scenario_row):
    """Return only the safe public fields of a scenario row (no answer key)."""
    return {
        "id":          scenario_row["id"],
        "title":       scenario_row["title"],
        "description": scenario_row["description"],
        "category":    scenario_row["category"],
        "priority":    scenario_row["priority"],
        "difficulty":  scenario_row["difficulty"],
        "created_at":  scenario_row["created_at"],
    }


def parse_json_column(text):
    """Safely parse a JSON text column. Returns an empty dict on any error."""
    if not text:
        return {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


def get_practice_usage_stats(conn):
    """Aggregate token usage and cost across ALL practice scenarios and attempts."""
    gen = conn.execute('''
        SELECT
            COALESCE(SUM(generation_input_tokens),  0) AS total_input,
            COALESCE(SUM(generation_output_tokens), 0) AS total_output,
            COALESCE(SUM(generation_cost_usd),      0) AS total_cost,
            COUNT(*) AS scenario_count
        FROM practice_scenarios
    ''').fetchone()

    grade = conn.execute('''
        SELECT
            COALESCE(SUM(grading_input_tokens),  0) AS total_input,
            COALESCE(SUM(grading_output_tokens), 0) AS total_output,
            COALESCE(SUM(grading_cost_usd),      0) AS total_cost,
            COUNT(*) AS attempt_count
        FROM practice_attempts
    ''').fetchone()

    return {
        "total_input_tokens":  gen["total_input"]  + grade["total_input"],
        "total_output_tokens": gen["total_output"] + grade["total_output"],
        "generation_cost":     gen["total_cost"],
        "grading_cost":        grade["total_cost"],
        "total_cost":          gen["total_cost"] + grade["total_cost"],
        "scenario_count":      gen["scenario_count"],
        "attempt_count":       grade["attempt_count"],
    }


def get_daily_api_call_count(conn, admin_username, today_str):
    """Count successful API calls made today by this admin (generations + gradings)."""
    gen_count = conn.execute(
        "SELECT COUNT(*) FROM practice_scenarios "
        "WHERE generated_by = ? AND created_at LIKE ?",
        (admin_username, today_str + '%')
    ).fetchone()[0]

    grade_count = conn.execute(
        "SELECT COUNT(*) FROM practice_attempts "
        "WHERE admin_username = ? AND submitted_at LIKE ?",
        (admin_username, today_str + '%')
    ).fetchone()[0]

    return gen_count + grade_count


def check_budget_and_daily_limit(conn, admin_username, today_str):
    """
    Return (True, None) when the request may proceed.
    Return (False, message) when the budget or daily limit has been reached.
    """
    from services.claude_practice import _get_config
    cfg   = _get_config()
    stats = get_practice_usage_stats(conn)

    if stats["total_cost"] >= cfg["budget"]:
        msg = (
            f"The configured local Practice Lab budget of ${cfg['budget']:.2f} "
            f"has been reached (estimated total spend: ${stats['total_cost']:.6f} USD). "
            "This is an estimate based on calls recorded by this application. "
            "Update PRACTICE_BUDGET_USD in your .env to raise the limit."
        )
        return False, msg

    daily_count = get_daily_api_call_count(conn, admin_username, today_str)
    if daily_count >= cfg["daily_limit"]:
        msg = (
            f"You have reached today's API call limit of {cfg['daily_limit']}. "
            "This limit resets at midnight. "
            "Update PRACTICE_DAILY_API_CALL_LIMIT in your .env to change the limit."
        )
        return False, msg

    return True, None


# ---------------------------------------------------------------------------
# Authentication Routes
# ---------------------------------------------------------------------------

@app.route('/')
def home():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db()
        user = conn.execute(
            'SELECT * FROM users WHERE username = ?', (username,)
        ).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['user'] = username
            session['role'] = user['role']
            if user['role'] == 'admin':
                return redirect(url_for('admin'))
            return redirect(url_for('dashboard'))
        error = 'Invalid username or password'
    return render_template('login.html', error=error)


@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        # Hash the password before saving — plain text is never stored
        password = generate_password_hash(request.form['password'])
        try:
            conn = get_db()
            conn.execute(
                'INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
                (username, password, 'user')
            )
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except Exception:
            error = 'Username already exists'
    return render_template('register.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ---------------------------------------------------------------------------
# User Routes
# ---------------------------------------------------------------------------

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    recent_tickets = conn.execute(
        'SELECT * FROM tickets WHERE created_by = ? ORDER BY date DESC LIMIT 5',
        (session['user'],)
    ).fetchall()
    conn.close()
    return render_template('dashboard.html', username=session['user'], recent_tickets=recent_tickets)


@app.route('/submit', methods=['GET', 'POST'])
def submit_ticket():
    if 'user' not in session:
        return redirect(url_for('login'))
    success = None
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        priority = request.form['priority']
        date = datetime.now().strftime('%Y-%m-%d %H:%M')
        conn = get_db()
        conn.execute(
            '''INSERT INTO tickets (title, description, priority, status, created_by, date)
               VALUES (?, ?, ?, 'open', ?, ?)''',
            (title, description, priority, session['user'], date)
        )
        conn.commit()
        conn.close()
        success = 'Ticket submitted successfully'
    return render_template('submit_ticket.html', success=success)


@app.route('/mytickets')
def my_tickets():
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    tickets = conn.execute(
        'SELECT * FROM tickets WHERE created_by = ? ORDER BY date DESC',
        (session['user'],)
    ).fetchall()
    conn.close()
    return render_template('mytickets.html', tickets=tickets)


@app.route('/ticket/<int:ticket_id>')
def ticket_detail(ticket_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    ticket = conn.execute(
        'SELECT * FROM tickets WHERE id = ?', (ticket_id,)
    ).fetchone()
    if ticket is None:
        conn.close()
        return 'Ticket not found', 404
    # Regular users can only view their own tickets; admins can view all
    if session['role'] != 'admin' and ticket['created_by'] != session['user']:
        conn.close()
        return 'Access denied', 403
    comments = conn.execute(
        'SELECT * FROM comments WHERE ticket_id = ? ORDER BY date ASC',
        (ticket_id,)
    ).fetchall()
    conn.close()
    return render_template('ticket_detail.html', ticket=ticket, comments=comments)


@app.route('/ticket/<int:ticket_id>/comment', methods=['POST'])
def post_comment(ticket_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    body = request.form.get('body', '').strip()
    if not body:
        return redirect(url_for('ticket_detail', ticket_id=ticket_id))
    conn = get_db()
    ticket = conn.execute(
        'SELECT * FROM tickets WHERE id = ?', (ticket_id,)
    ).fetchone()
    if ticket is None:
        conn.close()
        return 'Ticket not found', 404
    # Admins can comment on any ticket; regular users can only comment on their own
    if session['role'] != 'admin' and ticket['created_by'] != session['user']:
        conn.close()
        return 'Access denied', 403
    date = datetime.now().strftime('%Y-%m-%d %H:%M')
    conn.execute(
        'INSERT INTO comments (ticket_id, author, body, date) VALUES (?, ?, ?, ?)',
        (ticket_id, session['user'], body, date)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))


@app.route('/ticket/<int:ticket_id>/close', methods=['POST'])
def close_ticket(ticket_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    ticket = conn.execute(
        'SELECT * FROM tickets WHERE id = ?', (ticket_id,)
    ).fetchone()
    if ticket is None:
        conn.close()
        return 'Ticket not found', 404
    # Only the ticket's original submitter can close it
    if ticket['created_by'] != session['user']:
        conn.close()
        return 'Access denied', 403
    if ticket['status'] == 'closed':
        conn.close()
        return redirect(url_for('ticket_detail', ticket_id=ticket_id))
    date = datetime.now().strftime('%Y-%m-%d %H:%M')
    conn.execute(
        "UPDATE tickets SET status = 'closed' WHERE id = ?", (ticket_id,)
    )
    conn.execute(
        'INSERT INTO comments (ticket_id, author, body, date) VALUES (?, ?, ?, ?)',
        (ticket_id, 'System', f'Ticket closed by {session["user"]}', date)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))


# ---------------------------------------------------------------------------
# Admin Routes
# ---------------------------------------------------------------------------

@app.route('/admin')
def admin():
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    conn = get_db()
    # SUM(CASE WHEN ...) counts rows matching each condition in a single query,
    # avoiding multiple round-trips to the database
    stats = conn.execute('''
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = "open"        THEN 1 ELSE 0 END) AS open_count,
            SUM(CASE WHEN status = "in progress" THEN 1 ELSE 0 END) AS in_progress_count,
            SUM(CASE WHEN status = "resolved"    THEN 1 ELSE 0 END) AS resolved_count,
            SUM(CASE WHEN status = "closed"      THEN 1 ELSE 0 END) AS closed_count,
            SUM(CASE WHEN priority = "high"   AND status NOT IN ("resolved", "closed") THEN 1 ELSE 0 END) AS high_open,
            SUM(CASE WHEN priority = "medium" AND status NOT IN ("resolved", "closed") THEN 1 ELSE 0 END) AS medium_open,
            SUM(CASE WHEN priority = "low"    AND status NOT IN ("resolved", "closed") THEN 1 ELSE 0 END) AS low_open
        FROM tickets
    ''').fetchone()
    recent_tickets = conn.execute(
        'SELECT * FROM tickets ORDER BY date DESC LIMIT 5'
    ).fetchall()
    conn.close()
    return render_template(
        'admin.html',
        username=session['user'],
        stats=stats,
        recent_tickets=recent_tickets
    )


@app.route('/admin/tickets')
def admin_tickets():
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    status_filter = request.args.get('status', 'all')
    priority_filter = request.args.get('priority', 'all')
    # Build the WHERE clause dynamically based on which filters are active
    query = 'SELECT * FROM tickets'
    filters = []
    params = []
    if status_filter != 'all':
        filters.append('status = ?')
        params.append(status_filter)
    if priority_filter != 'all':
        filters.append('priority = ?')
        params.append(priority_filter)
    if filters:
        query += ' WHERE ' + ' AND '.join(filters)
    query += ' ORDER BY date DESC'
    conn = get_db()
    tickets = conn.execute(query, params).fetchall()
    conn.close()
    return render_template(
        'admin_tickets.html',
        tickets=tickets,
        status_filter=status_filter,
        priority_filter=priority_filter
    )


@app.route('/admin/update/<int:ticket_id>', methods=['POST'])
def update_ticket(ticket_id):
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    new_status = request.form['status']
    assigned_to = request.form.get('assigned_to', '').strip() or None
    date = datetime.now().strftime('%Y-%m-%d %H:%M')
    conn = get_db()
    ticket = conn.execute(
        'SELECT status, assigned_to FROM tickets WHERE id = ?', (ticket_id,)
    ).fetchone()
    # Record an audit log entry for each field that actually changed
    log_entries = []
    if ticket['status'] != new_status:
        log_entries.append(
            f"Status changed from {ticket['status'].title()} "
            f"to {new_status.title()} by {session['user']}"
        )
    old_assigned = ticket['assigned_to'] or 'Unassigned'
    new_assigned = assigned_to or 'Unassigned'
    if old_assigned != new_assigned:
        log_entries.append(f"Assigned to {new_assigned} by {session['user']}")
    conn.execute(
        'UPDATE tickets SET status = ?, assigned_to = ? WHERE id = ?',
        (new_status, assigned_to, ticket_id)
    )
    for entry in log_entries:
        conn.execute(
            'INSERT INTO comments (ticket_id, author, body, date) VALUES (?, ?, ?, ?)',
            (ticket_id, 'System', entry, date)
        )
    conn.commit()
    conn.close()
    return redirect(url_for('admin_tickets'))


# ---------------------------------------------------------------------------
# Practice Lab Routes
# ---------------------------------------------------------------------------

@app.route('/admin/practice')
def admin_practice():
    if not admin_is_authenticated():
        return redirect(url_for('login'))

    from services.claude_practice import (
        api_key_is_configured, VALID_CATEGORIES, VALID_DIFFICULTIES, _get_config
    )

    conn = get_db()
    usage_stats = get_practice_usage_stats(conn)

    # Per-admin attempt history (most recent 20)
    attempts = conn.execute('''
        SELECT
            pa.id, pa.scenario_id, pa.final_score, pa.letter_grade,
            pa.passed, pa.submitted_at, pa.raw_score,
            ps.title, ps.category, ps.difficulty
        FROM practice_attempts pa
        JOIN practice_scenarios ps ON pa.scenario_id = ps.id
        WHERE pa.admin_username = ?
        ORDER BY pa.submitted_at DESC
        LIMIT 20
    ''', (session['user'],)).fetchall()

    attempt_stats = conn.execute('''
        SELECT
            COUNT(*) AS total_attempts,
            COALESCE(AVG(final_score), 0) AS avg_score,
            COALESCE(MAX(final_score), 0) AS best_score
        FROM practice_attempts
        WHERE admin_username = ?
    ''', (session['user'],)).fetchone()

    conn.close()

    cfg = _get_config()
    budget_remaining = max(0.0, cfg["budget"] - usage_stats["total_cost"])

    # Sort categories with "Random" first, then alphabetical
    sorted_cats = ["Random"] + sorted(c for c in VALID_CATEGORIES if c != "Random")

    return render_template(
        'admin_practice.html',
        api_key_set=api_key_is_configured(),
        categories=sorted_cats,
        difficulties=sorted(VALID_DIFFICULTIES),
        usage_stats=usage_stats,
        attempts=attempts,
        attempt_stats=attempt_stats,
        budget_usd=cfg["budget"],
        budget_remaining=budget_remaining,
    )


@app.route('/admin/practice/generate', methods=['POST'])
def practice_generate():
    """Generate a new practice scenario via Claude (POST only — never GET)."""
    if not admin_is_authenticated():
        return redirect(url_for('login'))

    from services.claude_practice import (
        generate_practice_scenario, VALID_CATEGORIES, VALID_DIFFICULTIES,
        api_key_is_configured, PracticeLabConfigError,
        PracticeLabAPIError, PracticeLabResponseError,
    )

    if not api_key_is_configured():
        flash("ANTHROPIC_API_KEY is not configured. Add it to your .env file.", "error")
        return redirect(url_for('admin_practice'))

    category   = request.form.get('category',   '').strip()
    difficulty = request.form.get('difficulty', '').strip()

    if category not in VALID_CATEGORIES:
        flash("Invalid category selected.", "error")
        return redirect(url_for('admin_practice'))
    if difficulty not in VALID_DIFFICULTIES:
        flash("Invalid difficulty selected.", "error")
        return redirect(url_for('admin_practice'))

    today_str = datetime.now().strftime('%Y-%m-%d')
    conn = get_db()
    budget_ok, budget_msg = check_budget_and_daily_limit(conn, session['user'], today_str)
    if not budget_ok:
        conn.close()
        flash(budget_msg, "error")
        return redirect(url_for('admin_practice'))

    try:
        result = generate_practice_scenario(category, difficulty)
    except PracticeLabConfigError as exc:
        conn.close()
        flash(str(exc), "error")
        return redirect(url_for('admin_practice'))
    except (PracticeLabAPIError, PracticeLabResponseError) as exc:
        conn.close()
        flash(f"Could not generate scenario: {exc}", "error")
        return redirect(url_for('admin_practice'))

    ticket     = result["ticket"]
    answer_key = result["answer_key"]
    now        = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Only save after receiving a complete, validated response
    cursor = conn.execute('''
        INSERT INTO practice_scenarios
            (title, description, category, priority, difficulty,
             answer_key_json, generated_by, created_at,
             generation_input_tokens, generation_output_tokens, generation_cost_usd)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        ticket["title"],
        ticket["description"],
        ticket["category"],
        ticket["priority"],
        ticket["difficulty"],
        json.dumps(answer_key),
        session['user'],
        now,
        result["input_tokens"],
        result["output_tokens"],
        result["cost_usd"],
    ))
    conn.commit()
    scenario_id = cursor.lastrowid
    conn.close()

    # POST-Redirect-GET: redirect so a page refresh does not repeat the API call
    return redirect(url_for('practice_scenario', scenario_id=scenario_id))


@app.route('/admin/practice/scenario/<int:scenario_id>')
def practice_scenario(scenario_id):
    """Display the public practice ticket and response form (no answer key in template)."""
    if not admin_is_authenticated():
        return redirect(url_for('login'))

    from services.claude_practice import _get_config
    cfg = _get_config()

    conn = get_db()
    scenario = conn.execute(
        'SELECT * FROM practice_scenarios WHERE id = ?', (scenario_id,)
    ).fetchone()
    conn.close()

    if scenario is None:
        return 'Scenario not found', 404
    if scenario['generated_by'] != session['user']:
        return 'Access denied', 403

    # Only safe public fields are passed — answer_key_json stays in the database
    public = get_public_scenario(scenario)

    return render_template(
        'practice_scenario.html',
        scenario=public,
        max_chars=cfg["max_chars"],
    )


@app.route('/admin/practice/scenario/<int:scenario_id>/submit', methods=['POST'])
def practice_submit(scenario_id):
    """Grade the admin's response via Claude and save the attempt (POST only)."""
    if not admin_is_authenticated():
        return redirect(url_for('login'))

    from services.claude_practice import (
        grade_practice_response, api_key_is_configured, _get_config,
        PracticeLabConfigError, PracticeLabAPIError, PracticeLabResponseError,
    )
    cfg = _get_config()

    conn = get_db()
    scenario = conn.execute(
        'SELECT * FROM practice_scenarios WHERE id = ?', (scenario_id,)
    ).fetchone()

    if scenario is None:
        conn.close()
        return 'Scenario not found', 404
    if scenario['generated_by'] != session['user']:
        conn.close()
        return 'Access denied', 403

    response_text = request.form.get('response_text', '').strip()

    # Server-side validation — never call the API for invalid input
    if not response_text:
        flash("Response cannot be empty.", "error")
        conn.close()
        return redirect(url_for('practice_scenario', scenario_id=scenario_id))
    if len(response_text) < 20:
        flash("Response is too short (minimum 20 characters).", "error")
        conn.close()
        return redirect(url_for('practice_scenario', scenario_id=scenario_id))
    if len(response_text) > cfg["max_chars"]:
        flash(
            f"Response exceeds the {cfg['max_chars']:,} character maximum.", "error"
        )
        conn.close()
        return redirect(url_for('practice_scenario', scenario_id=scenario_id))

    if not api_key_is_configured():
        flash("ANTHROPIC_API_KEY is not configured.", "error")
        conn.close()
        return redirect(url_for('practice_scenario', scenario_id=scenario_id))

    today_str = datetime.now().strftime('%Y-%m-%d')
    budget_ok, budget_msg = check_budget_and_daily_limit(conn, session['user'], today_str)
    if not budget_ok:
        conn.close()
        flash(budget_msg, "error")
        return redirect(url_for('practice_scenario', scenario_id=scenario_id))

    public_ticket = get_public_scenario(scenario)
    answer_key    = parse_json_column(scenario['answer_key_json'])

    try:
        grading = grade_practice_response(public_ticket, answer_key, response_text)
    except PracticeLabConfigError as exc:
        conn.close()
        flash(str(exc), "error")
        return redirect(url_for('practice_scenario', scenario_id=scenario_id))
    except (PracticeLabAPIError, PracticeLabResponseError) as exc:
        conn.close()
        flash(f"Could not grade response: {exc}", "error")
        return redirect(url_for('practice_scenario', scenario_id=scenario_id))

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    feedback_json = json.dumps({
        "category_feedback":         grading["category_feedback"],
        "flags":                     grading["flags"],
        "strengths":                 grading["strengths"],
        "technical_errors":          grading["technical_errors"],
        "missing_items":             grading["missing_items"],
        "security_concerns":         grading["security_concerns"],
        "improvement_steps":         grading["improvement_steps"],
        "improved_example_response": grading["improved_example_response"],
    })

    # Only insert after a complete, validated grading response
    cursor = conn.execute('''
        INSERT INTO practice_attempts
            (scenario_id, admin_username, response_text,
             raw_score, final_score, letter_grade, passed, score_cap_reason,
             category_scores_json, feedback_json,
             grading_input_tokens, grading_output_tokens, grading_cost_usd,
             submitted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        scenario_id,
        session['user'],
        response_text,
        grading["raw_score"],
        grading["final_score"],
        grading["letter_grade"],
        1 if grading["passed"] else 0,
        grading["cap_reason"],
        json.dumps(grading["category_scores"]),
        feedback_json,
        grading["input_tokens"],
        grading["output_tokens"],
        grading["cost_usd"],
        now,
    ))
    conn.commit()
    attempt_id = cursor.lastrowid
    conn.close()

    # POST-Redirect-GET: result page is a safe GET that cannot trigger billing
    return redirect(url_for('practice_result', attempt_id=attempt_id))


@app.route('/admin/practice/result/<int:attempt_id>')
def practice_result(attempt_id):
    """Display the graded result. Pure read from DB — no API call."""
    if not admin_is_authenticated():
        return redirect(url_for('login'))

    conn = get_db()
    attempt = conn.execute(
        'SELECT * FROM practice_attempts WHERE id = ?', (attempt_id,)
    ).fetchone()

    if attempt is None:
        conn.close()
        return 'Result not found', 404
    if attempt['admin_username'] != session['user']:
        conn.close()
        return 'Access denied', 403

    scenario = conn.execute(
        'SELECT * FROM practice_scenarios WHERE id = ?', (attempt['scenario_id'],)
    ).fetchone()
    conn.close()

    category_scores = parse_json_column(attempt['category_scores_json'])
    feedback        = parse_json_column(attempt['feedback_json'])
    # Only expose the answer key AFTER grading is complete
    answer_key      = parse_json_column(scenario['answer_key_json'])
    public_ticket   = get_public_scenario(scenario)

    gen_cost   = scenario['generation_cost_usd']
    grade_cost = attempt['grading_cost_usd']

    return render_template(
        'practice_result.html',
        attempt=attempt,
        scenario=public_ticket,
        category_scores=category_scores,
        feedback=feedback,
        answer_key=answer_key,
        gen_cost=gen_cost,
        grade_cost=grade_cost,
        total_cost=gen_cost + grade_cost,
    )


# ---------------------------------------------------------------------------
# Application Startup
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # host='0.0.0.0' binds to all network interfaces so the app is reachable
    # from outside the Docker container. Harmless when running locally.
    app.run(host='0.0.0.0', debug=True)
