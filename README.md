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

**Admin features:**
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
- **Automation:** PowerShell
- **Version Control:** Git, GitHub

---

## How To Run Locally

**Requirements:** Python 3.x installed

**1. Clone the repository:**
```
git clone https://github.com/Wizugh/helpdesk-ticketing-system.git
cd helpdesk-ticketing-system
```

**2. Create and activate a virtual environment:**
```
python -m venv venv
venv\Scripts\activate
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
- Git version control and pushing to GitHub throughout the build process

---

## Author

Tahsin Ahsan — Computer Science, St. John's University
GitHub: https://github.com/Wizugh
