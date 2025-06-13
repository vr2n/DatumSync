from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
from starlette.config import Config
import os
from dotenv import load_dotenv

# ✅ Load environment variables
load_dotenv()

app = FastAPI()

# ✅ Middleware for session management
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "your-default-secret-key"))

# ✅ Template setup
templates = Jinja2Templates(directory="templates")

# ✅ OAuth configuration
config = Config('.env')  # or use `os.environ` directly if already loaded

oauth = OAuth(config)
oauth.register(
    name='google',
    client_id=config('GOOGLE_CLIENT_ID'),
    client_secret=config('GOOGLE_CLIENT_SECRET'),
    access_token_url='https://oauth2.googleapis.com/token',
    authorize_url='https://accounts.google.com/o/oauth2/v2/auth',
    api_base_url='https://www.googleapis.com/oauth2/v2/',
    client_kwargs={'scope': 'openid email profile'}
)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = request.session.get("user")
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.get('/login')
async def login(request: Request):
    redirect_uri = "https://datumsync.onrender.com/auth/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback")
async def auth(request: Request):
    try:
        # Step 1: Exchange the code for token
        token = await oauth.google.authorize_access_token(request)
        print("✅ OAuth token response:", token)

        # ✅ Step 2: Parse id_token from the full token dictionary
        user_info = await oauth.google.parse_id_token(request, token)
        print("✅ User info:", user_info)

        # Step 3: Save user in session
        request.session["user"] = dict(user_info)

        return RedirectResponse(url="/")

    except Exception as e:
        print("❌ Error during auth callback:", e)
        return RedirectResponse(url="/?error=auth_failed")


@app.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/")
