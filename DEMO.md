# ModelOS Annotate: image and text demo

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

Open **http://127.0.0.1:8011/app1/**.

If `backend/.env.local` sets `FIRESTORE_EMULATOR_HOST` (a local developer file, not tracked), it overrides the cloud database for every run. Remove that line, or start the backend with it unset, to use the shared database. Port 8000 was occupied in the verification environment, so 8011 was used. `run_demo.py` defaults to 8000 if `PORT` is omitted.

The runner loads `backend/demo.env.example` as defaults and respects existing environment overrides. It uses the checked-in Firestore project/database and local image storage. Its `APP_ENV=production` selects the repository's existing remote-database mode; the service is bound to loopback and this command does not deploy anything. Existing Google Application Default Credentials must have access to the configured database. If authentication is needed, run `gcloud auth application-default login`. There is no memory fallback or database reset.

The CPU models are YOLO26 nano, Grounding DINO tiny and Florence-2 base. Models are cached under ignored `backend/model_cache/` (Ultralytics may initially download `backend/yolo26n.pt`). Florence uses a pinned official revision with Transformers 4.49 and Torch 2.8 CPU. The older broad `requirements.txt` is retained; use the demo lock for this flow. The nano model and inference API follow the [official Ultralytics model documentation](https://docs.ultralytics.com/models/yolo26/).

An optional direct warm-up, without database writes:

```bash
cd backend
OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 ../.venv/bin/python warm_demo.py \
  ../frontend/src/assets/images/city_traffic_buses_1790017671585.jpg
```

**Local, without the shared database (recommended for trying image runs).** The deployed `ingenii-annotate` worker shares the cloud database (see Practical limits), so for a clean local run use the Firestore emulator. It needs Java and the emulator component (`sudo apt-get install openjdk-21-jre-headless google-cloud-cli-firestore-emulator`):

```bash
gcloud emulators firestore start --host-port=127.0.0.1:8080        # one terminal
APP_ENV=development FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 PORT=8011 \
  .venv/bin/python backend/run_demo.py                               # another
```

The emulator starts empty and keeps data only while it runs. Text still calls Gemini on Vertex AI.

For frontend development, keep the backend running and start Vite separately:

```bash
VITE_BACKEND_URL=http://127.0.0.1:8011 npm run dev --prefix frontend
```

## Demo steps

The product rule throughout: the AI drafts every label, and approves an item on its own only when **every** label is at or above the project's line (set in New project, "Send to review below"). Everything else goes to a person, least confident first.

**Image (object detection)**

1. Open workspace → New project. Name it, choose **Image · Object detection**, set classes and colours, set the line, and add images. Create project. If an upload fails, the project is kept and **Retry remaining uploads** sends only the files that didn't land.
2. **AI results** is the run desk. **Run AI** drafts every image with Florence-2 (scene note), YOLO26 and Grounding DINO (boxes, merged). The filters show where each image landed: below the line, approved by AI, approved, failed. The contact sheet shows each image with its boxes; the class summary shows where the AI is least sure; click an image for each box's model, confidence and agreement.
3. **Review** opens on the images below the line, least confident first. Per box: accept (A), correct (pick a class, 1–9, or move/resize it), reject (R). Draw boxes the AI missed, zoom, undo/redo (Ctrl/Cmd-Z, Shift-Ctrl/Cmd-Z). **Approve and next** saves, accepts anything still undecided (the button says how many), approves, and moves on. **Save draft** saves without approving. Leaving with unsaved edits asks first.
4. **Overview** reports the project from its saved labels: the six scorecards, the approval-line chart (drag it to see what another line would do), calibration, accuracy by class, mix-ups, kinds of fix, hardest items. Figures without enough evidence say what they need.
5. Export **COCO JSON** or **YOLO** from Review or Overview. Only approved images (by AI or by a person) and non-rejected boxes are exported.

**Text (entities, sentiment, classification)**

1. New project → **Text**, then **Named entities**, **Sentiment** or **Classification**. Upload `.txt`, `.pdf`, `.docx`, `.csv`, `.json` or `.tsv`.
2. **AI results → Run AI** sends each document to Gemini on Vertex AI (two at a time, from the page; keep it open until the run finishes). Each document is routed by the same line rule: the project's line decides, not the model's own 0.95 bar. A document still goes to a person when its result has errors or conflicts, or when the AI's label is not one of the project's classes (sentiment can come back as *Mixed*, which the default Positive / Neutral / Negative classes leave to a person). Labels are spelled as the project's classes (`POSITIVE` → `Positive`).
3. **Review** shows the document at reading size with entities marked in their class colours. Click an entity to correct it; select any words and pick a class (or press its number) to add one the AI missed. Sentiment and classification projects put one decision on the whole document. **Approve and next** as for images.
4. Export **JSON** (character offsets included) or **CSV**.

**Not connected yet, shown as agreed screens with sample data:** Quality check and Administration. QC sampling is saved with each project but not run (`DEMO_QC_BYPASS=true`: a person's approval is final).

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

To inspect an existing image detection project without changing data, run:

```bash
PROJECT_ID=<project-id> DEMO_URL=http://127.0.0.1:8011 node frontend/scripts/verify-image-ui.mjs
```

For a preinstalled Chromium, set `CHROMIUM_EXECUTABLE` to its executable path. Local screenshots, exports and run logs go in ignored `.demo/`.

Verified in this workspace:

- Cloud Firestore connectivity, real inference from all three models, project creation and image upload.
- Invalid upload retains the project; focused tests confirm inference failures do not publish partial/empty success.
- Blank-image false positives were explicitly rejected and their inspected images approved; rejected labels remained excluded after restart.
- Real traffic image: 91 merged labels persisted; review edits included relabel, clamp, deletion, manual box and rejection.
- COCO and YOLO exports contained 90 accepted labels; all classes/coordinates matched reviewed records (YOLO to six-decimal precision).
- Explicit approval survived backend restart; saving alone produced zero exportable labels.
- The image UI uses screen-sized HTML labels, consistent class colours, zoom-independent handles, a thumbnail filmstrip and an object inspector. Box names appear on focus by default; enabling Names avoids overlapping tags.
- Chromium verified label typography, dense-label spacing and square handles at 200% zoom.
- Chromium completed the live landing-to-approved-export flow, including a simulated 503 save failure, cancelled navigation, zoomed movement/resizing, undo/redo and geometry persistence after reload.
- Landing, New Project, Overview and Review inspected at 1440px, 720px and 390px, with no page-width overflow or browser JavaScript errors.

Verified on 2026-10-28 against the shared database, after the workspace was restored:

- Image: created a project with three street photos, ran the three models, and on the drafted image accepted, rejected, relabelled and drew a box, then **Approve and next**. The image was approved and the Overview's figures (AI accuracy 95.8% of 48 reviewed boxes, the person → bus mix-up, kinds of fix, hardest item) came from those saved decisions.
- Text: created an entities project with three short test documents. Gemini on Vertex labelled all three, and all cleared the 0.70 line, so the AI approved them. In review, one document had an entity added from a text selection, one rejected and one relabelled, then was approved. Saved offsets match the document text, the relabel kept the AI's original class, and the JSON export held the 24 approved entities without the rejected one.
- Local dry run on the Firestore emulator: three street photos all drafted (3 of 3; on the shared database the deployed worker had failed two). All three were reviewed in the UI (reject, undo, redo, Approve and next), and the exports matched the decisions: COCO with 3 images, 130 boxes and 4 classes, and YOLO with 130 label lines (133 boxes, 3 rejected).
- `npm test`, `tsc --noEmit` (no errors) and the backend tests (`test_demo_flow.py`, `test_span_review.py`).

## Practical limits

- **Another worker shares this database.** The Cloud Run service `ingenii-annotate` in the same Google Cloud project runs a batch worker on `engenii-annotate-native`. It can claim image jobs queued by a local backend and fails them with "Uploaded image file is unavailable", because the uploaded files exist only on the local machine. To run images reliably, point the local backend at its own database (the Firestore emulator or a separate database) or stop that service's worker. Text runs inside the local request and is not affected.

- CPU execution is serial and can take tens of seconds per image; full-model downloads are required on the first run. While a batch runs, other API calls slow down (several seconds each). Images need no external model; text needs Gemini on Vertex AI, billed to the configured Google Cloud project.
- A save is one atomic Firestore batch, limited to 500 writes including removed labels and the asset update. Larger annotation sets are refused before writing.
- Local image files must remain on this machine. Older cloud projects may reference images absent from this checkout; new demo uploads are saved under ignored `backend/storage/`.
- Vision models can produce false positives even on blank images. An empty result is never approved by AI; a person confirms it.
- The text run is driven from the AI results page; closing the page stops the documents not yet sent.
- No sign-in: decisions are not attributed to named reviewers, so the Overview's reviewer figures wait for that.
- No deployment, polygons/masks, video, relation extraction, QC or administration implementation is included.
