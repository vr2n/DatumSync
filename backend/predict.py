import os
import pandas as pd
import joblib
import tempfile
from google.cloud import storage
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

def download_blob(bucket_name, source_blob_name, destination_file_name):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    blob.download_to_filename(destination_file_name)

def upload_blob(bucket_name, source_file_name, destination_blob_name):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(source_file_name)

def predict_from_parquet(bucket_name, scaled_blob_path, target_column):
    with tempfile.TemporaryDirectory() as tmpdir:
        # Download scaled-data
        local_path = os.path.join(tmpdir, "scaled.parquet")
        download_blob(bucket_name, scaled_blob_path, local_path)

        df = pd.read_parquet(local_path)

        if target_column not in df.columns:
            raise ValueError(f"Target column '{target_column}' not found.")

        X = df.drop(columns=[target_column])
        y = df[target_column]

        # Train-test split (just for internal quality check)
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        # Train a simple classification model
        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)

        predictions = model.predict(X)

        df["prediction"] = predictions

        # Save output
        predictions_parquet_path = os.path.join(tmpdir, "predictions.parquet")
        predictions_json_path = os.path.join(tmpdir, "predictions.json")
        df.to_parquet(predictions_parquet_path, index=False)
        df[["prediction"]].to_json(predictions_json_path, orient="records", lines=False)

        user_prefix = os.path.dirname(scaled_blob_path)
        upload_blob(bucket_name, predictions_parquet_path, f"{user_prefix}/predictions.parquet")
        upload_blob(bucket_name, predictions_json_path, f"{user_prefix}/predictions.json")

        return {
            "message": "✅ Prediction completed.",
            "target_used": target_column,
            "parquet": f"{user_prefix}/predictions.parquet",
            "json": f"{user_prefix}/predictions.json",
            "report": classification_report(y, predictions, output_dict=True)
        }

# Local test runner
if __name__ == "__main__":
    result = predict_from_parquet(
        bucket_name="datumsync",
        scaled_blob_path="df_normalized.parquet",  # Update as needed
        target_column="label"                      # Update as needed
    )
    print(result)
