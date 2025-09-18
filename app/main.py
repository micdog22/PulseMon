import os, secrets, string, asyncio
from datetime import datetime, timezone
from typing import Optional
from itsdangerous import URLSafeSerializer, BadSignature
from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, delete
from dotenv import load_dotenv
from .db import Base, engine, SessionLocal
from .models import Monitor, History
from .services import start_worker

load_dotenv()
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
PUBLIC_STATUS_TITLE = os.getenv("PUBLIC_STATUS_TITLE", "Status — PulseMon")
app = FastAPI(title="PulseMon")
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
Base.metadata.create_all(bind=engine)
SECRET = os.getenv("ADMIN_SESSION_SECRET", "change-this-secret")
signer = URLSafeSerializer(SECRET, salt="pulsemon-admin")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def is_authed(request: Request) -> bool:
    cookie = request.cookies.get("pm_admin")
    if not cookie: return False
    try:
        data = signer.loads(cookie)
        return data.get("ok") is True
    except BadSignature:
        return False

def require_admin(request: Request):
    if not is_authed(request):
        raise HTTPException(status_code=401, detail="unauthorized")

def gen_token(n=24):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(start_worker(SessionLocal))

@app.get("/health")
def health():
    return {"status":"ok"}

@app.get("/", response_class=HTMLResponse)
def admin_home(request: Request, db: Session = Depends(get_db)):
    authed = is_authed(request)
    monitors = []
    if authed:
        monitors = db.scalars(select(Monitor).order_by(Monitor.created_at.desc())).all()
    return templates.TemplateResponse("admin.html", {"request": request, "authed": authed, "monitors": monitors})

@app.post("/admin/login")
def admin_login(token: str = Form(...)):
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="token inválido")
    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie("pm_admin", signer.dumps({"ok": True}), httponly=True, samesite="lax")
    return resp

@app.post("/admin/monitors")
def admin_create_monitor(request: Request, name: str = Form(...), slug: str = Form(...), interval_seconds: int = Form(...), grace_seconds: int = Form(...), webhook_url: Optional[str] = Form(None), db: Session = Depends(get_db)):
    require_admin(request)
    if db.scalar(select(Monitor).where(Monitor.slug == slug)):
        raise HTTPException(status_code=400, detail="slug já existe")
    token = gen_token(24)
    m = Monitor(name=name.strip(), slug=slug.strip(), token=token, interval_seconds=int(interval_seconds), grace_seconds=int(grace_seconds), webhook_url=webhook_url or None, status="UNKNOWN")
    db.add(m); db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.post("/admin/monitors/{slug}/delete")
def admin_delete_monitor(slug: str, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    m = db.scalar(select(Monitor).where(Monitor.slug == slug))
    if not m: raise HTTPException(status_code=404, detail="not found")
    db.execute(delete(History).where(History.slug == slug))
    db.delete(m); db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.get("/status", response_class=HTMLResponse)
def status_page(request: Request, db: Session = Depends(get_db)):
    mons = db.scalars(select(Monitor).order_by(Monitor.name.asc())).all()
    return templates.TemplateResponse("status.html", {"request": request, "monitors": mons, "title": PUBLIC_STATUS_TITLE})

@app.get("/h/{slug}/{token}")
def heartbeat(slug: str, token: str, db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    m = db.scalar(select(Monitor).where(Monitor.slug == slug))
    if not m or token != m.token:
        raise HTTPException(status_code=404, detail="not found")
    prev = m.status or "UNKNOWN"
    m.last_ping = datetime.now(timezone.utc)
    m.status = "UP"
    db.add(m); db.commit()
    if prev != "UP":
        db.add(History(slug=m.slug, prev_status=prev, new_status="UP", note="heartbeat received")); db.commit()
    return {"ok": True}
