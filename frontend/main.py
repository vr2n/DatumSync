from fastapi import FastAPI, Request, UploadFile, File, Form, Depends
from fastapi.responses import JSONResponse,HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os
from sqlalchemy.orm import Session
from database import SessionLocal, engine
from models import Base, User, ConvertedFile, ValidationResult, NormalizedFile, ProfileResult, PredictionResult
from google.cloud import storage
import uuid
import requests
from sqlalchemy import func, cast, Date
from stripe_utils import create_checkout_session



# ✅ Load environment variables
load_dotenv()
Base.metadata.create_all(bind=engine)

# ✅ Initialize FastAPI
app = FastAPI()

# ✅ Middleware for session handling
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "default-secret-key"))

# ✅ Template folder setup
templates = Jinja2Templates(directory="templates")

# ✅ OAuth Configuration
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    authorize_url='https://accounts.google.com/o/oauth2/v2/auth',
    access_token_url='https://oauth2.googleapis.com/token',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
    redirect_uri=os.getenv("REDIRECT_URI")  # 👈 Add this
)

BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
CLOUD_RUN_URL = "https://datumsync-481763043227.asia-south1.run.app"

def get_dashboard_stats(db: Session, email: str):
    return {
        "validation": db.query(func.count(ValidationResult.id)).filter(ValidationResult.email == email).scalar(),
        "normalization": db.query(func.count(NormalizedFile.id)).filter(NormalizedFile.email == email).scalar(),
        "conversion": db.query(func.count(ConvertedFile.id)).filter(ConvertedFile.email == email).scalar(),
        "prediction": db.query(func.count(PredictionResult.id)).filter(PredictionResult.email == email).scalar(),
        "history": db.query(func.count(ValidationResult.id)).filter(ValidationResult.email == email).scalar() +
                   db.query(func.count(NormalizedFile.id)).filter(NormalizedFile.email == email).scalar() +
                   db.query(func.count(ConvertedFile.id)).filter(ConvertedFile.email == email).scalar() +
                   db.query(func.count(PredictionResult.id)).filter(PredictionResult.email == email).scalar()
    }

def get_weekly_stats(db: Session, email: str):
    today = datetime.utcnow().date()
    past_7_days = [(today - timedelta(days=i)) for i in reversed(range(7))]
    dates_iso = [d.isoformat() for d in past_7_days]

    def query_daywise(model):
        results = (
            db.query(cast(model.created_at, Date).label("date"), func.count().label("count"))
            .filter(model.email == email)
            .filter(model.created_at >= today - timedelta(days=6))
            .group_by("date")
            .all()
        )
        count_map = {row.date.isoformat(): row.count for row in results}
        return [count_map.get(d, 0) for d in dates_iso]

    return {
        "dates": dates_iso,
        "validation": query_daywise(ValidationResult),
        "normalization": query_daywise(NormalizedFile),
        "conversion": query_daywise(ConvertedFile),
        "prediction": query_daywise(PredictionResult),
    }
@app.api_route("/health", methods=["GET", "HEAD"])
def health_check():
    return {"status": "ok"}

# ✅ Index route
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = request.session.get("user")
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

# ✅ Google OAuth Login
@app.get("/login")
async def login(request: Request):
    redirect_uri = os.getenv("REDIRECT_URI")
    return await oauth.google.authorize_redirect(request, redirect_uri)

# ✅ Google OAuth Callback
@app.get("/auth/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        userinfo = token.get('userinfo')
        if userinfo:
            user_data = {
                "name": userinfo["name"],
                "email": userinfo["email"],
                "picture": userinfo["picture"]
            }
            request.session['user'] = user_data

            # ✅ Save user to Supabase PostgreSQL if not exists
            db: Session = SessionLocal()
            existing_user = db.query(User).filter(User.email == user_data["email"]).first()
            if not existing_user:
                new_user = User(**user_data)
                db.add(new_user)
                db.commit()
            db.close()

        return RedirectResponse(url="/dashboard")

    except Exception as e:
        print("❌ Auth callback error:", e)
        return RedirectResponse(url="/?error=auth_failed")
    


# ✅ Logout
@app.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/")

# ✅ Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    db = SessionLocal()
    try:
        stats = get_dashboard_stats(db, user["email"])
        stats_by_day = get_weekly_stats(db, user["email"])
    finally:
        db.close()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "now": datetime.utcnow(),
        "stats": stats,
        "stats_by_day": stats_by_day
    })


