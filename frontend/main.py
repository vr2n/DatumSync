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
config = Config(environ=os.environ)
oauth = OAuth(config)
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = request.session.get("user")
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.get("/login")
async def login(request: Request):
    redirect_uri = request.url_for("auth")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/callback")
async def auth(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        print("✅ OAuth token response:", token)

        # Correct: pass the whole token dictionary to parse_id_token
        user = await oauth.google.parse_id_token(request, token)

        # Optional: print user info for debugging
        print("✅ Google user info:", user)

        # Store user in session
        request.session["user"] = dict(user)

        return RedirectResponse(url="/")

    except Exception as e:
        print("❌ Error during auth callback:", str(e))
        return RedirectResponse(url="/?error=auth_failed")


@app.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/")
