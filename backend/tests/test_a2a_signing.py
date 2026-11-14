"""Tests des Agent Cards A2A signées (spec 15b) — TDD avant le code.

Contrat : build_agent_card(signer=...) ajoute une AgentCardSignature JWS (ES256) ;
verify_agent_card valide avec la bonne clé, lève InvalidSignaturesError avec une
mauvaise clé, NoSignatureError sur card non signée ; sans signer → card inchangée.
"""

import pytest
from a2a.utils.signing import InvalidSignaturesError, NoSignatureError

from investia.agents.cards import build_agent_card, make_card_signer, verify_agent_card


def _es256_key() -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def test_card_signee_a_une_signature_verifiable():
    key = _es256_key()
    signer = make_card_signer(key, kid="test-kid", alg="ES256")
    card = build_agent_card("analyste", base_url="http://test", signer=signer)
    assert len(card.signatures) == 1
    verify_agent_card(card, key)  # ne lève rien


def test_verification_echoue_avec_mauvaise_cle():
    key = _es256_key()
    other = _es256_key()
    signer = make_card_signer(key, kid="test-kid", alg="ES256")
    card = build_agent_card("analyste", base_url="http://test", signer=signer)
    with pytest.raises(InvalidSignaturesError):
        verify_agent_card(card, other)


def test_verification_card_non_signee_leve_no_signature():
    card = build_agent_card("analyste")
    assert card.signatures == []
    with pytest.raises(NoSignatureError):
        verify_agent_card(card, _es256_key())


def test_sans_signer_la_card_est_identique():
    card = build_agent_card("risque", base_url="http://x")
    assert card.signatures == []
    assert card.name == "risque"
    assert card.supported_interfaces[0].url == "http://x/api/agents/risque/jsonrpc"
