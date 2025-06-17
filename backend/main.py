import os
import io
import json
import logging
import tempfile
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from google.cloud import storage
from google.cloud import logging as cloud_logging

# ✅ Module Imports
from conversion import read_from_buffer, convert_to_buffer, get_extension
from profiling_utils import load_data, profile_dataframe, detect_drift, upload_json_to_gcs
from normalization import normalize_file
from validation import validate
from predict import predict_from_parquet, download_blob

# ✅ App Initialization
app = FastAPI()
cloud_logging.Client().setup_logging()

# ✅ Config
BUCKET_NAME = "datumsync"
UPLOAD_PREFIX = "converted/"
SUPPORTED_EXTENSIONS = [".csv", ".parquet", ".xlsx"]
SUPPORTED_FORMATS = ('.csv', '.json', '.xlsx', '.parquet')

# ✅ Utility Functions
def download_from_gcs(bucket_name, blob_name) -> io.BytesIO:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    if not blob.exists():
        raise HTTPException(status_code=404, detail="File not found in GCS bucket.")
    return io.BytesIO(blob.download_as_bytes())

def upload_to_gcs(bucket_name, blob_name, buffer: io.BytesIO):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_file(buffer, rewind=True)

def file_exists_in_gcs(bucket_name: str, blob_name: str) -> bool:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return blob.exists()

# ✅ Health Check
@app.get("/")
def root():
    return {"status": "ok", "message": "💚 Service is healthy"}

# ✅ Conversion
@app.post("/convert-and-upload")
def convert_and_upload(
    filename: str = Query(...),
    source_format: str = Query(..., pattern="^(csv|json|excel|parquet)$"),
    target_format: str = Query(..., pattern="^(csv|json|excel|parquet)$")
):
    source_buffer = download_from_gcs(BUCKET_NAME, filename)
    df = read_from_buffer(source_buffer, source_format)
    converted_buffer = convert_to_buffer(df, target_format)

    base_name = filename.split("/")[-1].rsplit(".", 1)[0]
    converted_filename = f"{UPLOAD_PREFIX}{base_name}_converted.{get_extension(target_format)}"
    upload_to_gcs(BUCKET_NAME, converted_filename, converted_buffer)

    return {"message": "✅ Conversion successful", "converted_file_path": f"gs://{BUCKET_NAME}/{converted_filename}"}

# ✅ Profiling
class ProfileRequest(BaseModel):
    bucket_name: str
    current_blob: str
    baseline_blob: Optional[str] = None

@app.post("/profile")
def generate_profile(request: ProfileRequest):
    bucket = request.bucket_name
    current_blob = request.current_blob
    baseline_blob = request.baseline_blob

    current_df = load_data(bucket, current_blob)
    profile_result = profile_dataframe(current_df)

    profile_blob = f"profiling/{os.path.splitext(os.path.basename(current_blob))[0]}_profile.json"
    profile_url = upload_json_to_gcs(profile_result, bucket, profile_blob)

    result = {"profile_url": profile_url}

    if baseline_blob:
        baseline_df = load_data(bucket, baseline_blob)
        drift_result = detect_drift(baseline_df, current_df)
        drift_blob = f"profiling/{os.path.splitext(os.path.basename(current_blob))[0]}_drift.json"
        drift_url = upload_json_to_gcs(drift_result, bucket, drift_blob)
        result["drift_url"] = drift_url

    return result

# ✅ Normalization
@app.post("/normalize")
async def normalize_handler(request: Request):
    data = await request.json()
    name = data.get("name")
    bucket = data.get("bucket")

    if not name or not bucket:
        return JSONResponse(content={"error": "Missing 'name' or 'bucket'"}, status_code=400)

    if not any(name.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        return JSONResponse(content={"message": f"Ignored unsupported file: {name}"}, status_code=200)

    gcs_path = f"gs://{bucket}/{name}"
    if not file_exists_in_gcs(bucket, name):
        return JSONResponse(content={"error": f"File not found: {gcs_path}"}, status_code=404)

    output_path = normalize_file(gcs_path)
    return {"message": "✅ Normalization complete", "output_path": output_path}

# ✅ Validation
@app.post("/validate")
async def validate_file(request: Request):
    data = await request.json()
    bucket_name = data.get("bucket")
    file_name = data.get("name")

    if not bucket_name or not file_name:
        raise HTTPException(status_code=400, detail="Missing 'bucket' or 'name'")

    if not file_name.endswith(SUPPORTED_FORMATS):
        raise HTTPException(status_code=400, detail="Unsupported file format")

    tmp_path = f"/tmp/{os.path.basename(file_name)}"
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(file_name)
    blob.download_to_filename(tmp_path)

    if file_name.endswith(".csv"):
        df = pd.read_csv(tmp_path)
    elif file_name.endswith(".json"):
        df = pd.read_json(tmp_path)
    elif file_name.endswith(".xlsx"):
        df = pd.read_excel(tmp_path)
    elif file_name.endswith(".parquet"):
        df = pd.read_parquet(tmp_path)

    with open("validation_rules.json") as f:
        rules = json.load(f)

    result = validate(df, rules)
    result_blob = bucket.blob(f"validation-results/{file_name}.results.json")
    result_blob.upload_from_string(json.dumps(result, indent=2))

    return JSONResponse(content={"status": "success", "file": file_name})

# ✅ Prediction: Columns
@app.post("/columns")
async def get_columns(request: Request):
    data = await request.json()
    bucket_name = data.get("bucket_name")
    scaled_blob_path = data.get("scaled_blob_path")

    if not bucket_name or not scaled_blob_path:
        return JSONResponse(status_code=400, content={"error": "Missing 'bucket_name' or 'scaled_blob_path'"})

    if not file_exists_in_gcs(bucket_name, scaled_blob_path):
        return JSONResponse(status_code=404, content={"error": "File not found in GCS"})

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, "temp.parquet")
        download_blob(bucket_name, scaled_blob_path, file_path)
        df = pd.read_parquet(file_path)
        return {"columns": df.columns.tolist()}

# ✅ Prediction: Run Model
@app.post("/predict")
async def predict(request: Request):
    data = await request.json()
    bucket_name = data.get("bucket_name")
    scaled_blob_path = data.get("scaled_blob_path")
    target_column = data.get("target_column")

    if not bucket_name or not scaled_blob_path or not target_column:
        return JSONResponse(status_code=400, content={"error": "Missing required fields"})

    if not file_exists_in_gcs(bucket_name, scaled_blob_path):
        return JSONResponse(status_code=404, content={"error": "File not found in GCS"})

    result = predict_from_parquet(bucket_name, scaled_blob_path, target_column)
    return JSONResponse(content=result)

# ✅ Run Locally
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