# ✅ Validation Module
@app.get("/validate", response_class=HTMLResponse)
async def validate_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    db = SessionLocal()
    results = db.query(ValidationResult).filter(ValidationResult.email == user["email"]).order_by(ValidationResult.created_at.desc()).all()
    db.close()

    return templates.TemplateResponse("validation.html", {
        "request": request,
        "user": user,
        "results": results
    })


# ✅ Normalization Module
@app.get("/normalize", response_class=HTMLResponse)
async def normalize_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("normalization.html", {"request": request, "user": user})

# ✅ Conversion Module
@app.get("/convert", response_class=HTMLResponse)
async def convert_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    db: Session = SessionLocal()
    records = db.query(ConvertedFile).filter(ConvertedFile.email == user["email"]).order_by(ConvertedFile.created_at.desc()).all()
    db.close()

    return templates.TemplateResponse("conversion.html", {"request": request, "user": user, "records": records})

# ✅ Prediction Module
@app.get("/predict", response_class=HTMLResponse)
async def predict_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("prediction.html", {"request": request, "user": user})

# ✅ Data Profiling Module
@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("profiling.html", {"request": request, "user": user})

# ✅ Reports Module
@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    # Optionally add user-specific report history or stats
    return templates.TemplateResponse("reports.html", {"request": request, "user": user})

# ✅ Account Settings
@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("settings.html", {"request": request, "user": user})

#✅ Subscription
@app.get("/subscription", response_class=HTMLResponse)
async def subscription_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    return templates.TemplateResponse("subscription.html", {
        "request": request,
        "user": user
    })

@app.get("/subscription/success", response_class=HTMLResponse)
async def stripe_success(request: Request):
    user = request.session.get("user")
    return templates.TemplateResponse("subscription_success.html", {"request": request, "user": user})

@app.get("/subscription/cancel", response_class=HTMLResponse)
async def stripe_cancel(request: Request):
    user = request.session.get("user")
    return templates.TemplateResponse("subscription_cancel.html", {"request": request, "user": user})


