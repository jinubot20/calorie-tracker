# Calorie Tracker Migration Summary

## Changes Made

### 1. Created Startup Scripts

Created the following scripts in `~/projects/calorie-tracker/`:

- **`start_all.sh`** - Master script that starts:
  - Backend server (FastAPI on port 8888)
  - Ngrok tunnel (for external access via https://georgine-glebal-nenita.ngrok-free.dev)

- **`stop_all.sh`** - Stops all running processes

- **`start_backend.sh`** - Starts only the backend

- **`start_frontend.sh`** - Starts the frontend dev server (for development)

- **`start_ngrok.sh`** - Starts ngrok tunnel only

- **`README.md`** - Documentation for using the scripts

### 2. Fixed Paths

All scripts now use the correct path: `/home/ubuntu/projects/calorie-tracker/` (instead of old `/home/ubuntu/clawd/calorie-tracker/`)

### 3. Preserved Configuration

- Backend `.env` file contains correct environment variables
- Ngrok configuration is properly set up
- Database, logs, and uploads are in place

## How to Use

### Start the application:
```bash
cd ~/projects/calorie-tracker
./start_all.sh
```

### Stop the application:
```bash
cd ~/projects/calorie-tracker
./stop_all.sh
```

### Check ngrok URL:
```bash
curl -s http://localhost:4040/api/tunnels | python3 -m json.tool
```

## Testing Results

✓ Backend starts successfully
✓ Ngrok creates tunnel to https://georgine-glebal-nenita.ngrok-free.dev
✓ Frontend can be accessed via the ngrok URL

## Notes

- The app runs on port 8888
- The virtual environment (venv) is already set up
- All dependencies are installed
- Database file is in place at `backend/calorie_tracker.db`

## Future Considerations

If you ever move the project again, you'll need to update the paths in these shell scripts.
