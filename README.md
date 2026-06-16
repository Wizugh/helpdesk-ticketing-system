# Helpdesk Ticketing System

A full-stack helpdesk ticketing application built with Python Flask and SQLite,
accompanied by PowerShell automation scripts for common IT tasks.

Built as a portfolio project to demonstrate practical IT support skills including
user management, ticket lifecycle handling, role-based access control, audit logging,
and IT automation.

---

## What It Does

**User features:**
- Register and log in with a hashed password
- Submit IT support tickets with a title, description, and priority level (low / medium / high)
- View all tickets you have submitted and their current status
- Comment on open tickets to add updates or ask questions
- Close your own ticket once your issue is resolved

**Admin features (IT Support Practice Lab):**
- Generate a fictional IT support ticket with one click (AI-powered via Claude Haiku)
- Write a professional IT support response and receive AI grading across six rubric categories
- View a detailed score breakdown, specific feedback, security flags, and an improved example answer
- Review the hidden answer key (expected troubleshooting steps, prohibited actions, escalation conditions) revealed after grading
- Track attempt history, average score, and best score per session
- Retry any previous scenario without paying to regenerate it
- Monitor estimated API spend against a configurable local budget
- All practice data is fully isolated from real helpdesk tickets

**Admin features (helpdesk):**
- View all tickets across the system from a live analytics dashboard
  - Doughnut chart showing ticket breakdown by status
  - Priority bars showing active (open + in-progress) tickets by priority level
  - Five stat cards: total, open, in progress, resolved, closed
  - Recent tickets table with direct links
- Filter the full ticket list by status and priority
- Update ticket status (open → in progress → resolved) and assign tickets to agents
- All status changes and assignment changes are automatically recorded as audit log entries in the ticket activity thread

**Security:**
- Passwords are hashed using Werkzeug — plain text is never stored
- Sessions manage authentication across pages
- Role-based access control separates regular users from admins
- Regular users can only view and act on their own tickets

---

## Tech Stack

- **Backend:** Python, Flask
- **Templating:** Jinja2
- **Database:** SQLite
- **Frontend:** HTML, CSS, JavaScript
- **Charts:** Chart.js 4
- **AI:** Anthropic Python SDK (Claude Haiku)
- **Containerisation:** Docker, Docker Compose
- **Automation:** PowerShell
- **Version Control:** Git, GitHub

---

## IT Support Practice Lab

An admin-only feature that uses the Anthropic Claude API to generate realistic fictional IT support scenarios and grade your responses.

### Feature workflow

1. Admin selects a category (e.g. Networking, Security) and difficulty (Beginner / Intermediate / Advanced).
2. Claude Haiku generates a fictional workplace IT ticket and a hidden answer key.
3. The admin writes a professional IT support response.
4. Claude grades the response against a strict 100-point rubric.
5. Python independently validates every score, sums them, and applies caps — Claude's arithmetic is never trusted.
6. The admin sees a full breakdown with scores, feedback, an improved example, and the expected troubleshooting checklist.

### Grading rubric (100 points)

| Category                     | Max |
|------------------------------|-----|
| Technical Accuracy           |  35 |
| Troubleshooting Process      |  20 |
| Security & Safety            |  15 |
| Completeness & Escalation    |  10 |
| Professionalism & Empathy    |  10 |
| Clarity & Actionability      |  10 |

Passing score: **70 or higher** after score caps.

### Strict score caps

Certain flags automatically cap the final score regardless of the rubric total:

| Flag                                  | Maximum score |
|---------------------------------------|---------------|
| Requests or exposes credentials       | 39            |
| Dangerous or insecure guidance        | 39            |
| Fundamentally incorrect resolution   | 59            |
| No meaningful troubleshooting         | 69            |

If multiple caps apply, the lowest (most severe) is used.

### Anthropic API setup

