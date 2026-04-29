"""Tests for Twilio webhook response helpers."""

from api.routers.webhook import _build_twiml_message


def test_build_twiml_message_escapes_xml_special_characters():
    twiml = _build_twiml_message('Use <CONFIRM> & "check" it')

    assert "<CONFIRM>" not in twiml
    assert "&lt;CONFIRM&gt;" in twiml
    assert "&amp;" in twiml
    assert "&quot;check&quot;" in twiml
