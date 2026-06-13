from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'helpdeskkey123'

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'low',
            status TEXT NOT NULL DEFAULT 'open',
            created_by TEXT NOT NULL,
            date TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            author TEXT NOT NULL,
            body TEXT NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id)
        )
    ''')
    conn.commit()
    conn.close()

def migrate_db():
    conn = get_db()
    try:
        conn.execute('ALTER TABLE tickets ADD COLUMN assigned_to TEXT DEFAULT NULL')
        conn.commit()
    except:
        pass
    conn.close()

init_db()
migrate_db()

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
        user = conn.execute('SELECT * FROM users WHERE username = ?', 
                           (username,)).fetchone()
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
        password = generate_password_hash(request.form['password'])
        try:
            conn = get_db()
            conn.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
                        (username, password, 'user'))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except:
            error = 'Username already exists'
    return render_template('register.html', error=error)

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', username=session['user'])

@app.route('/admin')
def admin():
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    return render_template('admin.html', username=session['user'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/submit', methods=['GET', 'POST'])
def submit_ticket():
    if 'user' not in session:
        return redirect(url_for('login'))
    success = None
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        priority = request.form['priority']
        from datetime import datetime
        date = datetime.now().strftime('%Y-%m-%d %H:%M')
        conn = get_db()
        conn.execute('''INSERT INTO tickets 
                       (title, description, priority, status, created_by, date)
                       VALUES (?, ?, ?, 'open', ?, ?)''',
                    (title, description, priority, session['user'], date))
        conn.commit()
        conn.close()
        success = 'Ticket submitted successfully'
    return render_template('submit_ticket.html', success=success)

@app.route('/mytickets')
def my_tickets():
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    tickets = conn.execute('''SELECT * FROM tickets WHERE created_by = ? 
                             ORDER BY date DESC''',
                          (session['user'],)).fetchall()
    conn.close()
    return render_template('mytickets.html', tickets=tickets)

@app.route('/admin/tickets')
def admin_tickets():
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    status_filter = request.args.get('status', 'all')
    priority_filter = request.args.get('priority', 'all')
    conn = get_db()
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
    tickets = conn.execute(query, params).fetchall()
    conn.close()
    return render_template('admin_tickets.html', tickets=tickets,
                          status_filter=status_filter,
                          priority_filter=priority_filter)

@app.route('/ticket/<int:ticket_id>')
def ticket_detail(ticket_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    ticket = conn.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,)).fetchone()
    if ticket is None:
        conn.close()
        return 'Ticket not found', 404
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
    from datetime import datetime
    date = datetime.now().strftime('%Y-%m-%d %H:%M')
    conn = get_db()
    conn.execute(
        'INSERT INTO comments (ticket_id, author, body, date) VALUES (?, ?, ?, ?)',
        (ticket_id, session['user'], body, date)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('ticket_detail', ticket_id=ticket_id))

@app.route('/admin/update/<int:ticket_id>', methods=['POST'])
def update_ticket(ticket_id):
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    new_status = request.form['status']
    assigned_to = request.form.get('assigned_to', '').strip() or None
    conn = get_db()
    conn.execute('UPDATE tickets SET status = ?, assigned_to = ? WHERE id = ?',
                (new_status, assigned_to, ticket_id))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_tickets'))

if __name__ == '__main__':
    app.run(debug=True)