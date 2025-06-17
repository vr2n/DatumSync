from fastapi import FastAPI, Query, HTTPException
from google.cloud import storage
import io
from conversion import read_from_buffer, convert_to_buffer, get_extension

app = FastAPI()

BUCKET_NAME = "datumsync"
UPLOAD_PREFIX = "converted/"

def download_from_gcs(bucket_name, blob_name) -> io.BytesIO:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    if not blob.exists():
        raise HTTPException(status_code=404, detail="File not found in GCS bucket.")

    data = blob.download_as_bytes()
    return io.BytesIO(data)

def upload_to_gcs(bucket_name, blob_name, buffer: io.BytesIO):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_file(buffer, rewind=True)

@app.post("/convert-and-upload")
def convert_and_upload(
    filename: str = Query(..., description="Filename in the GCS bucket"),
    source_format: str = Query(..., pattern="^(csv|json|excel|parquet)$"),
    target_format: str = Query(..., pattern="^(csv|json|excel|parquet)$")
):
    # Step 1: Download source file
    source_buffer = download_from_gcs(BUCKET_NAME, filename)

    # Step 2: Convert
    df = read_from_buffer(source_buffer, source_format)
    converted_buffer = convert_to_buffer(df, target_format)

    # Step 3: Upload result
    base_name = filename.split("/")[-1].rsplit(".", 1)[0]
    converted_filename = f"{UPLOAD_PREFIX}{base_name}_converted.{get_extension(target_format)}"
    upload_to_gcs(BUCKET_NAME, converted_filename, converted_buffer)

    return {
        "message": "✅ Conversion successful",
        "converted_file_path": f"gs://{BUCKET_NAME}/{converted_filename}"
    }
