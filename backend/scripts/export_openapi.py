"""Print the API's OpenAPI schema; the frontend generates its types from it.

    python scripts/export_openapi.py > ../frontend/openapi.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import create_app  # noqa: E402

# Any pool object will do: building the schema never touches the database
print(json.dumps(create_app(pool=object()).openapi(), ensure_ascii=False, indent=2))
