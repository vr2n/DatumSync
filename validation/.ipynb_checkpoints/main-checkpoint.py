from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from validation import validate
from google.cloud import storage
import pandas as pd
import os
import json

app = FastAPI()

SUPPORTED_FORMATS = ('.csv', '.json', '.xlsx', '.parquet')

@app.post("/")
async def validate_file(request: Request):
    try:
        data = await request.json()
        bucket_name = data.get("bucket")
        file_name = data.get("name")

        if not bucket_name or not file_name:
            raise HTTPException(status_code=400, detail="Missing 'bucket' or 'name' in request body.")

        if not file_name.endswith(SUPPORTED_FORMATS):
            raise HTTPException(status_code=400, detail="Unsupported file format.")

        # Download file from GCS
        tmp_path = f"/tmp/{os.path.basename(file_name)}"
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(file_name)
        blob.download_to_filename(tmp_path)

        # Load file based on extension
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

        # Run validation
        result = validate(df, rules)

        # Save results to GCS
        result_blob = bucket.blob(f"validation-results/{file_name}.results.json")
        result_blob.upload_from_string(json.dumps(result, indent=2))

        return JSONResponse(content={"status": "success", "file": file_name})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