@app.get("/subscribe/pro")
async def subscribe_pro(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    email = user["email"]
    session_url = create_checkout_session(email)

    if session_url:
        return RedirectResponse(session_url)
    return {"error": "Unable to create Stripe checkout session"}

@app.post("/convert-file")
async def handle_conversion(
    request: Request,
    convert_file: UploadFile = File(...),
    format: str = Form(...)
):
    # ✅ Check user session
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    user_email = user["email"]
    # ✅ Generate GCS path with user's email
    filename = f"{user_email}/{uuid.uuid4().hex}_{convert_file.filename}"

    # ✅ Upload original file to GCS
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_file(convert_file.file)

    # ✅ Call Cloud Run conversion endpoint
    params = {
        "filename": filename,
        "source_format": "csv",      # hardcoded since file uploaded is CSV
        "target_format": format      # user-selected target format
    }
    response = requests.post(f"{CLOUD_RUN_URL}/convert-and-upload", params=params)

    # ✅ If conversion succeeds, store metadata in DB
    if response.status_code == 200:
        converted_path = response.json().get("converted_file_path")

        db: Session = SessionLocal()
        db_entry = ConvertedFile(
            email=user_email,
            original_file=filename,
            converted_path=converted_path,
            format=format,
            created_at=datetime.utcnow()
        )
        db.add(db_entry)
        db.commit()
        db.close()

    # ✅ Redirect back to Conversion Page
    return RedirectResponse("/convert", status_code=303)

@app.post("/validate-files")
async def handle_validation(
    request: Request,
    source_file: UploadFile = File(...),
    target_file: UploadFile = File(...)
):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    user_email = user["email"]

    # ✅ Generate unique file paths
    source_filename = f"{user_email}/{uuid.uuid4().hex}_{source_file.filename}"
    target_filename = f"{user_email}/{uuid.uuid4().hex}_{target_file.filename}"

    # ✅ Upload to GCS
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    bucket.blob(source_filename).upload_from_file(source_file.file)
    bucket.blob(target_filename).upload_from_file(target_file.file)

    # ✅ Call validation Cloud Run for both files
    for file in [source_filename, target_filename]:
        payload = {
            "bucket": BUCKET_NAME,
            "name": file
        }
        try:
            response = requests.post(f"{CLOUD_RUN_URL}/validate", json=payload)
            response.raise_for_status()
        except Exception as e:
            print("❌ Validation error:", e)

    # ✅ Compute validation result path
    result_path = f"validation-results/{source_filename}.results.json"

    # ✅ Insert into Supabase DB
    db: Session = SessionLocal()
    db_entry = ValidationResult(
        email=user_email,
        source_file=source_filename,
        target_file=target_filename,
        result_path=result_path,
        status="success",
        created_at=datetime.utcnow()
    )
    db.add(db_entry)
    db.commit()
    db.close()

    return RedirectResponse("/validate", status_code=303)

@app.post("/normalize-file")
async def handle_normalization(
    request: Request,
    input_file: UploadFile = File(...)
):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    user_email = user["email"]
    filename = f"{user_email}/{uuid.uuid4().hex}_{input_file.filename}"

    # ✅ Upload to GCS
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_file(input_file.file)

    # ✅ Call Cloud Run normalization endpoint
    payload = {
        "bucket": BUCKET_NAME,
        "name": filename
    }

    try:
        response = requests.post(f"{CLOUD_RUN_URL}/normalize", json=payload)
        response.raise_for_status()
    except Exception as e:
        print("❌ Normalization error:", e)
        return RedirectResponse("/normalize?error=true", status_code=303)

    output_path = response.json().get("output_path")

    # ✅ Insert normalization record into DB
    try:
        db: Session = SessionLocal()
        db_entry = NormalizedFile(
            email=user_email,
            input_file=filename,
            normalized_file=output_path,
            status="success",
            created_at=datetime.utcnow()
        )
        db.add(db_entry)
        db.commit()
    except Exception as e:
        print("❌ DB insert error (normalization):", e)
    finally:
        db.close()

    return RedirectResponse("/normalize", status_code=303)

@app.post("/profile-file")
async def handle_profiling(
    request: Request,
    profile_file: UploadFile = File(...)
):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    user_email = user["email"]
    filename = f"{user_email}/{uuid.uuid4().hex}_{profile_file.filename}"

    # ✅ Upload the file to GCS
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_file(profile_file.file)

    # ✅ Call Cloud Run profiling endpoint
    payload = {
        "bucket_name": BUCKET_NAME,
        "current_blob": filename,
        "baseline_blob": None  # optional, you can extend later
    }

    try:
        response = requests.post(f"{CLOUD_RUN_URL}/profile", json=payload)
        response.raise_for_status()
        result = response.json()
    except Exception as e:
        print("❌ Profiling error:", e)
        return RedirectResponse("/profile", status_code=303)

    # ✅ Save result to Supabase DB
    profile_url = result.get("profile_url")
    drift_url = result.get("drift_url")

    db: Session = SessionLocal()
    db_entry = ProfileResult(
        email=user_email,
        input_file=filename,
        profile_url=profile_url,
        drift_url=drift_url,
        created_at=datetime.utcnow()
    )
    db.add(db_entry)
    db.commit()
    db.close()

    return RedirectResponse("/profile", status_code=303)

@app.post("/upload-temp")
async def upload_temp_file(predict_file: UploadFile = File(...)):
    user_email = "anonymous"  # Update with real user session if needed
    filename = f"{user_email}/{uuid.uuid4().hex}_{predict_file.filename}"

    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        bucket.blob(filename).upload_from_file(predict_file.file)
        return {"bucket_name": BUCKET_NAME, "blob_path": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GCS upload failed: {str(e)}")


@app.post("/predict-file")
async def predict_file(
    request: Request,
    predict_file: UploadFile = File(...),
    target: str = Form(...)
):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    user_email = user["email"]
    suffix = os.path.splitext(predict_file.filename)[-1].lower()
    if suffix not in [".parquet", ".csv"]:
        return JSONResponse(status_code=400, content={"error": "Invalid file type"})

    blob_path = f"{user_email}/{uuid.uuid4().hex}_{predict_file.filename}"
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        bucket.blob(blob_path).upload_from_file(predict_file.file)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"GCS upload failed: {str(e)}"})

    try:
        prediction_response = requests.post(
            f"{CLOUD_RUN_URL}/predict",
            json={
                "bucket_name": BUCKET_NAME,
                "scaled_blob_path": blob_path,
                "target_column": target
            }
        )
        prediction_response.raise_for_status()
        prediction_result = prediction_response.json()
    except Exception as e:
        print("❌ Prediction error:", e)
        return JSONResponse(status_code=500, content={"error": "Prediction failed"})

    try:
        db: Session = SessionLocal()
        db_entry = PredictionResult(
            email=user_email,
            file_path=blob_path,
            target_column=target,
            result_summary=prediction_result,
            status="success",
            created_at=datetime.utcnow()
        )
        db.add(db_entry)
        db.commit()
    except Exception as db_err:
        print("⚠️ DB insert failed:", db_err)
    finally:
        db.close()

    return JSONResponse(content={"result": prediction_result})


