from fastapi.testclient import TestClient
import app.main as main

# Fake async authenticate_user that returns a simple user-like object
async def fake_auth(username, password):
    class User:
        def __init__(self, username):
            self.username = username

    return User(username)

# Monkeypatch the authenticate_user used by the app
main.authenticate_user = fake_auth

client = TestClient(main.app)
resp = client.post("/token", data={"username": "test", "password": "x"})
print("status_code:", resp.status_code)
try:
    print("json:", resp.json())
except Exception:
    print("text:", resp.text)
