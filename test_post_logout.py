import requests

s = requests.Session()
# Get the login page to get a CSRF token
r = s.get('http://localhost:5000/auth/login')
csrf_token = None
for line in r.text.split('\n'):
    if 'name="csrf_token"' in line:
        # Extract token
        csrf_token = line.split('value="')[1].split('"')[0]
        break

print("Found CSRF Token:", csrf_token)

# Try to POST to logout (even if we are not logged in, we can see if it redirects or gives 400 Bad Request)
# Oh wait, @login_required is on logout. If we are not logged in, @login_required will intercept and redirect to login,
# or give a 401. Let's see what flask_login does.
r_logout = s.post('http://localhost:5000/auth/logout', data={'csrf_token': csrf_token}, allow_redirects=False)
print("POST /logout status:", r_logout.status_code)
print("POST /logout headers:", r_logout.headers)
