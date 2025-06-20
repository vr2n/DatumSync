import pandas as pd
import numpy as np
import sys
import json
import os
from google.cloud import storage
from io import BytesIO
from scipy.stats import ks_2samp  # ✅ Added missing import


# === GCS Utilities ===
def download_blob_as_bytes(bucket_name: str, blob_name: str) -> bytes:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return blob.download_as_bytes()


def upload_to_gcs_from_bytes(data: bytes, bucket_name: str, destination_blob_name: str) -> str:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_string(data)

    # Return blob path or signed URL (if needed)
    return f"gs://{bucket_name}/{destination_blob_name}"


# === Data Loader ===
def load_data(bucket_name: str, blob_name: str) -> pd.DataFrame:
    file_bytes = download_blob_as_bytes(bucket_name, blob_name)

    if blob_name.endswith(".csv"):
        return pd.read_csv(BytesIO(file_bytes))
    elif blob_name.endswith(".parquet"):
        return pd.read_parquet(BytesIO(file_bytes))
    else:
        raise ValueError("Unsupported file type. Use CSV or Parquet.")


# === Profiling ===
def profile_column(col: pd.Series) -> dict:
    profile = {
        "dtype": str(col.dtype),
        "null_count": int(col.isnull().sum()),
        "null_percentage": float(col.isnull().mean()) * 100,
        "unique_count": int(col.nunique()),
    }

    if pd.api.types.is_numeric_dtype(col):
        profile.update({
            "min": float(col.min(skipna=True)),
            "max": float(col.max(skipna=True)),
            "mean": float(col.mean(skipna=True)),
            "std": float(col.std(skipna=True)),
        })
    elif pd.api.types.is_string_dtype(col):
        lengths = col.dropna().astype(str).str.len()
        profile.update({
            "min_length": int(lengths.min()) if not lengths.empty else 0,
            "max_length": int(lengths.max()) if not lengths.empty else 0,
            "avg_length": float(lengths.mean()) if not lengths.empty else 0,
        })
        top_freq = col.value_counts().head(5).to_dict()
        profile["top_values"] = {str(k): int(v) for k, v in top_freq.items()}
    elif pd.api.types.is_bool_dtype(col):
        profile["value_counts"] = col.value_counts(dropna=False).to_dict()
    elif pd.api.types.is_datetime64_any_dtype(col):
        profile.update({
            "min": str(col.min(skipna=True)),
            "max": str(col.max(skipna=True)),
        })

    return profile


def profile_dataframe(df: pd.DataFrame) -> dict:
    overall_profile = {
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "duplicate_rows": int(df.duplicated().sum()),
        "memory_usage_mb": float(df.memory_usage(deep=True).sum() / 1024 ** 2),
        "columns": {}
    }

    for col in df.columns:
        overall_profile["columns"][col] = profile_column(df[col])

    return overall_profile


def upload_json_to_gcs(data: dict, bucket_name: str, blob_name: str) -> str:
    json_bytes = json.dumps(data).encode("utf-8")
    return upload_to_gcs_from_bytes(json_bytes, bucket_name, blob_name)


# === Drift Detection ===
def calculate_psi(expected: pd.Series, actual: pd.Series, buckets: int = 10) -> float:
    def scale_bins(series):
        return np.histogram(series, bins=buckets)[0] / len(series)

    expected_percents = scale_bins(expected.dropna())
    actual_percents = scale_bins(actual.dropna())

    psi_value = np.sum([
        (e - a) * np.log((e + 1e-8) / (a + 1e-8))
        for e, a in zip(expected_percents, actual_percents)
    ])
    return psi_value


def detect_drift(baseline_df: pd.DataFrame, current_df: pd.DataFrame, psi_threshold: float = 0.2, null_threshold: float = 10.0) -> dict:
    drift_results = {}
    common_cols = [col for col in baseline_df.columns if col in current_df.columns]

    for col in common_cols:
        baseline_col = baseline_df[col]
        current_col = current_df[col]

        if pd.api.types.is_numeric_dtype(current_col) and pd.api.types.is_numeric_dtype(baseline_col):
            psi_score = calculate_psi(baseline_col, current_col)
            ks_pvalue = ks_2samp(baseline_col.dropna(), current_col.dropna()).pvalue

            mean_diff = abs(current_col.mean() - baseline_col.mean())
            std_diff = abs(current_col.std() - baseline_col.std())

            baseline_null_pct = baseline_col.isnull().mean() * 100
            current_null_pct = current_col.isnull().mean() * 100
            null_increase = current_null_pct - baseline_null_pct

            drift_results[col] = {
                "psi_score": round(psi_score, 4),
                "drift_by_psi": psi_score > psi_threshold,
                "ks_p_value": round(ks_pvalue, 4),
                "drift_by_ks": ks_pvalue < 0.05,
                "mean_baseline": round(baseline_col.mean(), 4),
                "mean_current": round(current_col.mean(), 4),
                "mean_diff": round(mean_diff, 4),
                "std_baseline": round(baseline_col.std(), 4),
                "std_current": round(current_col.std(), 4),
                "std_diff": round(std_diff, 4),
                "null_baseline_pct": round(baseline_null_pct, 2),
                "null_current_pct": round(current_null_pct, 2),
                "null_spike_detected": null_increase > null_threshold
            }

        elif pd.api.types.is_object_dtype(current_col):
            base_freq = baseline_col.value_counts(normalize=True)
            curr_freq = current_col.value_counts(normalize=True)

            overlap = base_freq.index.intersection(curr_freq.index)
            common_overlap = sum(min(base_freq.get(val, 0), curr_freq.get(val, 0)) for val in overlap)

            drift_results[col] = {
                "category_overlap": round(common_overlap, 4),
                "drift_by_low_overlap": common_overlap < 0.6,
                "null_baseline_pct": round(baseline_col.isnull().mean() * 100, 2),
                "null_current_pct": round(current_col.isnull().mean() * 100, 2)
            }

    return drift_results


# === CLI Usage (Optional) ===
def main():
    if len(sys.argv) < 3:
        print("Usage: python profile_utils.py <bucket_name> <current_data_blob> [baseline_data_blob]")
        sys.exit(1)

    bucket_name = sys.argv[1]
    current_blob = sys.argv[2]
    baseline_blob = sys.argv[3] if len(sys.argv) > 3 else None

    current_df = load_data(bucket_name, current_blob)
    current_profile = profile_dataframe(current_df)

    profile_blob_name = f"profiling/{os.path.splitext(os.path.basename(current_blob))[0]}_profile.json"
    profile_url = upload_json_to_gcs(current_profile, bucket_name, profile_blob_name)
    print(f"[✓] Profiling report uploaded to GCS: {profile_url}")

    if baseline_blob:
        baseline_df = load_data(bucket_name, baseline_blob)
        drift_report = detect_drift(baseline_df, current_df)

        drift_blob_name = f"profiling/{os.path.splitext(os.path.basename(current_blob))[0]}_drift.json"
        drift_url = upload_json_to_gcs(drift_report, bucket_name, drift_blob_name)
        print(f"[✓] Drift report uploaded to GCS: {drift_url}")


if __name__ == "__main__":
    main()
