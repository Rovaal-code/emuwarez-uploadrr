"""Configuration encryption helpers."""
from .legacy import (
    PASSPHRASE_SYMBOLS, encrypt_config_payload, decrypt_config_payload,
    passphrase_errors, prompt_new_passphrase,
)