1. Create an account at [console.anthropic.com](https://console.anthropic.com/) and generate an API key.
2. Copy `.env.example` to `.env`.
3. Set `ANTHROPIC_API_KEY=sk-ant-...` in your `.env` file.
4. The rest of the application starts normally without the key — only the Practice Lab is disabled.

### Local .env configuration

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
CLAUDE_MODEL=claude-haiku-4-5-20251001
PRACTICE_BUDGET_USD=5.00
PRACTICE_DAILY_API_CALL_LIMIT=40
PRACTICE_MAX_RESPONSE_CHARS=5000
CLAUDE_INPUT_COST_PER_MILLION=1.00
CLAUDE_OUTPUT_COST_PER_MILLION=5.00
```

### Docker setup

The same `.env` file is loaded by Docker Compose via `env_file`. No extra steps needed — the Practice Lab works in Docker the same way as locally.

### Model configuration

The default model is `claude-haiku-4-5-20251001`. To use a different model, set `CLAUDE_MODEL` in your `.env`. Token pricing defaults match Haiku 4.5; update `CLAUDE_INPUT_COST_PER_MILLION` and `CLAUDE_OUTPUT_COST_PER_MILLION` if you change models.

### Local budget

`PRACTICE_BUDGET_USD` sets a local estimated spend cap. The app blocks new API calls once this threshold is reached.

**Important:** This is an estimate based on calls recorded by this application — it is **not** your official Anthropic account balance. Check your actual usage at [console.anthropic.com](https://console.anthropic.com/).

### Daily API call limit

`PRACTICE_DAILY_API_CALL_LIMIT` caps the total number of API calls (generations + gradings) per admin per day. The counter resets at midnight. Default: 40 calls/day.

### How to run tests

Install dev dependencies:

```
pip install -r requirements-dev.txt
```

Run the full test suite (no real API calls are made):

```
python -m pytest tests/ -v
```

Or just the quick summary:

```
python -m pytest -q
```

### Privacy and security notes

- The Anthropic API key is never written to source code, templates, JavaScript, or logs.
- The hidden answer key is never included in HTML before an attempt is graded.
- Admin responses are sent to Claude inside `<administrator_response>` XML tags — the Anthropic-recommended pattern for injecting untrusted content safely.
- Claude is explicitly instructed not to follow any instructions embedded in the admin response.
- All AI-generated text is HTML-escaped by Jinja's default auto-escaping (`{{ variable }}`, never `{{ variable|safe }}`).
- AI text is never rendered with `innerHTML`.
- All database queries are parameterised — no string concatenation.
- Practice data (scenarios and attempts) is kept in separate tables and never mixes with real helpdesk tickets.

### AI feedback disclaimer

Scores and feedback are AI-generated by Claude for self-improvement practice only. This is not a certification, professional assessment, or official evaluation.

---

## How To Run Locally

**Requirements:** Python 3.x installed

**1. Clone the repository:**
```
git clone https://github.com/Wizugh/helpdesk-ticketing-system.git
cd helpdesk-ticketing-system
```

**2. Create and activate a virtual environment:**

Windows:
```
python -m venv venv
venv\Scripts\activate
```

Mac / Linux:
```
python3 -m venv venv
source venv/bin/activate
```

**3. Install dependencies:**
```
pip install -r requirements.txt
```

**4. Run the app:**
```
python app.py
```

**5. Open in browser:**
```
http://127.0.0.1:5000
```

**6. Create an admin account:**

Register a new account through the web interface, then open a Python shell and run:

```python
import sqlite3

conn = sqlite3.connect('database.db')
conn.execute("UPDATE users SET role = 'admin' WHERE username = 'yourusername'")
conn.commit()
conn.close()
```

---

## How To Run with Docker

**Requirements:** Docker Desktop installed and running

**1. Clone the repository:**
```
git clone https://github.com/Wizugh/helpdesk-ticketing-system.git
cd helpdesk-ticketing-system
```

**2. Create your environment file:**

`.env` is not included in the repository. Create it by copying the example template:
```
copy .env.example .env
```
This creates a `.env` file on your machine with placeholder values. Open it in any text editor — you will need to fill in `SECRET_KEY` in the next step.

**3. Generate a secret key and paste it into `.env`:**

Run one of these commands (you only need one — use whichever you have):

If you have Python installed:
```
python -c "import secrets; print(secrets.token_hex(32))"
```

If you only have Docker:
```
docker run --rm python:3.11-slim python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output, open `.env`, and replace `change-this-to-a-long-random-string` with it.
Leave `DATABASE_PATH` as-is.

**4. Build and start the container:**
```
docker compose up --build
```

**5. Open in browser:**
```
http://localhost:5000
```

**6. Create an admin account:**

Register a new account through the web interface, then open a second terminal and start a Python shell inside the container:
```
docker compose exec web python
```

Then run these lines one at a time, replacing `yourusername` with your account name:
```python
import sqlite3
conn = sqlite3.connect('/app/data/database.db')
conn.execute("UPDATE users SET role = 'admin' WHERE username = 'yourusername'")
conn.commit()
conn.close()
```

Type `exit()` when done.

**To stop the app:**
```
docker compose down
```

Your data is stored in a Docker volume and survives restarts. To also delete the database when stopping:
```
docker compose down -v
```

---

## PowerShell Automation Scripts

Located in the `/scripts` folder. Run from a PowerShell terminal inside the scripts directory.

**Onboarding Checklist**

Generates a formatted IT onboarding checklist for a new user and saves it as a text file.

```powershell
.\onboarding.ps1 -NewUsername "John"
```

**Disk Space Monitor**

Checks all drives on the machine, calculates usage percentages, flags drives over 80% with warnings,
and exports a timestamped log file.

```powershell
.\diskspace.ps1
```

**User Account Audit**

Lists all local user accounts with their enabled status and last login time.
Exports results to a timestamped CSV file.

```powershell
.\list_users.ps1
```

---

## What I Learned

- Building a full authentication system with hashed passwords and session management
- Implementing role-based access control to separate user and admin functionality
- Writing SQL queries with parameterised inputs to prevent SQL injection
- Using `SUM(CASE WHEN ...)` to gather multiple aggregated stats in a single database query
- Passing server-side data to JavaScript safely using Jinja2's `tojson` filter
- Building interactive charts with Chart.js and handling browser back/forward cache (bfcache) to replay animations
- Designing an automatic audit log that records field-level changes without any manual input
- Automating real IT tasks with PowerShell including user provisioning, disk monitoring, and account auditing
- Manual database administration — resetting passwords and updating user roles directly via SQL
- Containerising a Flask app with Docker and Docker Compose, including volume mounts for database persistence
- Managing secrets with environment variables so sensitive values like the Flask secret key never appear in source code
- Integrating the Anthropic Claude API for AI-powered scenario generation and structured response grading
- Using JSON Schema structured outputs (`output_config`) to enforce reliable, schema-conformant API responses
- Building a multi-turn conversation retry loop so a malformed AI response triggers one clean retry rather than a user-visible crash
- Independently validating and capping AI-reported scores in Python so Claude's arithmetic is never trusted
- Tracking API token usage per call and enforcing a local estimated spend cap to prevent accidental overuse
- Git version control and pushing to GitHub throughout the build process

---

## Author

Tahsin Ahsan — Computer Science, St. John's University
GitHub: https://github.com/Wizugh
