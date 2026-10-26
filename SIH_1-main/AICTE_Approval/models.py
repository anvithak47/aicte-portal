

from extensions import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="institution")
    institution_name = db.Column(db.String(200), nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institution_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)

    institution_name = db.Column(db.String(200), nullable=False)
    application_type = db.Column(db.String(100), nullable=False)
    # Optional region/state for workload reporting. Migration is handled in app.py.
    state = db.Column(db.String(80), nullable=True)

    current_stage = db.Column(db.String(100), default="Submitted")
    tracking_id = db.Column(db.String(40), unique=True, nullable=True, index=True)
    status = db.Column(db.String(50), default="Pending")

    submission_date = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    deadline = db.Column(db.DateTime, nullable=True)
    assigned_officer = db.Column(db.String(150), nullable=True)
    remarks = db.Column(db.Text, nullable=True)


class WorkflowStage(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    application_id = db.Column(
        db.Integer,
        db.ForeignKey("application.id"),
        nullable=False
    )

    stage_name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), default="Pending")
    assigned_to = db.Column(db.String(150), nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    remarks = db.Column(db.Text, nullable=True)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    application_id = db.Column(
        db.Integer,
        db.ForeignKey("application.id"),
        nullable=False
    )

    action = db.Column(db.String(200), nullable=False)
    performed_by = db.Column(db.String(150), nullable=True)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )


# Documents required for each application process
class DocumentRequirement(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    application_type = db.Column(db.String(100), nullable=False)
    document_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_mandatory = db.Column(db.Boolean, default=True)
    sequence_order = db.Column(db.Integer, nullable=False, default=1)


# Documents uploaded for an individual application
class UploadedDocument(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    application_id = db.Column(
        db.Integer,
        db.ForeignKey("application.id"),
        nullable=False
    )

    requirement_id = db.Column(
        db.Integer,
        db.ForeignKey("document_requirement.id"),
        nullable=False
    )

    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    sha256 = db.Column(db.String(64), nullable=True, index=True)
    extracted_text = db.Column(db.Text, nullable=True)
    upload_status = db.Column(db.String(50), default="Uploaded")
    uploaded_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )
    verified_by = db.Column(db.String(150), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    issue_date = db.Column(db.Date, nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)
    proposed_issue_date = db.Column(db.Date, nullable=True)
    proposed_expiry_date = db.Column(db.Date, nullable=True)
    renewal_status = db.Column(
        db.String(50),
        nullable=False,
        default="Not Required"
    )
    renewed_document_id = db.Column(
        db.Integer,
        db.ForeignKey("uploaded_document.id"),
        nullable=True
    )

class EVCRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(
        db.Integer,
        db.ForeignKey("application.id"),
        nullable=False
    )
    committee_name = db.Column(db.String(200), nullable=True)
    scheduled_date = db.Column(db.DateTime, nullable=True)
    completed_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50), nullable=False, default="Pending")
    assigned_officer = db.Column(db.String(150), nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

class Undertaking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(
        db.Integer,
        db.ForeignKey("application.id"),
        nullable=False
    )
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(50), nullable=False, default="Pending")
    evidence_file = db.Column(db.String(500), nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    verified_by = db.Column(db.String(150), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )


class DocumentIntegrityReview(db.Model):
    """Human-review queue item; automated flags are advisory, never a rejection."""
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("application.id"), nullable=False, index=True)
    document_id = db.Column(db.Integer, db.ForeignKey("uploaded_document.id"), nullable=False, index=True)
    matching_document_id = db.Column(db.Integer, db.ForeignKey("uploaded_document.id"), nullable=True)
    flag_category = db.Column(db.String(80), nullable=False, default="Exact Duplicate")
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(80), nullable=False, default="Flagged — Pending Review")
    officer_remarks = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    assigned_officer = db.Column(db.String(255), nullable=True)


class PersistentAlert(db.Model):
    """Persistent alert centre with acknowledgement, closure and auditability."""
    id = db.Column(db.Integer, primary_key=True)
    alert_key = db.Column(db.String(255), unique=True, nullable=False, index=True)
    application_id = db.Column(db.Integer, db.ForeignKey("application.id"), nullable=True, index=True)
    alert_type = db.Column(db.String(80), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text, nullable=True)
    due_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="Open")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    acknowledged_by = db.Column(db.String(255), nullable=True)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    closed_by = db.Column(db.String(255), nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)
    last_emailed_at = db.Column(db.DateTime, nullable=True)
    escalation_level = db.Column(db.Integer, nullable=False, default=0)
    escalated_to = db.Column(db.String(1000), nullable=True)


class CaseCommunication(db.Model):
    """Persisted, standardized in-application communications."""
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("application.id"), nullable=False, index=True)
    sender_email = db.Column(db.String(255), nullable=False)
    recipient_email = db.Column(db.String(255), nullable=True)
    template_key = db.Column(db.String(80), nullable=False, default="general")
    subject = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    delivery_status = db.Column(db.String(80), nullable=False, default="In-app only")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class RegulatoryRule(db.Model):
    """Editable demonstration rules; they are not authoritative AICTE policy."""
    id = db.Column(db.Integer, primary_key=True)
    rule_key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    label = db.Column(db.String(255), nullable=False)
    value = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text, nullable=True)
    updated_by = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
