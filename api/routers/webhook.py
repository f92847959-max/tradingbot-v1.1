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
        params = {k: str(v) for k, v in form.items()}
        return bool(validator.validate(url, params, signature))
    except ImportError:
        pass
    except Exception:
        logger.exception("Twilio RequestValidator raised unexpected error")
        return False

    # Fallback: emulate Twilio's signature scheme without the SDK.
    # Twilio computes HMAC-SHA1 over (url + sorted(k+v) joined) and
    # base64-encodes the digest. We must compare base64 to base64 — never hex.
    try:
        import base64
        import hmac
        import hashlib

        url = str(request.url)
        # Sorted concatenation of "key" + "value" pairs (Twilio spec).
        sorted_items = sorted(form.items(), key=lambda kv: kv[0])
        data = url + "".join(f"{k}{str(v)}" for k, v in sorted_items)
        digest = hmac.new(
            auth_token.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        expected = base64.b64encode(digest).decode("ascii")
        return hmac.compare_digest(expected, signature or "")
    except Exception:
        logger.exception("Twilio signature fallback validation failed", exc_info=True)
        return False


@router.post("/whatsapp")
async def whatsapp_incoming(request: Request) -> Response:
    """Receive incoming WhatsApp messages from Twilio.

    Twilio sends form-encoded POST with Body, From, etc.
    We process the message and respond with TwiML.
    """
    form = await request.form()

    # Validate Twilio signature before doing anything with the payload
    if not _validate_twilio_request(request, dict(form)):
        logger.warning("Rejected Twilio webhook with invalid signature from %s",
                       request.client.host if request.client else "unknown")
        raise HTTPException(status_code=403, detail="Invalid signature")

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
