#!/bin/bash
cd /app/SageKernelServer
git pull
python fastapi/src/main.py --url http://jupyter_server:8888/?token=123456
