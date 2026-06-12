# Helpdesk Ticketing System

A full-stack helpdesk ticketing application built with Python Flask and SQLite, 
accompanied by PowerShell automation scripts for common IT tasks.

Built as a portfolio project to demonstrate practical IT support skills including 
user management, ticket lifecycle handling, role-based access control, and IT automation.

---

## What It Does

- Users can register, log in, and submit IT support tickets with a title, 
  description, and priority level
- Admins can view all tickets across the system, filter by status or priority, 
  and update ticket status in real time
- Passwords are hashed and never stored in plain text
- Sessions manage authentication across pages
- Role-based access control separates regular users from admins

---

## Tech Stack

- **Backend:** Python, Flask
- **Database:** SQLite
- **Frontend:** HTML, CSS
- **Automation:** PowerShell
- **Version Control:** Git, GitHub

---

## How To Run Locally

**Requirements:** Python 3.x installed

**1. Clone the repository:**
git clone https://github.com/Wizugh/helpdesk-ticketing-system.git

cd helpdesk-ticketing-system

**2. Install dependencies:**
pip install flask werkzeug

**3. Run the app:**
python app.py

**4. Open in browser:**
http://127.0.0.1:5000

**5. Create an admin account:**
Register a new account, then open a Python shell and run:

import sqlite3

conn = sqlite3.connect('database.db')

conn.execute("UPDATE users SET role = 'admin' WHERE username = 'yourusername'")

conn.commit()

conn.close()

---

## PowerShell Automation Scripts

Located in the `/scripts` folder. Run from PowerShell terminal inside the scripts directory.

**Onboarding Checklist**
Generates a formatted IT onboarding checklist for a new user and saves it as a text file.

.\onboarding.ps1 -NewUsername "John"

**Disk Space Monitor**
Checks all drives on the machine, calculates usage percentages, flags drives over 80% with warnings, and exports a log file with a timestamp.

.\diskspace.ps1


**User Account Audit**
Lists all local user accounts with their status and last login time. Exports results to a CSV file.

.\list_users.ps1


---

## What I Learned

- Building a full authentication system with hashed passwords and session management
- Implementing role-based access control to separate user and admin functionality
- Writing SQL queries with parameterized inputs to prevent SQL injection
- Automating real IT tasks with PowerShell including user provisioning, disk monitoring, and account auditing
- Manual database administration — resetting passwords and updating user roles directly via SQL
- Git version control and pushing to GitHub throughout the build process

---

## Author

Tahsin Ahsan — Computer Science, St. John's University
GitHub: https://github.com/Wizugh