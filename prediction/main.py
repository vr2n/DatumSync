import os
import logging
import pandas as pd
import tempfile
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from google.cloud import storage
from predict import predict_from_parquet, download_blob

# Setup logging
logging.basicConfig(level=logging.INFO)

app = FastAPI()

# Health check
@app.get("/")
async def health_check():
    return {"status": "ok", "message": "🟢 Prediction API is healthy"}

# Utility: Check if file exists in GCS
def gcs_blob_exists(bucket_name: str, blob_name: str) -> bool:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return blob.exists()

# Endpoint: List columns of uploaded parquet file
@app.post("/columns")
async def get_columns(request: Request):
    try:
        data = await request.json()
        logging.info(f"📥 /columns payload: {data}")

        bucket_name = data.get("bucket_name")
        scaled_blob_path = data.get("scaled_blob_path")

        if not bucket_name or not scaled_blob_path:
            return JSONResponse(status_code=400, content={"error": "Missing 'bucket_name' or 'scaled_blob_path'"})

        if not gcs_blob_exists(bucket_name, scaled_blob_path):
            return JSONResponse(status_code=404, content={"error": "File not found in GCS"})

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "temp.parquet")
            download_blob(bucket_name, scaled_blob_path, file_path)
            df = pd.read_parquet(file_path)
            return {"columns": df.columns.tolist()}

    except Exception as e:
        logging.exception("❌ Exception in /columns")
        return JSONResponse(status_code=500, content={"error": f"Error in /columns: {str(e)}"})

# Endpoint: Perform prediction
@app.post("/predict")
async def predict(request: Request):
    try:
        data = await request.json()
        logging.info(f"📥 /predict payload: {data}")

        bucket_name = data.get("bucket_name")
        scaled_blob_path = data.get("scaled_blob_path")
        target_column = data.get("target_column")

        if not bucket_name or not scaled_blob_path or not target_column:
            return JSONResponse(status_code=400, content={"error": "Missing 'bucket_name', 'scaled_blob_path' or 'target_column'"})

        if not gcs_blob_exists(bucket_name, scaled_blob_path):
            return JSONResponse(status_code=404, content={"error": "File not found in GCS"})

        result = predict_from_parquet(bucket_name, scaled_blob_path, target_column)
        return JSONResponse(content=result)

    except Exception as e:
        logging.exception("❌ Exception in /predict")
        return JSONResponse(status_code=500, content={"error": f"Error in /predict: {str(e)}"})

