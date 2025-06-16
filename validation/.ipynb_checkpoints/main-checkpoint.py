from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from validation import validate
from google.cloud import storage
import pandas as pd
import os
import json
import base64

app = FastAPI()

SUPPORTED_FORMATS = ('.csv', '.json', '.xlsx', '.parquet')

@app.post("/")
async def pubsub_trigger(request: Request):
    try:
        envelope = await request.json()
        message = envelope.get("message", {})
        attributes = message.get("attributes", {})
        data = message.get("data")

        if data:
            payload = json.loads(base64.b64decode(data).decode())
        else:
            raise HTTPException(status_code=400, detail="Missing Pub/Sub data")

        bucket_name = payload["bucket"]
        file_name = payload["name"]

        if not file_name.endswith(SUPPORTED_FORMATS):
            raise HTTPException(status_code=400, detail="Unsupported file format.")

        # Download file from GCS
        tmp_path = f"/tmp/{os.path.basename(file_name)}"
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(file_name)
        blob.download_to_filename(tmp_path)

        # Load file
        if file_name.endswith(".csv"):
            df = pd.read_csv(tmp_path)
        elif file_name.endswith(".json"):
            df = pd.read_json(tmp_path)
        elif file_name.endswith(".xlsx"):
            df = pd.read_excel(tmp_path)
        elif file_name.endswith(".parquet"):
            df = pd.read_parquet(tmp_path)

        # Load validation rules
        with open("validation_rules.json") as f:
            rules = json.load(f)

        result = validate(df, rules)

        # Save results to GCS
        result_blob = bucket.blob(f"validation-results/{file_name}.results.json")
        result_blob.upload_from_string(json.dumps(result, indent=2))

        return JSONResponse(content={"status": "success", "file": file_name})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
