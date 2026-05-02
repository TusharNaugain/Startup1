from flask import Flask, request, session
from flask_login import LoginManager, UserMixin, login_user, logout_user

app = Flask(__name__)
app.secret_key = 'test'
lm = LoginManager(app)

class User(UserMixin):
    def get_id(self): return "1"

@lm.user_loader
def load_user(id): return User()

@app.route('/login')
def login():
    login_user(User(), remember=True)
    return "logged in"

@app.route('/logout_broken')
def logout_broken():
    logout_user()
    session.clear()  # This breaks it!
    return "logged out"

@app.route('/logout_fixed')
def logout_fixed():
    logout_user()
    # Don't call session.clear(), or pop only what we need
    return "logged out"

client = app.test_client()
print("Broken Logout:")
r1 = client.get('/login')
r2 = client.get('/logout_broken', headers={'Cookie': r1.headers['Set-Cookie'].split(';')[0]})
print("Set-Cookie:", r2.headers.getlist('Set-Cookie'))

print("\nFixed Logout:")
r3 = client.get('/login')
r4 = client.get('/logout_fixed', headers={'Cookie': r3.headers['Set-Cookie'].split(';')[0]})
print("Set-Cookie:", r4.headers.getlist('Set-Cookie'))

