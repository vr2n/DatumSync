import os
import json
import base64
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from google.cloud import logging as cloud_logging
from normalization import normalize_file  # ✅ Your existing normalization logic

app = FastAPI()

# ✅ Initialize Google Cloud Logging
cloud_logging.Client().setup_logging()

import logging  # Now Cloud Logging receives logs via standard logging

SUPPORTED_EXTENSIONS = [".csv", ".parquet", ".xlsx"]

@app.post("/")
async def handle_event(request: Request):
    try:
        event = await request.json()
        message = event.get("message", {})
        data_b64 = message.get("data", "")

        # 🧠 Decode base64-encoded message
        data = json.loads(base64.b64decode(data_b64).decode("utf-8"))
        name = data.get("name", "")

        if any(name.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
            file_gcs_path = f"gs://{data.get('bucket')}/{name}"
            logging.info(f"✅ Triggered by: {file_gcs_path}")
            normalize_file(file_gcs_path)
            logging.info(f"📄 Processed: {name}")
        else:
            logging.warning(f"⚠️ Ignored unsupported file: {name}")
        
        return {"message": "Event processed"}

    except Exception as e:
        logging.exception(f"🚨 Error processing event: {str(e)}")
        return JSONResponse(content={"error": "Internal Server Error"}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

