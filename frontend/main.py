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
    try:
        token = await oauth.google.authorize_access_token(request)
        print("OAuth token response:", token)

        id_token = token.get("id_token")
        if not id_token:
            raise ValueError("No ID token returned by Google")

        user = await oauth.google.parse_id_token(request, id_token)

        request.session["user"] = dict(user)
        return RedirectResponse(url="/")
    
    except Exception as e:
        print("❌ Error during auth callback:", str(e))
        return RedirectResponse(url="/?error=auth_failed")

    
    except Exception as e:
        print(f"❌ Error during auth callback: {e}")
        return HTMLResponse(f"Authentication failed: {e}", status_code=500)




@app.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/")
