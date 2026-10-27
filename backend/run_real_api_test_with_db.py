import asyncio
import json
import urllib.request
from uuid import uuid4
from datetime import datetime, UTC

from app.db.models import get_database
from app.config import get_settings

async def main():
    db = get_database()
    project_id = str(uuid4())
    asset_id = str(uuid4())
    
    target_labels = ["Person", "Organization", "Location", "Date", "Product", "Event", "Money"]
    sample_text = (
        "Satya Nadella is the CEO of Microsoft. Microsoft is headquartered in Redmond, Washington. "
        "The company announced the event on October 3, 2026 and launched a new product worth $999."
    )
    
    # Insert project doc with target_objects / labels
    await db.projects.insert_one({
        "id": project_id,
        "name": "E2E Complete NER Test Project",
        "description": "Test Project for Text NER with all Target Objects",
        "modality": "text",
        "task_type": "ENTITY_EXTRACTION",
        "labels": target_labels,
        "target_objects": target_labels,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC)
    })
    
    url = "http://localhost:8000/api/v1/text-annotation/analyze"
    fields = {
        "project_id": project_id,
        "asset_id": asset_id,
        "analysis_type": "ENTITY_EXTRACTION",
        "assessment_name": "Full Target Objects NER Assessment",
        "text": sample_text
    }
    
    boundary = "----WebKitFormBoundary" + str(uuid4()).replace("-", "")
    body_bytes = bytearray()
    
    for key, value in fields.items():
        body_bytes.extend(f"--{boundary}\r\n".encode("utf-8"))
        body_bytes.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        body_bytes.extend(f"{value}\r\n".encode("utf-8"))
    
    body_bytes.extend(f"--{boundary}--\r\n".encode("utf-8"))
    
    req = urllib.request.Request(
        url,
        data=bytes(body_bytes),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            status = response.status
            resp_body = response.read().decode("utf-8")
            print(f"HTTP Status: {status}")
            data = json.loads(resp_body)
            print("Response Payload:")
            print(json.dumps(data, indent=2))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