@app.post("/columns")
async def get_columns(request: Request):
    data = await request.json()
    bucket_name = data.get("bucket_name")
    scaled_blob_path = data.get("scaled_blob_path")

    if not bucket_name or not scaled_blob_path:
        return JSONResponse(status_code=400, content={"error": "Missing 'bucket_name' or 'scaled_blob_path'"})

    def file_exists(bucket, name):
        return storage.Client().bucket(bucket).blob(name).exists()

    if not file_exists(bucket_name, scaled_blob_path):
        return JSONResponse(status_code=404, content={"error": "File not found in GCS"})

    import pandas as pd
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, "temp.parquet")
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(scaled_blob_path)
        blob.download_to_filename(file_path)
        df = pd.read_parquet(file_path)
        return {"columns": df.columns.tolist()}

@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    db: Session = SessionLocal()
    email = user["email"].lower()
    history = []

    # ✅ Validation Reports
    validations = db.query(ValidationResult).filter(
        func.lower(ValidationResult.email) == email
    ).all()
    for v in validations:
        history.append({
            "file": v.source_file,
            "module": "Validation",
            "status": v.status,
            "created_at": v.created_at,
            "email": v.email,
            "view": v.result_path or "#",
            "id": v.id
        })

    # ✅ Normalization Reports
    normalizations = db.query(NormalizedFile).filter(
        func.lower(NormalizedFile.email) == email
    ).all()
    for n in normalizations:
        history.append({
            "file": n.input_file,
            "module": "Normalization",
            "status": n.status,
            "created_at": n.created_at,
            "email": n.email,
            "view": n.normalized_file or "#",
            "id": n.id
        })

    # ✅ Conversion Reports
    conversions = db.query(ConvertedFile).filter(
        func.lower(ConvertedFile.email) == email
    ).all()
    for c in conversions:
        history.append({
            "file": c.original_file,
            "module": "Conversion",
            "status": "success",
            "created_at": c.created_at,
            "email": c.email,
            "view": c.converted_path or "#",
            "id": c.id
        })

    # ✅ Prediction Reports
    predictions = db.query(PredictionResult).filter(
        func.lower(PredictionResult.email) == email
    ).all()
    for p in predictions:
        history.append({
            "file": p.file_path,
            "module": "Prediction",
            "status": p.status,
            "created_at": p.created_at,
            "email": p.email,
            "view": f"/view/prediction/{p.id}",
            "id": p.id
        })

    # ✅ Profiling Reports
    profiles = db.query(ProfileResult).filter(
        func.lower(ProfileResult.email) == email
    ).all()
    for pr in profiles:
        history.append({
            "file": pr.input_file,
            "module": "Profiling",
            "status": "success",
            "created_at": pr.created_at,
            "email": pr.email,
            "view": pr.profile_url or "#",
            "id": pr.id
        })

    db.close()

    history.sort(key=lambda x: x["created_at"] or datetime.min, reverse=True)

    return templates.TemplateResponse("reports.html", {
        "request": request,
        "user": user,
        "history": history
    })