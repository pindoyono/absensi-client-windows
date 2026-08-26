"""
Device credentials management menggunakan Windows Credential Manager.
Implementasi untuk REQ-CRED-002.

Menyimpan secrets (API key, encryption keys) di Windows Credential Manager
alih-alih plaintext .env file.
"""
import logging
from typing import Optional

try:
    import keyring
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False

logger = logging.getLogger(__name__)

CREDENTIAL_SERVICE = "AbsensiKiosk"


class CredentialManager:
    """Manage device credentials securely."""
    
    @staticmethod
    def set_credential(key: str, value: str) -> bool:
        """
        Store credential di Windows Credential Manager / OS keychain.
        
        Args:
            key: Credential key (e.g., 'device_api_key', 'face_encryption_key')
            value: Credential value (secret)
        
        Returns:
            True jika berhasil, False jika gagal
        """
        if not HAS_KEYRING:
            logger.error("keyring library not available, cannot store credential")
            return False
        
        try:
            keyring.set_password(CREDENTIAL_SERVICE, key, value)
            logger.info(f"Credential stored: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to store credential {key}: {e}", exc_info=True)
            return False
    
    @staticmethod
    def get_credential(key: str) -> Optional[str]:
        """
        Retrieve credential dari Windows Credential Manager / OS keychain.
        
        Args:
            key: Credential key
        
        Returns:
            Credential value, atau None jika tidak ada / error
        """
        if not HAS_KEYRING:
            logger.debug("keyring library not available, cannot retrieve credential")
            return None
        
        try:
            value = keyring.get_password(CREDENTIAL_SERVICE, key)
            if value:
                logger.debug(f"Credential retrieved: {key}")
            else:
                logger.warning(f"Credential not found: {key}")
            return value
        except Exception as e:
            logger.error(f"Failed to retrieve credential {key}: {e}", exc_info=True)
            return None
    
    @staticmethod
    def delete_credential(key: str) -> bool:
        """
        Delete credential dari Windows Credential Manager / OS keychain.
        
        Args:
            key: Credential key
        
        Returns:
            True jika berhasil, False jika gagal
        """
        if not HAS_KEYRING:
            logger.error("keyring library not available, cannot delete credential")
            return False
        
        try:
            keyring.delete_password(CREDENTIAL_SERVICE, key)
            logger.info(f"Credential deleted: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete credential {key}: {e}", exc_info=True)
            return False
    
    @staticmethod
    def is_available() -> bool:
        """Check jika keyring/Credential Manager tersedia."""
        return HAS_KEYRING
