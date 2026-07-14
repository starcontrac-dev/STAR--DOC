import os
import io
import sys
from fastapi.testclient import TestClient
# Ensure project root is on sys.path so 'app' package can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app.main as main_app
import app.auth as auth

from app.auth import get_current_active_user
from app.models.user import User

# Override auth dependency to bypass DB reliance
main_app.app.dependency_overrides[get_current_active_user] = lambda: User(id=1, username="testuser", email="test@example.com", hashed_password="x", disabled=False)

client = TestClient(main_app.app)

# Debug: print registered routes
print("Registered routes:")
for route in main_app.app.routes:
    try:
        methods = getattr(route, 'methods', None) or getattr(route, 'methods', [])
        print(route.path, methods)
    except Exception:
        pass

from app.core.config import settings

# Ensure template exists
os.makedirs(settings.PLANTILLAS_DIR, exist_ok=True)
tpl_path = os.path.join(settings.PLANTILLAS_DIR, "test_template.md")
with open(tpl_path, "w", encoding="utf-8") as f:
    f.write("Hola {{name}}\nID={{ID}}")

# Prepare CSV content
csv_content = "ID,name\n1,Alice\n2,Bob\n"

files = {
    "template_file": ("test_template.md", open(tpl_path, "rb"), "text/markdown"),
    "data_file": ("data.csv", io.BytesIO(csv_content.encode()), "text/csv")
}

data = {
    "templateSourceType": "file",
    "dataSourceType": "file",
    "output_format": "md",
    # send_email not set to avoid gmail flow
}

resp = client.post("/generate-batch", data=data, files=files)
print("STATUS", resp.status_code)
print(resp.text)
print("OUTPUT_DIR CONTENTS:", os.listdir(settings.OUTPUT_DIR))

# Close opened file handle
files['template_file'][1].close()
