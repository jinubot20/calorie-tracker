#!/bin/bash
# Kill existing ngrok processes
pkill -9 ngrok
sleep 2

# Start ngrok for port 8888 (the backend port)
ngrok http 8888 --log=ngrok.log
