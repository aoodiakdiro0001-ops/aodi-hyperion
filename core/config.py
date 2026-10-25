"""Aodı-Hyperion 1.0.0 — core config & state (stdlib-only, zero deps)."""
import os
from pathlib import Path

VERSION = "1.0.0"
BRAND = "Aodı-Hyperion"

HOME = Path(os.environ.get("HY_HOME", str(Path.home() / ".hyperion")))
HOME.mkdir(parents=True, exist_ok=True)
DB_FILE = HOME / "hyperion.db"
KEY_DIR = HOME / "keys"
ARTIFACTS = HOME / "artifacts"

# Services (Hyperion binds its own address space)
DEFAULT_PORT = int(os.environ.get("HY_PORT", "9412"))        # organism core API
MESH_URL = os.environ.get("HY_MESH_URL", "http://127.0.0.1:9411")  # Go gossip mesh

# Execution guardrails (bounded everywhere)
MAX_GENERATIONS = int(os.environ.get("HY_GENERATIONS", "6"))
POPULATION = int(os.environ.get("HY_POPULATION", "5"))
MUTATION_TRIES = int(os.environ.get("HY_MUTATIONS", "12"))
GEN_TIMEOUT = int(os.environ.get("HY_GEN_TIMEOUT", "300"))
SANDBOX_TIMEOUT = int(os.environ.get("HY_SANDBOX_TIMEOUT", "15"))
SANDBOX_MEM_MB = int(os.environ.get("HY_SANDBOX_MEM_MB", "384"))
TENSOR_BLOCKS_TIMEOUT = int(os.environ.get("HY_TENSOR_TIMEOUT", "20"))
MAX_WORKERS = int(os.environ.get("HY_MAX_WORKERS", "8"))

# Optional secrets / telemetry
TELEGRAM_BOT_TOKEN = os.environ.get("HY_TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("HY_TELEGRAM_CHAT", "")
TELEGRAM_RELAY = os.environ.get("HY_TELEGRAM_RELAY", "")

CONTACT = {
    "email": "baranavisat@gmail.com",
    "whatsapp": "+90 531 326 37 22",
    "whatsapp_url": "https://wa.me/905313263722",
    "github": "https://github.com/aoodiakdiro0001-ops",
    "btc": "bc1q8dhtdrndxsl70e97t8grydfe6pjue37zrhzf6c",
    "usdt": "TLWdTjqqogkXNEXGiPWsGdjFP6ioycxeWW",
}


def banner():
    return "\n".join([
        "=======================================================",
        f"  {BRAND} v{VERSION} — self-evolving neural organism",
        "  signed gossip mesh · schnorr zk attestations",
        "  genetic engine · sha256 lineage chain · zero cloud",
        "=======================================================",
    ])


def save_json(path, data):
    import json
    path = Path(path)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def load_json(path, default=None):
    import json
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default
