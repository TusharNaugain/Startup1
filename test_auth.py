import requests

s = requests.Session()
r = s.get('http://localhost:5000/auth/login')
print("GET /login status:", r.status_code)

# We can't easily login via OTP here without fetching the OTP from firestore or email.
# But we can create a test user and login directly or simulate a login by using the OTP.
