from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from datetime import datetime
import os

# ✅ Load environment variables
load_dotenv()

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
            request.session['user'] = {
                "name": userinfo["name"],
                "email": userinfo["email"],
                "picture": userinfo["picture"]
            }
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

    # Simulated stats — replace with actual logic if needed
    stats = {
        "normalization": 42,
        "conversion": 36,
        "prediction": 29,
        "validation": 51,
        "history": 60
    }

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "now": datetime.utcnow(),
        "stats": stats
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
