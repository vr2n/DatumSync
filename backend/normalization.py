import io
import numpy as np
import pandas as pd
from google.cloud import storage
from scipy.stats import normaltest
from scipy.stats.mstats import winsorize
from sklearn.preprocessing import LabelEncoder, MinMaxScaler, OneHotEncoder
import pyarrow.parquet as pq
import pyarrow as pa
import logging

# Load data from GCS
def load_file_from_gcs(gcs_path):
    client = storage.Client()
    bucket_name, blob_name = gcs_path.replace("gs://", "").split("/", 1)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    if not blob.exists():
        raise FileNotFoundError(f"File not found: {gcs_path}")

    file_bytes = blob.download_as_bytes()
    ext = gcs_path.split(".")[-1].lower()

    if ext == "csv":
        return pd.read_csv(io.BytesIO(file_bytes))
    elif ext in ["xlsx", "xls"]:
        return pd.read_excel(io.BytesIO(file_bytes))
    elif ext == "parquet":
        return pd.read_parquet(io.BytesIO(file_bytes))
    else:
        raise ValueError("Unsupported file type")

# Detect outliers
def detect_outliers(df, method=None, threshold=1.5):
    outlier_percentages = {}
    numeric_cols = df.select_dtypes(include=[np.number]).columns

    if method is None:
        sample = df.sample(frac=0.1, random_state=42)
        normality_pvals = sample[numeric_cols].apply(lambda x: normaltest(x.dropna())[1] if x.dropna().shape[0] > 8 else np.nan)
        normality_pvals = normality_pvals.dropna()

        if not normality_pvals.empty and (normality_pvals > 0.05).all():
            method = "zscore"
        else:
            method = "iqr"
        logging.info(f"Auto-selected outlier method: {method}")

    for col in numeric_cols:
        if method == "iqr":
            Q1, Q3 = df[col].quantile([0.25, 0.75])
            IQR = Q3 - Q1
            lower, upper = Q1 - threshold * IQR, Q3 + threshold * IQR
            mask = (df[col] < lower) | (df[col] > upper)
        elif method == "zscore":
            mean, std = df[col].mean(), df[col].std()
            mask = abs((df[col] - mean) / std) > threshold
        else:
            raise ValueError("Invalid method")

        outlier_percentages[col] = (mask.sum() / len(df)) * 100
    return outlier_percentages

# Handle outliers
def clean_or_winsorize(df, outlier_percentages, threshold=5):
    for col, pct in outlier_percentages.items():
        if not np.issubdtype(df[col].dtype, np.number):
            continue
        Q1, Q3 = df[col].quantile([0.25, 0.75])
        IQR = Q3 - Q1
        lower, upper = Q1 - 1.5 * IQR, Q3 + 1.5 * IQR
        if pct <= threshold:
            df[col] = df[col].where((df[col] >= lower) & (df[col] <= upper))
        else:
            df[col] = winsorize(df[col], limits=(0.05, 0.05))
    return df

# Encode categoricals
def encode_categorical(df):
    cat_cols = df.select_dtypes(include=["object", "category"]).columns
    for col in cat_cols:
        unique_vals = df[col].nunique()
        if unique_vals <= 10:
            enc = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
            transformed = enc.fit_transform(df[[col]])
            col_names = [f"{col}_{i}" for i in range(transformed.shape[1])]
            df = df.drop(columns=[col]).join(pd.DataFrame(transformed, columns=col_names, index=df.index))
        else:
            df[col] = LabelEncoder().fit_transform(df[col].astype(str))
    return df

# Scale numeric features
def scale_numerical(df):
    num_cols = df.select_dtypes(include=["float64", "int64"]).columns
    if not num_cols.empty:
        scaler = MinMaxScaler()
        df[num_cols] = scaler.fit_transform(df[num_cols])
    return df

# Save DataFrame to Parquet in GCS
def save_parquet_to_gcs(df, output_path):
    client = storage.Client()
    bucket_name, blob_name = output_path.replace("gs://", "").split("/", 1)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    sink = pa.BufferOutputStream()
    table = pa.Table.from_pandas(df)
    with pq.ParquetWriter(sink, schema=table.schema, compression="snappy") as writer:
        writer.write_table(table)

    blob.upload_from_string(sink.getvalue().to_pybytes(), content_type="application/octet-stream")
    logging.info(f"✅ Saved normalized data to: {output_path}")

# Master normalization function
def normalize_file(gcs_path):
    logging.info(f"📥 Starting normalization for: {gcs_path}")
    df = load_file_from_gcs(gcs_path)

    # Drop fully empty columns
    df.dropna(axis=1, how="all", inplace=True)

    # Try converting object to datetime if >50% valid
    for col in df.columns:
        if df[col].dtype == "object":
            converted = pd.to_datetime(df[col], errors="coerce", format="%Y-%m-%d")
            if converted.notna().sum() > 0.5 * len(df):
                df[col] = converted
                logging.info(f"🕒 Converted {col} to datetime")

    # Fill missing values
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].median())

    # Process outliers
    outliers = detect_outliers(df)
    df = clean_or_winsorize(df, outliers)

    # Encode & scale
    df = encode_categorical(df)
    df = scale_numerical(df)

    # Output path
    output_path = gcs_path.replace("raw/", "normalized/").rsplit(".", 1)[0] + "_normalized.parquet"
    save_parquet_to_gcs(df, output_path)

    logging.info(f"✅ Finished normalization for: {gcs_path}")
    return output_path
