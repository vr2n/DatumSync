from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
from starlette.config import Config
import os

app = FastAPI()

# Session middleware for storing login sessions
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "your-default-secret-key"))

templates = Jinja2Templates(directory="templates")

# Google OAuth setup
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
    token = await oauth.google.authorize_access_token(request)

    # Debug log (you can also use logging instead of print in production)
    print("OAuth token response:", token)

    id_token = token.get("id_token")
    if not id_token:
        raise HTTPException(status_code=400, detail="Google OAuth response missing ID token.")

    # Safely parse the ID token
    user = await oauth.google.parse_id_token(request, {"id_token": id_token})
    request.session["user"] = dict(user)
    return RedirectResponse(url="/")

@app.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/")
