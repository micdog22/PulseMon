import os, asyncio, httpx
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select
from .models import Monitor, History

WORKER_INTERVAL = int(os.getenv("WORKER_INTERVAL_SEC", "60"))

async def start_worker(SessionLocal):
    await asyncio.sleep(1)
    while True:
        try:
            await run_once(SessionLocal)
        except Exception as e:
            print("[worker] error:", e)
        await asyncio.sleep(WORKER_INTERVAL)

async def run_once(SessionLocal):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        mons = db.scalars(select(Monitor)).all()
        for m in mons:
            prev = m.status or "UNKNOWN"
            if not m.last_ping:
                continue
            delta = (now - m.last_ping).total_seconds()
            threshold = (m.interval_seconds or 0) + (m.grace_seconds or 0)
            new = "UP" if delta <= threshold else "DOWN"
            if new != prev:
                m.status = new
                db.add(m)
                db.add(History(slug=m.slug, prev_status=prev, new_status=new, note=f"delta={int(delta)}s threshold={threshold}s"))
                db.commit()
                if m.webhook_url:
                    await notify_webhook(m, now)

async def notify_webhook(m: Monitor, now):
    payload = {"slug": m.slug, "name": m.name, "status": m.status, "occurred_at": now.isoformat(), "interval_seconds": m.interval_seconds, "grace_seconds": m.grace_seconds, "last_ping": m.last_ping.isoformat() if m.last_ping else None}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(m.webhook_url, json=payload)
        except Exception as e:
            print("[webhook] failed:", e)
