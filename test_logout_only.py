from flask import Flask, request
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

@app.route('/logout')
def logout():
    logout_user()
    return "logged out"

client = app.test_client()
r1 = client.get('/login')
print("Login Set-Cookie:", r1.headers.getlist('Set-Cookie'))
r2 = client.get('/logout')
print("Logout Set-Cookie:", r2.headers.getlist('Set-Cookie'))
