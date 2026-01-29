# Calorie Tracker - Startup Scripts

This directory contains startup scripts for the Calorie Tracker application.

## Scripts

- `start_all.sh` - Start everything (backend + ngrok) in one command
- `stop_all.sh` - Stop all processes
- `start_backend.sh` - Start only the backend server
- `start_frontend.sh` - Start the frontend dev server
- `start_ngrok.sh` - Start ngrok tunnel for external access

## Usage

### Start everything:
```bash
./start_all.sh
```

### Stop everything:
```bash
./stop_all.sh
```

### Start individual components:
```bash
# Backend only
./start_backend.sh

# Frontend dev server (if needed)
./start_frontend.sh

# Ngrok only
./start_ngrok.sh
```

## Access Points

- **Backend API:** http://localhost:8888
- **Frontend (via ngrok):** Run `curl -s http://localhost:4040/api/tunnels` to get the URL

## Logs

- Backend logs: `backend/backend_run.log`
- Ngrok logs: `ngrok.log`

## Project Structure

```
~/projects/calorie-tracker/
├── backend/
│   ├── main.py          # FastAPI application
│   ├── database.py      # Database models
│   ├── ai_engine.py     # AI integration
│   ├── auth.py          # Authentication
│   ├── venv/            # Python virtual environment
│   └── .env             # Environment variables
├── frontend/
│   ├── src/             # React source code
│   ├── dist/            # Built frontend
│   └── package.json     # Node dependencies
└── *.sh                 # Startup scripts
```

## Environment Variables

Backend `.env` contains:
- `ZHIPUAI_API_KEY` - AI model API key
- `GOOGLE_API_KEY` - Google API key
- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `BACKEND_URL` - Backend URL
- `FRONTEND_URL` - Frontend URL (ngrok URL)
- `GMAIL_APP_PASSWORD` - Gmail app password for notifications
- `GMAIL_USER` - Gmail username
- `PERSONAL_EMAIL` - Personal email for notifications
