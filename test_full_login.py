import requests
import json
import re

s = requests.Session()

# Get login page
r = s.get('http://localhost:5000/auth/login')
csrf_token = None
for line in r.text.split('\n'):
    if 'name="csrf_token"' in line:
        csrf_token = line.split('value="')[1].split('"')[0]
        break

print("Login CSRF Token:", csrf_token)

# POST to generate OTP
r2 = s.post('http://localhost:5000/auth/login', data={'csrf_token': csrf_token, 'email': 'naugaintushar@gmail.com'}, allow_redirects=False)
print("POST /login status:", r2.status_code)
print("POST /login headers:", r2.headers)

# Get verify page
r3 = s.get('http://localhost:5000/auth/verify')
verify_csrf = None
for line in r3.text.split('\n'):
    if 'name="csrf_token"' in line:
        verify_csrf = line.split('value="')[1].split('"')[0]
        break
print("Verify CSRF Token:", verify_csrf)

# Now we need the OTP. Let's read it from Firebase using firebase_admin locally
import firebase_admin
from firebase_admin import credentials, firestore
cred = credentials.Certificate('firebase_credentials.json')
firebase_admin.initialize_app(cred)
db = firestore.client()
doc = db.collection('otps').document('naugaintushar@gmail.com').get()
otp = doc.to_dict()['otp']
print("Fetched OTP:", otp)

# Submit OTP
r4 = s.post('http://localhost:5000/auth/verify', data={'csrf_token': verify_csrf, 'otp': otp}, allow_redirects=False)
print("POST /verify status:", r4.status_code)
print("POST /verify headers:", r4.headers)

# Now we should be logged in. Let's get the home page to get the new CSRF token
r5 = s.get('http://localhost:5000/')
home_csrf = None
for line in r5.text.split('\n'):
    if 'name="csrf_token"' in line:
        home_csrf = line.split('value="')[1].split('"')[0]
        break
print("Home CSRF Token:", home_csrf)

# Now test logout
r6 = s.post('http://localhost:5000/auth/logout', data={'csrf_token': home_csrf}, allow_redirects=False)
print("POST /logout status:", r6.status_code)
print("POST /logout headers:", r6.headers)

# Test if we are logged out
r7 = s.get('http://localhost:5000/', allow_redirects=False)
print("GET / status after logout:", r7.status_code)

