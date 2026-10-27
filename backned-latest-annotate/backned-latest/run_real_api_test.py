import json
import urllib.request
import urllib.parse
from uuid import uuid4

def run_real_api_test():
    url = "http://localhost:8000/api/v1/text-annotation/analyze"
    project_id = str(uuid4())
    asset_id = str(uuid4())
    
    # We will submit a form request with generic NER analysis
    fields = {
        "project_id": project_id,
        "asset_id": asset_id,
        "analysis_type": "ENTITY_EXTRACTION",
        "assessment_name": "NER Test Assessment",
        "text": "Microsoft CEO Satya Nadella announced new AI features in Redmond, Washington on October 3, 2026."
    }
    
    # Encode as multipart form data
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
            print("Response Payload Summary:")
            print(json.dumps({
                "analysis_id": data.get("analysis_id"),
                "status": data.get("status"),
                "agent_status": data.get("agent_status"),
                "annotation_count": len(data.get("annotations", [])),
                "annotations": data.get("annotations", [])
            }, indent=2))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_real_api_test()
