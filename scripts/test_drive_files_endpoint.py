from fastapi.testclient import TestClient
import app.main as main

# Create a fake user object similar to UserInDB with username attribute
class FakeUser:
    def __init__(self, username):
        self.username = username

# Monkeypatch get_current_active_user dependency to return FakeUser
main.get_current_active_user = lambda: FakeUser('testuser')

client = TestClient(main.app)
resp = client.get('/api/drive/files', params={'mime_type':'application/vnd.google-apps.document', 'q':''})
print('status', resp.status_code)
try:
    print('json', resp.json())
except Exception:
    print('text', resp.text)
