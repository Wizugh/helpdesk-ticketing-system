from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3


app = Flask(__name__)
app.secret_key = 'helpdeskkey123'


# ---------------------------------------------------------------------------
# Database Helpers
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect('database.db')
    # row_factory lets us access columns by name, e.g. row['title'],
    # instead of by numeric index like row[1]
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables on first run if they do not already exist."""
    conn = get_db()
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
# Application Startup
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    app.run(debug=True)
