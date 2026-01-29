#!/bin/bash
echo "Stopping Calorie Tracker..."

# Stop backend
pkill -f 'python3 main.py'
echo "✓ Backend stopped"

# Stop ngrok
pkill ngrok
echo "✓ Ngrok stopped"

echo ""
echo "All processes stopped"
