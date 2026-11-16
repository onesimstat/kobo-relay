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
# ============================================================
# ROUTE DÉDIÉE À L'AUDIT THIMO URBAIN
# ============================================================

AUDIT_ASSET_UID = "azJQDhtaijutJnfzj5cVdF"
AUDIT_VERSION = "vJeHJ24qWjwTwhHqhxHrNj"


def create_audit_xml(data: dict) -> str:
    """Construit le XML OpenRosa pour l'audit THIMO (1 bénéficiaire par soumission)."""
    root = Element(AUDIT_ASSET_UID, {
        "xmlns:jr": "http://openrosa.org/javarosa",
        "xmlns:orx": "http://openrosa.org/xforms",
        "id": AUDIT_ASSET_UID,
        "version": AUDIT_VERSION,
    })

    formhub = SubElement(root, "formhub")
    SubElement(formhub, "uuid").text = str(uuid.uuid4())

    # Métadonnées globales
    SubElement(root, "start").text = str(data.get("start", "") or "")
    SubElement(root, "end").text = str(data.get("end", "") or "")
    SubElement(root, "today").text = str(data.get("today", "") or "")
    SubElement(root, "username").text = str(data.get("username", "") or "")
    SubElement(root, "deviceid").text = str(data.get("deviceid", "") or "")

    # MODULE 1 : Métadonnées d'inspection
    module_1 = SubElement(root, "module_1")
    for col in ["nom_agent", "date_visite", "heure_arrivee", "commune",
                "site_name", "brigade_id", "gps_site", "brigade_presente",
                "motif_absence_brigade"]:
        SubElement(module_1, col).text = str(data.get(col, "") or "")

    # MODULE 2 : Référence d'enrôlement
    module_2 = SubElement(root, "module_2")
    SubElement(module_2, "id_benef").text = str(data.get("id_benef", "") or "")

    # MODULE 3 : Statut de présence
    module_3 = SubElement(root, "module_3")
    SubElement(module_3, "statut_presence").text = str(data.get("statut_presence", "") or "")

    # MODULE 4 : Anomalies
    module_4 = SubElement(root, "module_4")
    SubElement(module_4, "codes_anomalies").text = str(data.get("codes_anomalies", "") or "")
    SubElement(module_4, "detail_anomalie").text = str(data.get("detail_anomalie", "") or "")

    # MODULE 5 : Preuves
    module_5 = SubElement(root, "module_5")
    SubElement(module_5, "face_match_result").text = str(data.get("face_match_result", "") or "")
    SubElement(module_5, "observations").text = str(data.get("observations", "") or "")

    # Meta
    meta = SubElement(root, "meta")
    SubElement(meta, "instanceID").text = f"uuid:{uuid.uuid4()}"
    SubElement(meta, "instanceName").text = (
        f"Audit-{data.get('brigade_id', '')}-{data.get('today', '')}"
    )

    return minidom.parseString(tostring(root)).toprettyxml(indent="  ")


@app.post("/submit-audit")
async def submit_audit(request: Request):
    """Route dédiée à l'audit THIMO."""
    try:
        logger.info("Réception d'une soumission d'audit THIMO")
        data = await request.json()
        if not data:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        logger.info(f"Audit reçu : brigade={data.get('brigade_id')}")

        xml_content = create_audit_xml(data)

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
            logger.info("Audit envoyé avec succès à Kobo")
            return JSONResponse({"success": True, "message": "Audit enregistré dans Kobo"})
        elif resp.status_code == 401:
            return JSONResponse(
                {"success": False, "error": "Authentification refusée par Kobo (401)"},
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