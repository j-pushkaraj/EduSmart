from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User

auth_bp = Blueprint("auth", __name__)

# ==========================
# ✅ SIGNUP
# ==========================
@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")  # Store as plain text
        role = request.form.get("role")

        # Validate required fields
        if not name or not email or not password or not role:
            flash("All fields are required.", "danger")
            return redirect(url_for("auth.signup"))

        # Check for existing user
        existing_user = User.query.filter(
            (User.email == email) | (User.name == name)
        ).first()

        if existing_user:
            flash("A user with this email or username already exists.", "danger")
            return redirect(url_for("auth.signup"))

        # Create user with plain password in password_hash field
        new_user = User(
            name=name,
            email=email,
            password_hash=password,  # <-- Using password_hash column for plain password
            role=role
        )
        db.session.add(new_user)
        db.session.commit()

        flash("Account created successfully! Please login.", "success")
        return redirect(url_for("auth.login"))

    return render_template("signup.html")


# ==========================
# ✅ LOGIN
# ==========================
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name_or_email = request.form.get("username")
        password = request.form.get("password")

        # Allow login via username OR email
        user = User.query.filter(
            (User.name == name_or_email) | (User.email == name_or_email)
        ).first()

        if not user or user.password_hash != password:  # Plain text comparison
            flash("Invalid username/email or password", "error")
            return redirect(url_for("auth.login"))

        login_user(user)

        # Redirect based on role
        if user.role == "student":
            return redirect(url_for("student.dashboard"))
        elif user.role == "teacher":
            return redirect(url_for("teacher.dashboard"))
        else:
            return redirect(url_for("landing"))

    return render_template("login.html")



# ==========================
# ✅ LOGOUT
# ==========================
@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("landing"))
