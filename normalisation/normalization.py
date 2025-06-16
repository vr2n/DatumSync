import io
import numpy as np
import pandas as pd
from google.cloud import storage
from scipy.stats import normaltest
from scipy.stats.mstats import winsorize
from sklearn.preprocessing import LabelEncoder, MinMaxScaler, OneHotEncoder
import pyarrow.parquet as pq
import pyarrow as pa

# ✅ Load data from GCS
def load_parquet_from_gcs(gcs_path):
    gcs_client = storage.Client()
    bucket_name, blob_name = gcs_path.replace("gs://", "").split("/", 1)
    bucket = gcs_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    
    parquet_bytes = blob.download_as_bytes()
    df = pd.read_parquet(io.BytesIO(parquet_bytes))
    
    return df

# ✅ Outlier detection
def detect_outliers(df, method=None, threshold=1.5):
    outlier_percentages = {}
    numeric_cols = df.select_dtypes(include=[np.number]).columns

    if method is None:
        sample = df.sample(frac=0.1, random_state=42)
        normality_pvals = sample[numeric_cols].apply(lambda x: normaltest(x.dropna())[1])
        method = "zscore" if (normality_pvals > 0.05).all() else "iqr"
        print(f"Auto-selected method: {method}")

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
            raise ValueError("Method must be 'iqr' or 'zscore'.")

        outlier_percentages[col] = (mask.sum() / len(df)) * 100
    
    return outlier_percentages

# ✅ Clean or Winsorize
def clean_or_winsorize(df, outlier_percentages, threshold=5):
    for col, percent in outlier_percentages.items():
        Q1, Q3 = df[col].quantile([0.25, 0.75])
        IQR = Q3 - Q1
        lower, upper = Q1 - 1.5 * IQR, Q3 + 1.5 * IQR
        if percent <= threshold:
            df[col] = df[col].where((df[col] >= lower) & (df[col] <= upper))
        else:
            df[col] = winsorize(df[col], limits=(0.05, 0.05))
    return df

# ✅ Encode categoricals
def encode_categorical(df):
    categorical_cols = df.select_dtypes(include=["object", "category"]).columns
    for col in categorical_cols:
        unique_count = df[col].nunique()
        if unique_count <= 10:
            encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
            encoded = pd.DataFrame(encoder.fit_transform(df[[col]]), columns=[f"{col}_{i}" for i in range(unique_count)])
            df = df.join(encoded).drop(columns=[col])
        else:
            df[col] = LabelEncoder().fit_transform(df[col])
    return df

# ✅ Scale
def scale_numerical(df):
    numerical_cols = df.select_dtypes(include=["float64", "int64"]).columns
    scaler = MinMaxScaler()
    df[numerical_cols] = scaler.fit_transform(df[numerical_cols])
    return df

# ✅ Save to GCS
def save_parquet_to_gcs(df, output_path):
    gcs_client = storage.Client()
    bucket_name, blob_name = output_path.replace("gs://", "").split("/", 1)
    bucket = gcs_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    
    sink = pa.BufferOutputStream()
    schema = pa.Schema.from_pandas(df)
    with pq.ParquetWriter(sink, schema=schema, compression="snappy") as writer:
        writer.write_table(pa.Table.from_pandas(df))
    
    blob.upload_from_string(sink.getvalue().to_pybytes(), content_type="application/octet-stream")
    print(f"✅ Successfully uploaded processed data to: {output_path}")

# ✅ This is now callable from main.py
def normalize_file(gcs_path):
    df = load_parquet_from_gcs(gcs_path)
    print("✅ Data loaded successfully. Columns:", df.columns.tolist())

    df.dropna(axis=1, how='all', inplace=True)
    df = df.apply(lambda col: pd.to_datetime(col, format='%Y-%m-%d', errors='coerce') if col.dtype == 'object' else col)
    df.fillna(df.median(numeric_only=True), inplace=True)
    print("✅ Missing values imputed.")

    outlier_percentages = detect_outliers(df)
    df = clean_or_winsorize(df, outlier_percentages)
    print("✅ Outliers processed.")

    df = encode_categorical(df)
    print("✅ Categorical variables encoded.")

    df = scale_numerical(df)
    print("✅ Data scaling completed.")

    output_path = "gs://datumsync/scaled-data.parquet"
    save_parquet_to_gcs(df, output_path)
