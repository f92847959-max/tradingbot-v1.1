"""Twilio WhatsApp webhook for incoming messages.

Configure in Twilio console:
  Webhook URL: https://your-domain/webhook/whatsapp
  (Use ngrok for local development: ngrok http 8000)
"""

import logging

from fastapi import APIRouter, Request, Response, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])


def _validate_twilio_request(request: Request, form: dict) -> bool:
    """Validate incoming Twilio webhook using TWILIO_AUTH_TOKEN.

    Falls die Twilio-Bibliothek nicht verfügbar ist, wird ein best-effort
    HMAC-SHA1 Vergleich mit `TWILIO_AUTH_TOKEN` versucht.
    """
    signature = request.headers.get("X-Twilio-Signature", "")
    auth_token = request.app.state.settings.twilio_auth_token if hasattr(request.app.state, "settings") else None
    if not auth_token:
        # No token configured — reject
        logger.warning("Twilio auth token not configured; rejecting webhook")
        return False

    # Try to use Twilio's RequestValidator if available
    try:
        from twilio.request_validator import RequestValidator

        validator = RequestValidator(auth_token)
        url = str(request.url)
        # form may be Starlette UploadFile objects; convert to simple dict of strings
        params = {k: v for k, v in form.items()}
        valid = validator.validate(url, params, signature)
        return valid
    except Exception:
        # Fallback: HMAC-SHA1 of body (best-effort, less secure)
        try:
            import hmac
            import hashlib
            body = "".join(f"{k}={v}&" for k, v in sorted(form.items())).encode("utf-8")
            expected = hmac.new(auth_token.encode(), body, hashlib.sha1).hexdigest()
            # Twilio uses base64 signature normally; compare hex as best-effort
            return signature.endswith(expected)
        except Exception:
            return False


@router.post("/whatsapp")
async def whatsapp_incoming(request: Request) -> Response:
    """Receive incoming WhatsApp messages from Twilio.

    Twilio sends form-encoded POST with Body, From, etc.
    We process the message and respond with TwiML.
    """
    form = await request.form()
    body = str(form.get("Body", ""))
    from_number = str(form.get("From", ""))

    logger.info("WhatsApp received from %s: %s", from_number, body)

    # Get confirmation handler from app state
    handler = getattr(request.app.state, "confirmation_handler", None)
    if handler is None:
        reply = "Bot laeuft im Auto-Modus. Keine Bestaetigung noetig."
    else:
        reply = await handler.handle_incoming_message(body)

    logger.info("WhatsApp reply: %s", reply)

    # Respond with TwiML
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Message>{reply}</Message></Response>"
    )
    return Response(content=twiml, media_type="application/xml")
