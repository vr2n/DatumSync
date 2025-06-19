from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os
from sqlalchemy.orm import Session
from database import SessionLocal, engine
from models import Base, User, ConvertedFile, ValidationResult, NormalizedFile
from google.cloud import storage
import uuid
import requests


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
    client_kwargs={'scope': 'openid email profile'}
)

BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
CLOUD_RUN_URL = "https://datumsync-481763043227.asia-south1.run.app"

# ✅ Index route
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = request.session.get("user")
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

# ✅ Google OAuth Login
@app.get("/login")
async def login(request: Request):
    redirect_uri = "https://datumsync.onrender.com/auth/callback"
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

    # Simulated total stats
    stats = {
        "normalization": 42,
        "conversion": 36,
        "prediction": 29,
        "validation": 51,
        "history": 60
    }

    # Simulated day-wise data for the last 7 days
    today = datetime.utcnow().date()
    stats_by_day = {
        "dates": [(today - timedelta(days=i)).isoformat() for i in reversed(range(7))],
        "validation":   [8, 5, 7, 6, 9, 10, 6],
        "normalization":[4, 3, 5, 4, 6, 7, 5],
        "conversion":   [2, 3, 3, 2, 4, 5, 4],
        "prediction":   [1, 2, 2, 3, 4, 5, 4],
    }

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
    input_file: UploadFile = File(...)  # 👈 matches your form field name
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

    
    
    return RedirectResponse("/normalize", status_code=303)
