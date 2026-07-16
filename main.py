import os
import uuid
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
import requests
from requests.auth import HTTPBasicAuth

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Configuration ---
KC_SERVER = "https://kc-eu.kobotoolbox.org"
USERNAME = "tiemoko_onesime"
PASSWORD = os.environ.get("KOBO_PASSWORD")
if not PASSWORD:
    raise RuntimeError("La variable d'environnement KOBO_PASSWORD n'est pas définie.")
ASSET_UID = "apZMkPrSVJNPxBVxb7eu6Q"
VERSION = "vJeHJ24qWjwTwhHqhxHrNj"

# Endpoint OpenRosa officiel utilisé par KoboCollect / ODK Collect.
# Authentification HTTP Basic directe -> pas de login web, pas de CSRF,
# pas de problème de partage de cookies entre sous-domaines.
SUBMISSION_URL = f"{KC_SERVER}/{USERNAME}/submission"


# --- Fonction XML ---
def create_kobo_xml(data: dict) -> str:
    root = Element(ASSET_UID, {
        "xmlns:jr": "http://openrosa.org/javarosa",
        "xmlns:orx": "http://openrosa.org/xforms",
        "id": ASSET_UID,
        "version": VERSION,
    })
    formhub = SubElement(root, "formhub")
    SubElement(formhub, "uuid").text = str(uuid.uuid4())
    for col, value in data.items():
        el = SubElement(root, col)
        el.text = "" if value is None else str(value)
    meta = SubElement(root, "meta")
    SubElement(meta, "instanceID").text = f"uuid:{uuid.uuid4()}"
    return minidom.parseString(tostring(root)).toprettyxml(indent="  ")


# --- Endpoint de soumission ---
@app.post("/submit")
async def submit(request: Request):
    try:
        logger.info("Réception d'une soumission")
        data = await request.json()
        if not data:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        logger.info("Génération du XML...")
        xml_content = create_kobo_xml(data)

        logger.info("Envoi direct vers l'endpoint OpenRosa (HTTP Basic Auth)...")
        files = {
            "xml_submission_file": (
                "submission.xml",
                xml_content.encode("utf-8"),
                "text/xml",
            )
        }

        resp = requests.post(
            SUBMISSION_URL,
            files=files,
            auth=HTTPBasicAuth(USERNAME, PASSWORD),
            timeout=30,
        )

        if resp.status_code in (201, 202):
            logger.info("Soumission réussie")
            return JSONResponse({"success": True, "message": "Soumission envoyée avec succès"})
        elif resp.status_code == 401:
            logger.error("Échec d'authentification (401) - vérifiez USERNAME/PASSWORD")
            return JSONResponse(
                {"success": False, "error": "Authentification refusée par Kobo (401). Vérifiez le nom d'utilisateur et le mot de passe."},
                status_code=500,
            )
        else:
            logger.error(f"Erreur Kobo: {resp.status_code} - {resp.text[:500]}")
            return JSONResponse(
                {"success": False, "error": f"Kobo error: {resp.status_code} - {resp.text[:200]}"},
                status_code=500,
            )

    except Exception as e:
        logger.error(f"Erreur: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000, timeout_keep_alive=120)