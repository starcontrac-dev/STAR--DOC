from fastapi.testclient import TestClient
import os
import random
import string

# Import app directly
import app.main as main

client = TestClient(main.app)

# Generate random username to avoid unique conflicts
username = 'testuser_' + ''.join(random.choice(string.ascii_lowercase) for _ in range(6))
user_payload = {
    'username': username,
    'email': f'{username}@example.com',
    'full_name': 'Test User',
    'password': 'TestPass123!'
}
print('Registering user:', username)
resp = client.post('/register', json=user_payload)
print('register status:', resp.status_code)
try:
    print('register json:', resp.json())
except Exception:
    print('register text:', resp.text)

# Now attempt token
resp2 = client.post('/token', data={'username': username, 'password': 'TestPass123!'})
print('token status:', resp2.status_code)
try:
    print('token json:', resp2.json())
except Exception:
    print('token text:', resp2.text)
