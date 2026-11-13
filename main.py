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
    SubElement(root, "start").text = data.get("start", "")
    SubElement(root, "end").text = data.get("end", "")
    SubElement(root, "today").text = data.get("today", "")
    SubElement(root, "username").text = data.get("username", "")
    SubElement(root, "deviceid").text = data.get("deviceid", "")

    # MODULE 1 : Métadonnées d'inspection
    module_1 = SubElement(root, "module_1")
    for col in ["nom_agent", "date_visite", "heure_arrivee", "commune",
                "site_name", "brigade_id", "gps_site", "brigade_presente",
                "motif_absence_brigade"]:
        SubElement(module_1, col).text = str(data.get(col, "") or "")

    # MODULE 2 : Référence d'enrôlement (les champs calculés sont ignorés)
    module_2 = SubElement(root, "module_2")
    SubElement(module_2, "id_benef").text = str(data.get("id_benef", "") or "")
    # Les autres champs (nom_b, prenoms_b, etc.) sont calculés par Kobo, pas besoin de les envoyer

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
    # Les photos (photo_preuve, signature_enqueteur) seront gérées plus tard (base64)

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
