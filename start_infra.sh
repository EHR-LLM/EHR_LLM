#!/bin/bash
PYENV_PYTHON=/Users/fodepixofarfan/.pyenv/versions/3.12.5/bin/python3.12
cd /Users/fodepixofarfan/coding/EHR_LLM
exec "$PYENV_PYTHON" -m src.start_task --config configs/start_task.yaml --auto-controller
