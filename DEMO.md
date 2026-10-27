# ModelOS Annotate image demo

The default entry is the approved editorial landing. Its workspace links open the React rail workspace at `/app1/next.html#/projects`. The legacy implementation remains in source/history but is not a build entry.

## Start

Run from the repository root. Node 24+ and Python 3.13 are used by the verified dependency lock.

```bash
UV_CACHE_DIR=/tmp/modelos-uv uv venv --python 3.13 .venv
UV_CACHE_DIR=/tmp/modelos-uv uv pip sync --python .venv/bin/python \
  backend/requirements-demo.lock \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  --index-strategy unsafe-best-match
npm ci --prefix frontend
npm run build --prefix frontend
PORT=8011 .venv/bin/python backend/run_demo.py
```

Open **http://127.0.0.1:8011/app1/**. Port 8000 was occupied in the verification environment, so 8011 was used. `run_demo.py` defaults to 8000 if `PORT` is omitted.

The runner loads `backend/demo.env.example` as defaults and respects existing environment overrides. It uses the checked-in Firestore project/database and local image storage. Its `APP_ENV=production` selects the repository's existing remote-database mode; the service is bound to loopback and this command does not deploy anything. Existing Google Application Default Credentials must have access to the configured database. If authentication is needed, run `gcloud auth application-default login`. There is no memory fallback or database reset.

The CPU models are YOLO26 nano, Grounding DINO tiny and Florence-2 base. Models are cached under ignored `backend/model_cache/` (Ultralytics may initially download `backend/yolo26n.pt`). Florence uses a pinned official revision with Transformers 4.49 and Torch 2.8 CPU. The older broad `requirements.txt` is retained; use the demo lock for this flow. The nano model and inference API follow the [official Ultralytics model documentation](https://docs.ultralytics.com/models/yolo26/).

An optional direct warm-up, without database writes:

```bash
cd backend
OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 ../.venv/bin/python warm_demo.py \
  ../frontend/src/assets/images/city_traffic_buses_1790017671585.jpg
```

For frontend development, keep the backend running and start Vite separately:

```bash
VITE_BACKEND_URL=http://127.0.0.1:8011 npm run dev --prefix frontend
```

## Demo steps

1. Open workspace → New project. Choose **Image / Object detection**, set classes/colours and the confidence highlight threshold, and stage images.
2. Create project. Upload failures retain the created project and offer retry for remaining files. The saved project can also be opened to upload images later.
3. Open **Upload & run AI**. Upload more images if needed, then click **Run AI**. Status, errors, captions, boxes, model confidence and provenance come from persisted results. The three required models must all succeed before results are published.
4. Open Review. Select an image; draw missing boxes, select/move them, drag corner handles to resize, relabel or delete them, and accept/reject labels. Zoom and Undo/Redo are available. Keys 1–9 select classes; Delete removes a selected box; Ctrl/Cmd-Z and Shift-Ctrl/Cmd-Z undo/redo.
5. **Save edits**. Saved edits reopen review and do not approve the image. Failed saves keep the local edits. Navigation asks before discarding unsaved edits.
6. **Approve image** after every label is decided and saved. Successful empty results also require explicit approval. Human approval is final under `DEMO_QC_BYPASS=true`.
7. Download **COCO JSON** or **YOLO** from Review or Overview. Only approved images and non-rejected labels are exported. The UI downloads label-only ZIPs; the existing export API can include images with `include_images=true`.

Overview retains the editorial scorecards, paired figures, class table, hardest-items table and reviewer sections. Counts and correction evidence use persisted records. Calibration, ground-truth accuracy and reviewer comparisons remain unavailable where evidence is insufficient. QC and Administration are visible unavailable states. Text/video and non-box image tasks are outside this demo.

## Verification

```bash
npm run lint --prefix frontend
npm run build --prefix frontend
npm test --prefix frontend
PYTHONPATH=backend .venv/bin/python -m pytest \
  backend/app/services/test_demo_flow.py \
  backend/app/inference/test_dino_mapping_regression.py \
  backend/app/inference/test_merge_conflicts.py \
  -q -o asyncio_default_fixture_loop_scope=function
```

The focused suite covers inference failure versus successful empty results, geometry clamping, confidence/provenance preservation, atomic-save failure, rejected-label filtering, saved-but-unapproved export, upload retry without duplicate project creation, zoom/move/resize, undo/redo, navigation protection and preservation of unsaved edits.

The live browser check creates one new project and leaves it available for inspection. Run it from the repository root after starting the backend:

```bash
cd frontend
npx playwright install chromium
cd ..
DEMO_URL=http://127.0.0.1:8011 node frontend/scripts/verify-demo.mjs
```

For a preinstalled Chromium, set `CHROMIUM_EXECUTABLE` to its executable path. Local screenshots, exports and run logs go in ignored `.demo/`.

Verified in this workspace:

- Cloud Firestore connectivity, real inference from all three models, project creation and image upload.
- Invalid upload retains the project; focused tests confirm inference failures do not publish partial/empty success.
- Blank-image false positives were explicitly rejected and their inspected images approved; rejected labels remained excluded after restart.
- Real traffic image: 91 merged labels persisted; review edits included relabel, clamp, deletion, manual box and rejection.
- COCO and YOLO exports contained 90 accepted labels; all classes/coordinates matched reviewed records (YOLO to six-decimal precision).
- Explicit approval survived backend restart; saving alone produced zero exportable labels.
- Chromium completed the live landing-to-approved-export flow, including a simulated 503 save failure, cancelled navigation, zoomed movement/resizing, undo/redo and geometry persistence after reload.
- Landing, New Project, Overview and Review inspected at 1440px, 720px and 390px, with no page-width overflow or browser JavaScript errors.

## Practical limits

- CPU execution is serial and can take tens of seconds per image; full-model downloads are required on the first run. No external LLM is required.
- A save is one atomic Firestore batch, limited to 500 writes including removed boxes and the asset update. Larger annotation sets are refused before writing.
- Local image files must remain on this machine. Older cloud projects may reference images absent from this checkout; new demo uploads are saved under ignored `backend/storage/`.
- Vision models can produce false positives even on blank images; mandatory human review can reject them. Successful empty inference and all-rejected reviews are supported.
- No deployment, polygons/masks, text/video processing, QC or administration implementation is included.
