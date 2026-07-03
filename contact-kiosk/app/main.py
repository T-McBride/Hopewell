"""
Contact directory kiosk - main FastAPI application.

Run with:
    uvicorn app.main:app --host 0.0.0.0 --port 8000

See README.md for full setup, including Raspberry Pi kiosk autostart.
"""
import io
import uuid
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageOps

from app import auth, database
from app.database import get_conn, init_db, log_action, now_iso, get_setting, set_setting
from app.pdf_generator import build_directory_pdf

BASE_DIR = Path(__file__).parent
PHOTO_DIR = BASE_DIR / "data" / "photos"
PHOTO_DIR.mkdir(parents=True, exist_ok=True)

MAX_PHOTO_DIMENSION = 800  # px, longest side - keeps files small for a Pi's storage/CPU

app = FastAPI(title="Contact Directory Kiosk")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.mount("/kiosk", StaticFiles(directory=str(BASE_DIR / "static" / "kiosk"), html=True), name="kiosk")
app.mount("/admin-ui", StaticFiles(directory=str(BASE_DIR / "static" / "admin"), html=True), name="admin-ui")
app.mount("/images", StaticFiles(directory=str(BASE_DIR / "static" / "images"), html=True), name="images")


@app.on_event("startup")
def on_startup():
    init_db()
    auth.ensure_pin_file_exists()


@app.get("/")
def root():
    return RedirectResponse(url="/kiosk/")


# ---------------------------------------------------------------------------
# Public kiosk endpoints
# ---------------------------------------------------------------------------

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _save_photo(upload: UploadFile) -> str:
    if upload.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type")

    raw = upload.file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Photo too large (max 8MB)")

    image = Image.open(io.BytesIO(raw))
    image = ImageOps.exif_transpose(image)  # respect camera orientation
    image = image.convert("RGB")
    image.thumbnail((MAX_PHOTO_DIMENSION, MAX_PHOTO_DIMENSION))

    filename = f"{uuid.uuid4().hex}.jpg"
    image.save(PHOTO_DIR / filename, "JPEG", quality=85)
    return filename


