import os
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from google.cloud import logging as cloud_logging
from google.cloud import storage
from normalization import normalize_file  # ✅ Your normalization logic

import logging

app = FastAPI()

# ✅ Initialize Google Cloud Logging
cloud_logging.Client().setup_logging()

SUPPORTED_EXTENSIONS = [".csv", ".parquet", ".xlsx"]

# ✅ GCS Existence Checker
def file_exists_in_gcs(bucket_name: str, blob_name: str) -> bool:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return blob.exists()


@app.get("/")
async def health_check():
    return {"status": "ok", "message": "💚 Service is healthy"}

@app.post("/normalize")
async def handle_event(request: Request):
    try:
        data = await request.json()

        name = data.get("name", "")
        bucket = data.get("bucket", "")

        if not name or not bucket:
            logging.warning("⚠️ Missing file name or bucket.")
            return JSONResponse(content={"error": "Missing 'name' or 'bucket'"}, status_code=400)

        if not any(name.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
            logging.warning(f"⚠️ Unsupported file type: {name}")
            return JSONResponse(content={"message": f"Ignored unsupported file: {name}"}, status_code=200)

        gcs_path = f"gs://{bucket}/{name}"

        if not file_exists_in_gcs(bucket, name):
            logging.error(f"❌ GCS file not found: {gcs_path}")
            return JSONResponse(content={"error": f"File not found: {gcs_path}"}, status_code=404)

        logging.info(f"✅ Triggered by: {gcs_path}")
        output_path = normalize_file(gcs_path)
        logging.info(f"📄 Successfully processed and saved to: {output_path}")

        return {"message": "Event processed successfully", "output_path": output_path}

    except Exception as e:
        logging.exception(f"🚨 Error processing event: {str(e)}")
        return JSONResponse(content={"error": f"Internal Server Error: {str(e)}"}, status_code=500)



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
