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
from models import Base, User, ConversionLog
from google.cloud import storage
import uuid

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
    return templates.TemplateResponse("validation.html", {"request": request, "user": user})

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
    return templates.TemplateResponse("conversion.html", {"request": request, "user": user})

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
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")

    user_email = user["email"]
    safe_email = user_email.replace("@", "_").replace(".", "_")
    bucket_name = f"{safe_email}_bucket"
    filename = f"{uuid.uuid4()}_{convert_file.filename}"
    blob_path = f"converted/{filename}"

    try:
        # Upload file to user-specific bucket
        client = storage.Client()
        bucket = client.bucket(bucket_name)

        if not bucket.exists():
            bucket = client.create_bucket(bucket_name)

        blob = bucket.blob(blob_path)
        blob.upload_from_file(convert_file.file, content_type="text/csv")

        # Log to DB
        db: Session = SessionLocal()
        new_log = ConversionLog(
            email=user_email,
            filename=filename,
            format=format,
            gcs_path=f"gs://{bucket_name}/{blob_path}"
        )
        db.add(new_log)
        db.commit()
        db.close()

    except Exception as e:
        print(f"❌ Conversion error: {e}")
        return templates.TemplateResponse("conversion.html", {
            "request": request,
            "user": user,
            "error": f"Upload failed: {str(e)}"
        })

    return RedirectResponse("/convert", status_code=303)