@app.post("/api/contacts")
def submit_contact(
    full_name: str = Form(...),
    phone_mobile: str = Form(""),
    email: str = Form(""),
    home_address: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    zip: str = Form(""),
    consent_given: bool = Form(False),
    photo: Optional[UploadFile] = File(None),
):
    full_name = full_name.strip()
    if not full_name:
        raise HTTPException(status_code=400, detail="Name is required")
    if not consent_given:
        raise HTTPException(status_code=400, detail="Consent is required to submit an entry")

    photo_filename = _save_photo(photo) if photo is not None else None

    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO contacts
                (full_name, phone_mobile, email, home_address, city, state, zip, photo_path,
                 consent_given, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'pending', ?, ?)
            """,
            (
                full_name,
                phone_mobile.strip(),
                email.strip(),
                home_address.strip(),
                city.strip(),
                state.strip(),
                zip.strip(),
                photo_filename,
                now_iso(),
                now_iso()))
        contact_id = cursor.lastrowid
        log_action(conn, contact_id, "submitted", actor="kiosk")
        conn.commit()

    return {"id": contact_id, "status": "pending"}


@app.get("/api/directory.html", response_class=HTMLResponse)
def public_directory(request: Request):
    """Always-on browsable directory. Never includes home_address."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT full_name, phone_mobile, email, home_address, city, state, zip, photo_path
            FROM contacts
            WHERE status = 'approved'
            ORDER BY full_name COLLATE NOCASE
            """
        ).fetchall()
    contacts = [dict(r) for r in rows]
    return templates.TemplateResponse(
        "directory.html",
        {"request": request, "contacts": contacts, "include_home_address": True})


@app.get("/api/photos/{filename}")
def get_photo(filename: str):
    # Served for use in the public directory and admin UI. Only ever serves
    # files from the dedicated photo directory, never arbitrary paths.
    safe_path = (PHOTO_DIR / filename).resolve()
    if safe_path.parent != PHOTO_DIR.resolve() or not safe_path.exists():
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(safe_path)


# ---------------------------------------------------------------------------
# Admin auth
# ---------------------------------------------------------------------------

@app.post("/api/admin/login")
def admin_login(pin: str = Form(...)):
    if not auth.verify_pin(pin):
        raise HTTPException(status_code=401, detail="Incorrect PIN")
    token = auth.create_session_token()
    response = JSONResponse({"ok": True})
    response.set_cookie(
        auth.SESSION_COOKIE_NAME,
        token,
        max_age=auth.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return response


@app.post("/api/admin/logout")
def admin_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.SESSION_COOKIE_NAME)
    return response


@app.post("/api/admin/change-pin")
def admin_change_pin(new_pin: str = Form(...), _: None = Depends(auth.require_admin)):
    if len(new_pin) < 4:
        raise HTTPException(status_code=400, detail="PIN must be at least 4 digits")
    auth.set_pin(new_pin)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin contact management
# ---------------------------------------------------------------------------

@app.get("/api/admin/contacts")
def admin_list_contacts(status_filter: Optional[str] = None, _: None = Depends(auth.require_admin)):
    query = "SELECT * FROM contacts"
    params = ()
    if status_filter and status_filter != "all":
        query += " WHERE status = ?"
        params = (status_filter,)
    query += " ORDER BY created_at DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@app.patch("/api/admin/contacts/{contact_id}")
def admin_update_contact(contact_id: int, payload: dict, _: None = Depends(auth.require_admin)):
    allowed_fields = {
        "full_name", "phone_mobile", "email", "home_address", "status", "city", "state", "zip",
    }
    updates = {k: v for k, v in payload.items() if k in allowed_fields}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    if "status" in updates and updates["status"] not in {"pending", "approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Invalid status")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values())

    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Contact not found")
        conn.execute(
            f"UPDATE contacts SET {set_clause}, updated_at = ? WHERE id = ?",
            (*values, now_iso(), contact_id))
        log_action(conn, contact_id, f"updated:{','.join(updates)}", actor="admin")
        conn.commit()
    return {"ok": True}


@app.delete("/api/admin/contacts/{contact_id}")
def admin_delete_contact(contact_id: int, _: None = Depends(auth.require_admin)):
    with get_conn() as conn:
        row = conn.execute("SELECT photo_path FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Contact not found")
        conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        log_action(conn, contact_id, "deleted", actor="admin")
        conn.commit()

    if row["photo_path"]:
        photo_file = PHOTO_DIR / row["photo_path"]
        if photo_file.exists():
            photo_file.unlink()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin settings + directory generation
# ---------------------------------------------------------------------------

@app.get("/api/admin/settings")
def admin_get_settings(_: None = Depends(auth.require_admin)):
    with get_conn() as conn:
        value = get_setting(conn, "include_home_address_default", "0")
    return {"include_home_address_default": value == "1"}


@app.put("/api/admin/settings")
def admin_put_settings(payload: dict, _: None = Depends(auth.require_admin)):
    if "include_home_address_default" in payload:
        with get_conn() as conn:
            set_setting(
                conn,
                "include_home_address_default",
                "1" if payload["include_home_address_default"] else "0")
            conn.commit()
    return {"ok": True}


@app.get("/api/admin/directory.pdf")
def admin_directory_pdf(include_home_address: Optional[bool] = None, _: None = Depends(auth.require_admin)):
    with get_conn() as conn:
        default_value = get_setting(conn, "include_home_address_default", "0") == "1"
        rows = conn.execute(
            """
            SELECT full_name, phone_mobile, email, home_address, city, state, zip, photo_path
            FROM contacts WHERE status = 'approved'
            """
        ).fetchall()

    include_address = default_value if include_home_address is None else include_home_address
    contacts = [dict(r) for r in rows]
    pdf_bytes = build_directory_pdf(contacts, include_home_address=include_address)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=directory.pdf"})


@app.get("/admin/")
def admin_redirect():
    return RedirectResponse(url="/admin-ui/")
