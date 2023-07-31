#!/bin/bash
cd /app/SageKernelServer
python fastapi/src/main.py --url http://jupyter_server:8888/?token=123456
