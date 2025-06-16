from fastapi import FastAPI, Query
from pydantic import BaseModel
from typing import Optional
from profile import (
    download_from_gcs,
    load_data,
    profile_dataframe,
    detect_drift,
    upload_json_to_gcs
)
import os

app = FastAPI()


class ProfileRequest(BaseModel):
    bucket_name: str
    current_blob: str
    baseline_blob: Optional[str] = None


@app.post("/profile")
def generate_profile(request: ProfileRequest):
    bucket = request.bucket_name
    current_blob = request.current_blob
    baseline_blob = request.baseline_blob

    current_path = download_from_gcs(bucket, current_blob)
    current_df = load_data(current_path)
    profile_result = profile_dataframe(current_df)

    profile_blob = f"profiling/{os.path.splitext(os.path.basename(current_blob))[0]}_profile.json"
    profile_url = upload_json_to_gcs(profile_result, bucket, profile_blob)

    result = {
        "profile_url": profile_url
    }

    if baseline_blob:
        baseline_path = download_from_gcs(bucket, baseline_blob)
        baseline_df = load_data(baseline_path)
        drift_result = detect_drift(baseline_df, current_df)

        drift_blob = f"profiling/{os.path.splitext(os.path.basename(current_blob))[0]}_drift.json"
        drift_url = upload_json_to_gcs(drift_result, bucket, drift_blob)

        result["drift_url"] = drift_url

    return result
