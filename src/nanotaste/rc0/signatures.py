"""OpenSSH signature verification for owner-controlled RC0 records."""

from __future__ import annotations

import subprocess
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from nanotaste.rc0.canonical import canonical_bytes
from nanotaste.rc0.contracts import validate_record


class SignatureError(ValueError):
    """Raised when a required owner signature cannot be verified."""


def signature_message(record: dict[str, Any]) -> bytes:
    """Return canonical bytes excluding the signature and outer record digest."""
    validate_record(record)
    message = deepcopy(record)
    message.pop("digest")
    payload = message.get("payload")
    if not isinstance(payload, dict) or not isinstance(payload.get("signature"), str):
        raise SignatureError("record does not carry an OpenSSH signature")
    payload.pop("signature")
    return canonical_bytes(message)


def verify_ssh_signature(
    record: dict[str, Any],
    *,
    allowed_signers_file: Path,
    identity: str,
    namespace: str,
    ssh_keygen: str = "ssh-keygen",
) -> None:
    """Verify a purpose-specific OpenSSH signature without invoking a shell."""
    signature = record.get("payload", {}).get("signature")
    if not isinstance(signature, str) or not signature.startswith("-----BEGIN SSH SIGNATURE-----"):
        raise SignatureError("record signature is not an armored OpenSSH signature")
    if not allowed_signers_file.is_file() or allowed_signers_file.is_symlink():
        raise SignatureError("allowed signers file is missing or unsafe")
    with TemporaryDirectory() as temp_dir:
        signature_path = Path(temp_dir) / "record.sig"
        signature_path.write_text(signature, encoding="utf-8")
        result = subprocess.run(
            [
                ssh_keygen,
                "-Y",
                "verify",
                "-f",
                str(allowed_signers_file),
                "-I",
                identity,
                "-n",
                namespace,
                "-s",
                str(signature_path),
            ],
            input=signature_message(record),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise SignatureError(f"OpenSSH signature verification failed: {detail}")
