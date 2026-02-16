import os
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger(__name__)

KEY_FILE = ".secret.key"

def get_key() -> bytes:
    """Get the encryption key from env or file, or generate a new one."""
    key = os.getenv("ENCRYPTION_KEY")
    if key:
        return key.encode() if isinstance(key, str) else key
    
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            return f.read()
            
    # Generate new key
    key = Fernet.generate_key()
    try:
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        logger.info(f"Generated new encryption key and saved to {KEY_FILE}")
    except Exception as e:
        logger.warning(f"Could not save encryption key to file: {e}. Secrets will be lost on restart unless ENCRYPTION_KEY env var is set.")
    return key

_fernet = None

def get_fernet():
    global _fernet
    if _fernet is None:
        _fernet = Fernet(get_key())
    return _fernet

def encrypt_secret(secret: str) -> str:
    """Encrypt a string secret."""
    if not secret:
        return secret
    f = get_fernet()
    return f.encrypt(secret.encode()).decode()

def decrypt_secret(encrypted_secret: str) -> str:
    """Decrypt a string secret."""
    if not encrypted_secret:
        return encrypted_secret
    f = get_fernet()
    try:
        return f.decrypt(encrypted_secret.encode()).decode()
    except Exception as e:
        logger.error(f"Failed to decrypt secret: {e}")
        return ""
