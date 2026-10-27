"""Start the explicit cloud-persisted image demo from the backend directory."""
import os
from pathlib import Path
from dotenv import dotenv_values

root = Path(__file__).resolve().parent
os.chdir(root)
for key, value in dotenv_values(root / 'demo.env.example').items():
    if value is not None:
        os.environ.setdefault(key, value)
os.environ.setdefault('HF_MODULES_CACHE', str(root / 'model_cache/modules'))
os.environ.setdefault('YOLO_CONFIG_DIR', str(root / 'model_cache/ultralytics'))
os.environ.setdefault('STATIC_DIR', str(root.parent / 'frontend/dist'))
os.environ.setdefault('OMP_NUM_THREADS', '4')
os.environ.setdefault('MKL_NUM_THREADS', '4')
import uvicorn
uvicorn.run('app.main:app', host='127.0.0.1', port=int(os.environ.get('PORT', '8000')))
