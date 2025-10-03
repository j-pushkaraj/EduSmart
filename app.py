from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# Import DB & Models
from flask_migrate import Migrate
from models import db, User
from routes.auth import auth_bp
from routes.student import student_bp
from routes.teacher import teacher_bp

app = Flask(__name__)
app.secret_key = "dev_secret_key"  # Change for production

# Database setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///edusmart.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize DB
db.init_app(app)
migrate = Migrate(app, db)

# Login Manager
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(student_bp)
app.register_blueprint(teacher_bp)  # ✅ Teacher routes now live under /teacher/*

# Landing Page
@app.route("/")
def landing():
    return render_template("landing.html")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Create DB tables if not exist
    app.run(debug=True)

