#!/bin/bash
# Master script to start the Calorie Tracker application

echo "Starting Calorie Tracker..."

# Start the backend
echo "Starting backend..."
cd /home/ubuntu/projects/calorie-tracker/backend
nohup ./venv/bin/python3 main.py > backend_run.log 2>&1 &
BACKEND_PID=$!
echo "Backend started (PID: $BACKEND_PID)"

# Wait for backend to start
sleep 3

# Check if backend is running
if ps -p $BACKEND_PID > /dev/null; then
    echo "✓ Backend is running"
else
    echo "✗ Backend failed to start. Check backend_run.log"
    exit 1
fi

# Start ngrok (for external access)
echo "Starting ngrok for external access..."
cd /home/ubuntu/projects/calorie-tracker
ngrok http 8888 --log=ngrok.log > /dev/null 2>&1 &
NGROK_PID=$!
echo "Ngrok started (PID: $NGROK_PID)"

# Wait a bit for ngrok to initialize
sleep 2

echo ""
echo "Calorie Tracker is now running!"
echo "Backend: http://localhost:8888"
echo ""
echo "To see the ngrok URL, run: curl -s http://localhost:4040/api/tunnels"
echo ""
echo "To stop everything, run: pkill -f 'python3 main.py' && pkill ngrok"
