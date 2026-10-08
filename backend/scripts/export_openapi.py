"""Print the API's OpenAPI schema; the frontend generates its types from it.

python scripts/export_openapi.py > ../frontend/openapi.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import create_app

# Building the schema never touches the database: the app connects only on startup
print(json.dumps(create_app().openapi(), ensure_ascii=False, indent=2))
