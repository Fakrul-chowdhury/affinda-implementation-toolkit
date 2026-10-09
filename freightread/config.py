"""Settings, read from environment variables (or a local, git-ignored .env file)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path=ROOT / ".env"):
    # Minimal .env reader so the project has no extra dependency for it.
    # Real environment variables always win over the file.
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

AFFINDA_API_KEY = os.environ.get("AFFINDA_API_KEY", "")
AFFINDA_WORKSPACE_ID = os.environ.get("AFFINDA_WORKSPACE_ID", "")
AFFINDA_DOCUMENT_TYPE_ID = os.environ.get("AFFINDA_DOCUMENT_TYPE_ID", "")
AFFINDA_BASE_URL = os.environ.get("AFFINDA_BASE_URL", "https://api.affinda.com/v3")

# "mock" runs fully offline from recorded/simulated responses; "live" calls Affinda and uses credits.
# Default to mock so nobody burns credits by accident.
EXTRACTOR_MODE = os.environ.get("EXTRACTOR_MODE", "mock").lower()

RULES_FILE = Path(os.environ.get("RULES_FILE", ROOT / "rules" / "wattlebird.yaml"))
