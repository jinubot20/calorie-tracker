#!/bin/bash
pkill -9 -f main.py
sleep 2
cd /home/ubuntu/projects/calorie-tracker/backend
nohup ./venv/bin/python3 main.py > backend_run.log 2>&1 &
