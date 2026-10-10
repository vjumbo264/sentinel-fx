"""Canonical JSON + sha256 for pair packs."""
import hashlib, json

def canonical(obj) -> str:
    """Canonical JSON: sorted keys, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def pack_checksum(pack: dict) -> str:
    """sha256 of canonical JSON with checksum_sha256 removed."""
    body = {k: v for k, v in pack.items() if k != "checksum_sha256"}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()

def verify_checksum(pack: dict) -> bool:
    got = pack.get("checksum_sha256", "")
    return bool(got) and got == pack_checksum(pack)
