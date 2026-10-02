# SAATHI

SAATHI is a local Flask prototype with a landing page, account registration/login, and a conversational demo. It uses SQLite to keep each user's conversations on this computer.

The chat replies are simple demo responses. This app does not use a real AI service and is not a therapist, doctor, diagnostic system, or replacement for professional care.

## Requirements

- Python 3.10 or newer
- No separate database server; SQLite is included with Python

## Install and run on Windows

Open PowerShell in this project folder and run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

If PowerShell prevents activation, use Command Prompt instead:

```bat
py -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>. Stop the local server with `Ctrl+C` in its terminal.

## First run

The app creates the `instance` folder and `instance/saathi.db` SQLite database automatically when it starts. The database contains `user`, `conversation`, and `message` tables. Passwords are stored as Werkzeug password hashes, not plaintext. The database stays on this computer and is ignored by Git.

To confirm that messages are saved, create an account, log in, send a message, then refresh the chat page. The exchange should remain visible, and the conversation will appear in the history panel. Start another chat with **New Chat**; earlier conversations remain in the list.

## Local secret key

For local development, the app uses a clearly marked fallback session secret so it can run without extra setup. Before any deployment, set a long random `SECRET_KEY` environment variable and use HTTPS. On PowerShell, set it for the current terminal before starting Flask:

```powershell
$env:SECRET_KEY = "replace-with-a-long-random-value"
python app.py
```

Do not commit real secrets. This project is configured for local development, not production deployment.

## Pages

- `/` - landing page
- `/register` - create an account
- `/login` - sign in
- `/chat` - latest conversation; requires login
- `/chat/new` - start a conversation with a POST form
- `/chat/<id>` - open one of your own conversations
- `/logout` - log out with a POST form
# Emotional-help-System-
