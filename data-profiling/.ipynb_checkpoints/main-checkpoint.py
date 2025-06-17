from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from profiling_utils import load_data, profile_dataframe, detect_drift, upload_json_to_gcs
import os.path  # ✅ Needed for basename and splitext

app = FastAPI()


class ProfileRequest(BaseModel):
    bucket_name: str
    current_blob: str
    baseline_blob: Optional[str] = None


@app.get("/")
def root():
    return {"status": "ok"}


@app.post("/profile")
def generate_profile(request: ProfileRequest):
    """
    Generate profiling report and optionally drift report
    """
    bucket = request.bucket_name
    current_blob = request.current_blob
    baseline_blob = request.baseline_blob

    # Load and profile current dataset
    current_df = load_data(bucket, current_blob)
    profile_result = profile_dataframe(current_df)

    profile_blob = f"profiling/{os.path.splitext(os.path.basename(current_blob))[0]}_profile.json"
    profile_url = upload_json_to_gcs(profile_result, bucket, profile_blob)

    result = {
        "profile_url": profile_url
    }

    # If baseline provided, perform drift detection
    if baseline_blob:
        baseline_df = load_data(bucket, baseline_blob)
        drift_result = detect_drift(baseline_df, current_df)

        drift_blob = f"profiling/{os.path.splitext(os.path.basename(current_blob))[0]}_drift.json"
        drift_url = upload_json_to_gcs(drift_result, bucket, drift_blob)

        result["drift_url"] = drift_url

    return result
