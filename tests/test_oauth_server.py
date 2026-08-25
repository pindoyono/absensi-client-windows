import base64
import hashlib
from app.device.oauth_server import _generate_pkce_pair

def test_pkce_challenge_sesuai_verifier():
    verifier, challenge = _generate_pkce_pair()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    assert challenge == expected
