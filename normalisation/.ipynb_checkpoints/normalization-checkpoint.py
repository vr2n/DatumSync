# normalization_service.py
import io
import json
import logging
import argparse
import pandas as pd
import numpy as np
from google.cloud import storage
from scipy.stats import normaltest
from scipy.stats.mstats import winsorize
from sklearn.preprocessing import LabelEncoder, MinMaxScaler, OneHotEncoder
import pyarrow.parquet as pq
import pyarrow as pa

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_parquet_from_gcs(gcs_path):
    try:
        gcs_client = storage.Client()
        bucket_name, blob_name = gcs_path.replace("gs://", "").split("/", 1)
        blob = gcs_client.bucket(bucket_name).blob(blob_name)
        df = pd.read_parquet(io.BytesIO(blob.download_as_bytes()))
        return df
    except Exception as e:
        logger.error(f"Error loading file from GCS: {e}")
        raise

def detect_outliers(df, method=None, threshold=1.5):
    outlier_percentages = {}
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    if method is None:
        sample = df.sample(frac=0.1, random_state=42)
        normality_pvals = sample[numeric_cols].apply(lambda x: normaltest(x.dropna())[1])
        method = "zscore" if (normality_pvals > 0.05).all() else "iqr"
        logger.info(f"Auto-selected method: {method}")
    for col in numeric_cols:
        if method == "iqr":
            Q1, Q3 = df[col].quantile([0.25, 0.75])
            IQR = Q3 - Q1
            lower, upper = Q1 - threshold * IQR, Q3 + threshold * IQR
            mask = (df[col] < lower) | (df[col] > upper)
        else:
            mean, std = df[col].mean(), df[col].std()
            mask = abs((df[col] - mean) / std) > threshold
        outlier_percentages[col] = (mask.sum() / len(df)) * 100
    return outlier_percentages

def clean_or_winsorize(df, outlier_percentages, threshold=5):
    for col, percent in outlier_percentages.items():
        if col not in df.columns: continue
        Q1, Q3 = df[col].quantile([0.25, 0.75])
        IQR = Q3 - Q1
        lower, upper = Q1 - 1.5 * IQR, Q3 + 1.5 * IQR
        if percent <= threshold:
            df[col] = df[col].where((df[col] >= lower) & (df[col] <= upper))
        else:
            df[col] = pd.Series(winsorize(df[col], limits=(0.05, 0.05)))
    return df

def encode_categorical(df):
    categorical_cols = df.select_dtypes(include=["object", "category"]).columns
    for col in categorical_cols:
        if df[col].nunique() <= 10:
            encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
            encoded = pd.DataFrame(encoder.fit_transform(df[[col]]),
                                   columns=[f"{col}_{i}" for i in range(encoder.fit(df[[col]]).categories_[0].shape[0])])
            df = df.drop(columns=[col]).join(encoded)
        else:
            df[col] = df[col].astype(str)
            df[col] = LabelEncoder().fit_transform(df[col])
    return df

def scale_numerical(df):
    numerical_cols = df.select_dtypes(include=["float64", "int64"]).columns
    scaler = MinMaxScaler()
    df[numerical_cols] = scaler.fit_transform(df[numerical_cols])
    return df

def save_parquet_to_gcs(df, output_path):
    try:
        gcs_client = storage.Client()
        bucket_name, blob_name = output_path.replace("gs://", "").split("/", 1)
        bucket = gcs_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        sink = pa.BufferOutputStream()
        schema = pa.Schema.from_pandas(df)
        with pq.ParquetWriter(sink, schema=schema, compression="snappy") as writer:
            writer.write_table(pa.Table.from_pandas(df))

        blob.upload_from_string(sink.getvalue().to_pybytes(), content_type="application/octet-stream")
        logger.info(f"✅ Uploaded processed data to: {output_path}")
    except Exception as e:
        logger.error(f"❌ Error saving file to GCS: {e}")
        raise

def main(input_path, output_path):
    df = load_parquet_from_gcs(input_path)
    logger.info(f"✅ Loaded data with shape: {df.shape}")

    df.dropna(axis=1, how='all', inplace=True)
    for col in df.select_dtypes(include=["object"]):
        try:
            df[col] = pd.to_datetime(df[col], format='%Y-%m-%d', errors='raise')
        except:
            continue
    df.fillna(df.median(numeric_only=True), inplace=True)
    logger.info("✅ Missing values handled")

    outlier_percentages = detect_outliers(df)
    df = clean_or_winsorize(df, outlier_percentages)
    logger.info("✅ Outliers processed")

    df = encode_categorical(df)
    logger.info("✅ Categorical features encoded")

    df = scale_numerical(df)
    logger.info("✅ Data scaled")

    save_parquet_to_gcs(df, output_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="GCS path to input Parquet file")
    parser.add_argument("--output", required=True, help="GCS path for output Parquet file")
    args = parser.parse_args()
    main(args.input, args.output)
