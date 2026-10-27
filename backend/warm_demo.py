"""Run all three real demo adapters against an image without modifying Firestore."""
import os
import sys
from pathlib import Path
os.environ.setdefault('HF_MODULES_CACHE', str(Path('model_cache/modules').resolve()))
os.environ.setdefault('YOLO_CONFIG_DIR', str(Path('model_cache/ultralytics').resolve()))
from app.config import Settings
from app.inference.registry import create_registry_from_settings, InferenceRuntime

settings = Settings(_env_file='demo.env.example')
settings.ensure_runtime_dirs()
registry = create_registry_from_settings(settings)
runtime = InferenceRuntime(registry)
path = Path(sys.argv[1]).resolve()
for key in ('yolo26','dino','florence'):
    if not registry.try_load(key):
        raise RuntimeError(f'{key}: {registry._errors.get(key)}')
    if key == 'florence':
        result=registry.get(key).assist(path, asset_id='warmup', labels=['car','bus','truck','person'])
        print('REAL_RESULT', key, result.caption, flush=True)
    else:
        result=runtime.detect(key,path,asset_id='warmup',labels=['car','bus','truck','person'])
        print('REAL_RESULT',key,len(result),[(r.label,round(r.confidence,3)) for r in result[:8]],flush=True)
