#!/bin/bash
cd ~/gold-prediction/backend
export PYTHONPATH=$PYTHONPATH:.
nohup ../venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 &