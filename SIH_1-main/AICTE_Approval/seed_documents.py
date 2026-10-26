"""Seed clearly labelled prototype document requirements for each supported type."""
from app import app
from extensions import db
from models import DocumentRequirement

TYPES = ["New Institution", "Extension of Approval", "Increase in Intake", "New Course", "Change of Institution Name", "Closure of Course"]
BASE = [
    ("Application Form", "Completed application form for this prototype workflow", True),
    ("Institution Registration / Identity Document", "Sample requirement; confirm the actual requirement against applicable official guidance", True),
    ("Supporting Evidence", "Application-specific supporting evidence; sample requirement only", True),
]
with app.app_context():
    db.create_all()
    added = 0
    for app_type in TYPES:
        for sequence, (name, description, mandatory) in enumerate(BASE, 1):
            if DocumentRequirement.query.filter_by(application_type=app_type, document_name=name).first():
                continue
            db.session.add(DocumentRequirement(application_type=app_type, document_name=name, description=description, is_mandatory=mandatory, sequence_order=sequence))
            added += 1
    db.session.commit()
    print(f"Added {added} sample document requirements. These are placeholders, not official AICTE rules.")
