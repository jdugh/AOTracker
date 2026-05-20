import os
import uuid
from typing import Optional

import requests


def send_pushbullet_notification(title: str, body: str, api_key: Optional[str] = None, device_iden: Optional[str] = None, timeout: int = 15) -> bool:
    """Send a Pushbullet note notification."""
    resolved_api_key = (api_key or os.getenv("API_KEY") or "").strip()
    if not resolved_api_key:
        print("[NOTIFICATION] API_KEY absente ou vide dans .env, envoi Pushbullet ignore.")
        return False

    payload = {
        "guid": uuid.uuid4().hex,
        "type": "note",
        "title": title,
        "body": body,
    }
    resolved_device = (device_iden or os.getenv("PUSHBULLET_DEVICE_IDEN") or "").strip()
    if resolved_device:
        payload["device_iden"] = resolved_device

    try:
        response = requests.post(
            url="https://api.pushbullet.com/v2/pushes",
            headers={"Access-Token": resolved_api_key},
            data=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        return True
    except Exception as exc:
        print(f"Error on send message: {exc}")
        return False


def send_daily_summary_notification(nb_boamp: int, nb_place: int) -> bool:
    """Send daily summary notification for newly inserted AO entries."""
    total = nb_boamp + nb_place
    title = f"📢 {total} nouvel(les) AO détecté(es)"
    body = f"📢 {total} AO détecté : {nb_boamp} BOAMP & {nb_place} LAPLACE"
    print(f"[NOTIFICATION] {title}\n{body}")
    return send_pushbullet_notification(title=title, body=body)
