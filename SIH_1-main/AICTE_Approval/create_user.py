"""Interactive development account creator. No default passwords are embedded."""
import getpass
import sys
from app import app
from extensions import db
from models import User

with app.app_context():
    db.create_all()
    role = (sys.argv[1] if len(sys.argv) > 1 else input("Account type (institution/officer/committee/authority): ")).strip().lower()
    if role not in {"institution", "officer", "committee", "authority"}:
        raise SystemExit("Account type must be institution, officer, committee or authority.")
    email = input("Email: ").strip().lower()
    if "@" not in email:
        raise SystemExit("Please enter a valid email.")
    institution_name = None
    if role == "institution":
        institution_name = input("Institution name: ").strip()
        if not institution_name:
            raise SystemExit("Institution name is required.")
    password = getpass.getpass("Password (at least 10 characters): ")
    confirm = getpass.getpass("Confirm password: ")
    if len(password) < 10 or password != confirm:
        raise SystemExit("Passwords must match and contain at least 10 characters.")
    if User.query.filter_by(email=email).first():
        raise SystemExit("An account with this email already exists.")
    user = User(email=email, role=role, institution_name=institution_name)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    print(f"Created {role} account for {email}.")
