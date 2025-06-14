from fastapi import FastAPI, Request
import uvicorn
import base64
import json
from normalization_service import normalize_data

app = FastAPI()

@app.post("/")
async def trigger_normalization(request: Request):
    envelope = await request.json()
    message = envelope.get("message")
    if not message:
        return {"error": "Missing Pub/Sub message"}
    
    data = base64.b64decode(message["data"]).decode("utf-8")
    attributes = json.loads(data)

    bucket_name = attributes["bucket"]
    file_name = attributes["name"]

    if not file_name.lower().endswith(('.csv', '.parquet', '.xlsx')):
        return {"message": f"Skipped file: {file_name}"}

    input_path = f"gs://{bucket_name}/{file_name}"
    output_path = f"gs://{bucket_name}/normalized/{file_name.replace('.', '_normalized.')}"
    
    normalize_data(input_path, output_path)
    return {"message": f"✅ Normalization complete for {file_name}"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080)
