from flask import request, session, g, send_file
from flask import Flask
from flask_cors import CORS
from functools import wraps
from extensions import db
import os
import secrets
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)
except ImportError:
    # The app still runs without .env loading; install requirements.txt for normal setup.
    pass

app = Flask(__name__)

frontend_url = os.environ.get(
    "FRONTEND_URL", "http://localhost:5173"
).rstrip("/")

CORS(
    app,
    supports_credentials=True,
    resources={
        r"/api/*": {
            "origins": [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                frontend_url,
            ]
        }
    },
)


configured_secret = os.environ.get("SECRET_KEY", "").strip()
if not configured_secret or configured_secret.lower().startswith("replace-with-"):
    secret_file = os.path.join(INSTANCE_DIR, ".secret_key")
    try:
        with open(secret_file, "r", encoding="utf-8") as handle:
            configured_secret = handle.read().strip()
    except OSError:
        configured_secret = secrets.token_urlsafe(48)
        try:
            with open(secret_file, "w", encoding="utf-8") as handle:
                handle.write(configured_secret)
            try:
                os.chmod(secret_file, 0o600)
            except OSError:
                pass
        except OSError:
            # In-memory fallback is safe for a single run but will invalidate sessions on restart.
            pass
    if configured_secret:
        app.logger.warning("SECRET_KEY was not configured; using a generated local development key. Set SECRET_KEY in .env for stable sessions.")
app.config["SECRET_KEY"] = configured_secret or secrets.token_urlsafe(48)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "0") == "1"
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 8
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///aicte.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_CONTENT_LENGTH", "20971520"))  # Default 20 MB request limit

db.init_app(app)

OFFICER_ONLY_PREFIXES = (
    "/api/integrity-reviews", "/api/reports", "/api/dashboard",
    "/api/evc/", "/api/undertakings/overdue",
    "/api/documents/expiry-alerts", "/api/documents/expired",
    "/api/regulatory-rules"
)
OFFICER_ONLY_SUFFIXES = ("/stage", "/complete-stage", "/assign", "/remarks", "/decision", "/verify", "/ai-validation", "/renew/verify", "/validity")

@app.before_request
def enforce_api_authentication():
    """Require server-side sessions for API routes and enforce role boundaries."""
    if request.method == "OPTIONS" or not request.path.startswith("/api/") or request.path.startswith("/api/auth/"):
        return None
    from models import User, Application
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id else None
    if not user or not user.active:
        session.clear()
        return {"error": "Authentication required. Please sign in."}, 401
    g.current_user = user
    if user.role == "institution":
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.path in ("/api/applications",):
            if request.method != "POST":
                return {"error": "This action is not permitted for institutions."}, 403
        if request.path.startswith(OFFICER_ONLY_PREFIXES) or any(request.path.endswith(x) for x in OFFICER_ONLY_SUFFIXES):
            return {"error": "Officer role required."}, 403
        if request.method == "POST" and request.path != "/api/applications" and not request.path.endswith("/documents") and not request.path.endswith("/submit") and not request.path.endswith("/undertakings") and "/undertakings/" not in request.path and not request.path.endswith("/renew-upload") and not request.path.endswith("/communications") and not request.path.endswith("/replace"):
            return {"error": "This action is reserved for an AICTE officer."}, 403
        if request.method in ("PUT", "PATCH", "DELETE"):
            allowed_institution_mutations = ("/documents/", "/undertakings/")
            if not any(part in request.path for part in allowed_institution_mutations):
                return {"error": "This action is reserved for an AICTE officer."}, 403
            if request.path.endswith("/verify") or request.path.endswith("/remarks") or request.path.endswith("/edit"):
                return {"error": "This action is reserved for an AICTE officer."}, 403
        # Any route carrying an application ID is restricted to its owning institution.
        app_id = (request.view_args or {}).get("application_id")
        if app_id is not None:
            application = db.session.get(Application, app_id)
            if application and application.institution_user_id != user.id:
                return {"error": "Application not found."}, 404
            if not application:
                return {"error": "Application not found."}, 404
    elif user.role == "officer":
        if request.path == "/api/applications" and request.method == "POST":
            return {"error": "Officers cannot submit institution applications."}, 403
    elif user.role in {"committee", "authority"}:
        # Committee accounts see only applications explicitly assigned to them through an EVC record.
        # Authority accounts see decision-pending and already-decided cases; application ownership is checked below.
        if request.path.startswith(("/api/integrity-reviews", "/api/regulatory-rules", "/api/alerts/email-digest")):
            return {"error": "Officer role required for this action."}, 403
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if user.role == "committee" and request.method == "PUT" and "/evc/" in request.path:
                pass
            elif user.role == "authority" and request.method == "PUT" and request.path.endswith("/decision"):
                pass
            elif user.role == "authority" and request.method == "PUT" and request.path.startswith("/api/alerts/records/"):
                pass
            else:
                return {"error": "This action is not permitted for this role."}, 403
        application_id = (request.view_args or {}).get("application_id")
        # Global endpoints are allow-listed by role. Per-application endpoints are
        # checked below against EVC assignments or the authority decision queue.
        if application_id is None:
            if user.role == "committee":
                allowed_global = {"/api/applications", "/api/evc/overdue", "/api/alerts/records"}
                if request.path not in allowed_global and not (request.path.startswith("/api/alerts/records/") and request.method == "PUT"):
                    return {"error": "This global view is not available to committee accounts."}, 403
            elif user.role == "authority":
                # Authority users see only decision-queue cases and alerts explicitly escalated to them.
                # Broad institution-wide expiry/compliance endpoints remain officer-only to prevent leakage.
                allowed_global = {"/api/applications", "/api/dashboard", "/api/reports/summary", "/api/alerts/records"}
                if request.path not in allowed_global and not (request.path.startswith("/api/alerts/records/") and request.method == "PUT"):
                    return {"error": "This global view is not available to authority accounts."}, 403
        if application_id is not None:
            application = db.session.get(Application, application_id)
            if not application:
                return {"error": "Application not found."}, 404
            if user.role == "committee":
                from models import EVCRecord
                assigned = EVCRecord.query.filter_by(application_id=application_id, assigned_officer=user.email).first()
                if not assigned:
                    return {"error": "This application is not assigned to your committee account."}, 404
            elif user.role == "authority" and application.current_stage not in {"Decision Pending", "Approved", "Rejected"}:
                return {"error": "This application is not in the authority decision queue."}, 404
    else:
        return {"error": "Invalid account role."}, 403
    return None

@app.route("/api/auth/session", methods=["GET"])
def auth_session():
    from models import User
    user = db.session.get(User, session.get("user_id")) if session.get("user_id") else None
    if not user or not user.active:
        session.clear()
        return {"authenticated": False}, 200
    return {"authenticated": True, "user": {"id": user.id, "email": user.email, "role": user.role, "institution_name": user.institution_name}}, 200

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    from models import User
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    if not email or not password:
        return {"error": "Email and password are required."}, 400
    user = User.query.filter_by(email=email).first()
    if not user or not user.active or not user.check_password(password):
        return {"error": "Invalid email or password."}, 401
    requested_role = data.get("role")
    if requested_role and requested_role != user.role:
        return {"error": "This account is not authorized for the selected role."}, 403
    session.clear()
    session["user_id"] = user.id
    session.permanent = True
    return {"message": "Signed in successfully", "user": {"id": user.id, "email": user.email, "role": user.role, "institution_name": user.institution_name}}, 200

@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    from models import User
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    institution_name = str(data.get("institution_name", "")).strip()
    if len(email) > 255 or "@" not in email or "." not in email.split("@")[-1]:
        return {"error": "Enter a valid email address."}, 400
    if len(password) < 10:
        return {"error": "Password must contain at least 10 characters."}, 400
    if not institution_name or len(institution_name) > 200:
        return {"error": "Institution name is required (maximum 200 characters)."}, 400
    if User.query.filter_by(email=email).first():
        return {"error": "An account with this email already exists."}, 409
    user = User(email=email, role="institution", institution_name=institution_name)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    session.clear(); session["user_id"] = user.id; session.permanent = True
    return {"message": "Institution account created", "user": {"id": user.id, "email": user.email, "role": user.role, "institution_name": user.institution_name}}, 201

@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return {"message": "Signed out successfully"}, 200


@app.route("/")
def home():
    return "AICTE Approval Workflow Backend is Running!"
@app.route("/test-post", methods=["GET", "POST"])
def test_post():
    return {"message": "POST works!"}


@app.route("/api/applications", methods=["GET"])
def get_applications():
    from models import Application

    query = Application.query
    if getattr(g, "current_user", None):
        if g.current_user.role == "institution":
            query = query.filter_by(institution_user_id=g.current_user.id)
        elif g.current_user.role == "committee":
            from models import EVCRecord
            assigned_ids = db.session.query(EVCRecord.application_id).filter_by(assigned_officer=g.current_user.email)
            query = query.filter(Application.id.in_(assigned_ids))
        elif g.current_user.role == "authority":
            query = query.filter(Application.current_stage.in_(["Decision Pending", "Approved", "Rejected"]))
    applications = query.order_by(Application.id.desc()).all()

    return {
        "applications": [
            {
                "id": app.id,
                "tracking_id": app.tracking_id,
                "institution_name": app.institution_name,
                "application_type": app.application_type,
                "state": getattr(app, "state", None),
                "contact_email": (db.session.get(__import__("models").User, app.institution_user_id).email if app.institution_user_id and db.session.get(__import__("models").User, app.institution_user_id) else None),
                "current_stage": app.current_stage,
                "status": app.status,
                "submission_date": (
                    app.submission_date.isoformat()
                    if app.submission_date else None
                ),
                "deadline": (
                    app.deadline.isoformat()
                    if app.deadline else None
                ),
                "assigned_officer": app.assigned_officer,
                "remarks": app.remarks,
            }
            for app in applications
        ]
    }





@app.route("/api/applications/<int:application_id>/stage", methods=["PUT"])
def update_application_stage(application_id):
    from models import Application

    data = request.get_json(silent=True) or {}
    application = db.session.get(Application, application_id)

    if not application:
        return {"error": "Application not found"}, 404

    new_stage = data.get("current_stage")
    reason = str(data.get("reason", "")).strip()
    if not new_stage:
        return {"error": "current_stage is required"}, 400
    if not reason:
        return {"error": "reason is required for a workflow stage change"}, 400
    transitions = {
        "Submitted": {"Initial Scrutiny", "Scrutiny", "Deficiency Raised"},
        "Initial Scrutiny": {"Document Verification", "Deficiency Raised", "Scrutiny"},
        "Document Verification": {"Deficiency Raised", "Technical Review"},
        "Deficiency Raised": set(),
        "Resubmitted": {"Document Verification", "Technical Review", "Deficiency Raised"},
        "Technical Review": {"Committee Review", "Decision Pending", "Deficiency Raised"},
        "Committee Review": {"Decision Pending", "Deficiency Raised"},
        "Scrutiny": {"EVC", "Decision Pending", "Deficiency Raised"},
        "EVC": {"SAC/SHC", "Decision Pending", "Deficiency Raised"},
        "SAC/SHC": {"Decision Pending", "Deficiency Raised"},
        "Decision Pending": {"Deficiency Raised"},
        "Draft": {"Submitted"},
    }
    if new_stage in {"Approved", "Rejected", "Decision Issued"}:
        return {"error": "Final decisions must be recorded through the authorized decision endpoint."}, 403
    if new_stage == "Technical Review":
        from models import DocumentRequirement, UploadedDocument, DocumentIntegrityReview
        requirements = DocumentRequirement.query.filter_by(application_type=application.application_type, is_mandatory=True).all()
        documents = UploadedDocument.query.filter_by(application_id=application.id).order_by(UploadedDocument.id.asc()).all()
        latest = {d.requirement_id: d for d in documents}
        missing = [r.document_name for r in requirements if r.id not in latest]
        unverified = [latest[r.id].file_name for r in requirements if r.id in latest and latest[r.id].upload_status != "Verified"]
        open_flags = DocumentIntegrityReview.query.filter_by(application_id=application.id).filter(DocumentIntegrityReview.status.in_(["Flagged — Pending Review", "Under Investigation", "Clarification Requested", "Referred for Further Verification"])).count()
        if missing or unverified or open_flags:
            return {"error": "Technical Review cannot start until required documents are verified and active integrity flags are resolved.", "missing_documents": missing, "unverified_documents": unverified, "open_integrity_flags": open_flags}, 409
    if application.current_stage == "EVC" and new_stage == "SAC/SHC":
        from models import EVCRecord
        completed = EVCRecord.query.filter_by(application_id=application.id, status="Completed").first()
        if not completed:
            return {"error": "EVC must be marked Completed before advancing to SAC/SHC."}, 409
    if application.current_stage == "Draft":
        transitions["Draft"] = set()
    if new_stage not in transitions.get(application.current_stage, set()):
        return {"error": "Invalid workflow transition.", "current_stage": application.current_stage, "requested_stage": new_stage}, 409
    previous_stage = application.current_stage
    application.current_stage = new_stage
    application.status = {"Deficiency Raised": "Deficient", "Resubmitted": "Resubmitted", "Decision Pending": "Pending Decision", "Draft": "Draft", "Submitted": "Pending"}.get(new_stage, "In Progress")
    from models import AuditLog
    db.session.add(AuditLog(application_id=application.id, action="Workflow stage changed", performed_by=g.current_user.email, details=f"Reason: {reason}. Changes: {previous_stage} -> {new_stage}"))

    db.session.commit()

    return {
        "message": "Application stage updated",
        "application_id": application.id,
        "current_stage": application.current_stage,
        "status": application.status
    }, 200


@app.route(
    "/api/applications/<int:application_id>/complete-stage",
    methods=["PUT"]
)
def complete_application_stage(application_id):
    from models import (
        Application,
        WorkflowStage,
        AuditLog,
        UploadedDocument,
        DocumentRequirement,
        EVCRecord
    )
    from datetime import datetime

    application = db.session.get(Application, application_id)

    if not application:
        return {"error": "Application not found"}, 404

    data = request.get_json(silent=True) or {}

    workflows = {
        "Only Scrutiny": ["Scrutiny"],
        "Scrutiny + EVC": ["Scrutiny", "EVC"],
        "EVC + SAC/SHC": ["EVC", "SAC/SHC"],
        "Only EVC": ["EVC"],
        "Scrutiny + EVC + SAC/SHC": [
            "Scrutiny", "EVC", "SAC/SHC"
        ]
    }

    workflow_name = data.get("workflow", "Scrutiny + EVC")
    stages = workflows.get(workflow_name)

    if not stages:
        return {"error": "Invalid workflow"}, 400
    current_stage = application.current_stage
    if current_stage == "Submitted":
        application.current_stage = stages[0]
        application.status = "In Progress"

        db.session.add(AuditLog(
            application_id=application.id,
            action="Workflow started",
            performed_by=g.current_user.email,
            details=(
                f"Application moved from Submitted to {stages[0]}. "
                f"Workflow: {workflow_name}"
            )
        ))

        db.session.commit()

        return {
            "message": "Workflow started",
            "previous_stage": "Submitted",
            "current_stage": application.current_stage,
            "status": application.status
        }, 200
    if current_stage not in stages:
        return {
            "error": "Current stage is not in this workflow",
            "current_stage": current_stage,
            "workflow": workflow_name
        }, 400

    # Check required documents before completing Scrutiny.
    
    # Check required documents before completing Scrutiny.
    if current_stage == "Scrutiny":
        from datetime import date
    
        requirements = DocumentRequirement.query.filter_by(
            application_type=application.application_type
        ).all()
    
        documents = UploadedDocument.query.filter_by(
            application_id=application.id
        ).all()
    
        documents_by_requirement = {
            document.requirement_id: document
            for document in documents
        }
    
        missing_documents = []
        unverified_documents = []
        expired_documents = []
    
        for requirement in requirements:
            if not requirement.is_mandatory:
                continue
    
            document = documents_by_requirement.get(requirement.id)
    
            if document is None:
                missing_documents.append(requirement.document_name)
                continue
    
            if document.upload_status != "Verified":
                unverified_documents.append({
                    "document_name": requirement.document_name,
                    "status": document.upload_status
                })
                continue
    
            if document.expiry_date is not None and document.expiry_date < date.today():
                expired_documents.append({
                    "document_name": requirement.document_name,
                    "expiry_date": document.expiry_date.isoformat()
                })
    
        if missing_documents or unverified_documents or expired_documents:
            return {
                "error": "Resolve mandatory document issues before completing Scrutiny",
                "missing_documents": missing_documents,
                "unverified_documents": unverified_documents,
                "expired_documents": expired_documents
            }, 400
    # Check that EVC is completed before advancing from EVC.
    if current_stage == "EVC":
        completed_evc = EVCRecord.query.filter_by(
            application_id=application.id,
            status="Completed"
        ).first()

        if not completed_evc:
            return {
                "error": "EVC must be completed before advancing"
            }, 400

    index = stages.index(current_stage)
    now = datetime.utcnow()

    if index == len(stages) - 1:
        application.current_stage = "Decision Pending"
        application.status = "Pending Decision"
    else:
        application.current_stage = stages[index + 1]
        application.status = "In Progress"

    db.session.add(WorkflowStage(
        application_id=application.id,
        stage_name=current_stage,
        status="Completed",
        started_at=now,
        completed_at=now,
        remarks=f"{current_stage} completed"
    ))

    db.session.add(AuditLog(
        application_id=application.id,
        action="Stage completed",
        performed_by=g.current_user.email,
        details=(
            f"{current_stage} completed. "
            f"Workflow: {workflow_name}"
        )
    ))

    db.session.commit()

    return {
        "message": "Workflow advanced",
        "completed_stage": current_stage,
        "current_stage": application.current_stage,
        "status": application.status
    }, 200

@app.route("/api/applications/<int:application_id>/history", methods=["GET"])
def get_application_history(application_id):
    from models import Application, WorkflowStage, AuditLog

    application = db.session.get(Application, application_id)

    if not application:
        return {"error": "Application not found"}, 404

    history = []

    # 1. Workflow stage history
    stages = WorkflowStage.query.filter_by(
        application_id=application_id
    ).all()

    for stage in stages:
        history.append({
            "source": "workflow",
            "action": "Workflow stage update",
            "stage_name": stage.stage_name,
            "status": stage.status,
            "performed_by": None,
            "timestamp": (
                stage.completed_at.isoformat()
                if stage.completed_at
                else (
                    stage.started_at.isoformat()
                    if stage.started_at else None
                )
            ),
            "started_at": (
                stage.started_at.isoformat()
                if stage.started_at else None
            ),
            "completed_at": (
                stage.completed_at.isoformat()
                if stage.completed_at else None
            ),
            "remarks": stage.remarks,
            "reason": None
        })

    # 2. Audit log history
    logs = AuditLog.query.filter_by(
        application_id=application_id
    ).all()

    for log in logs:
        history.append({
            "source": "audit_log",
            "action": getattr(log, "action", None),
            "performed_by": getattr(log, "performed_by", None),
            "timestamp": (
                log.timestamp.isoformat()
                if log.timestamp else None
            ),
            "details": getattr(log, "details", None),
            "reason": (
                log.details.split("Reason: ", 1)[1].split(". Changes:", 1)[0]
                if log.details and "Reason: " in log.details
                else None
            ),
            "remarks": getattr(log, "remarks", None)
        })

    # 3. Sort chronologically; records without timestamps go last
    history.sort(
        key=lambda item: item.get("timestamp") or ""
    )

    return {
        "application_id": application_id,
        "total_events": len(history),
        "history": history
    }, 200


@app.route("/api/alerts/deadlines", methods=["GET"])
def get_deadline_alerts():
    from models import Application
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    upcoming_limit = now + timedelta(days=7)

    query = Application.query.filter(
        Application.deadline.isnot(None),
        Application.status.notin_(["Approved", "Rejected"]),
        Application.current_stage != "Completed"
    )
    if getattr(g, "current_user", None) and g.current_user.role == "institution":
        query = query.filter_by(institution_user_id=g.current_user.id)
    applications = query.all()

    alerts = []

    for application in applications:
        deadline = application.deadline

        if deadline < now:
            alert_type = "Overdue"
            days_overdue = max(1, (now - deadline).days)

            if days_overdue >= 7:
                escalation_level = "Level 2"
            elif days_overdue >= 3:
                escalation_level = "Level 1"
            else:
                escalation_level = "Normal"

            days_remaining = None

        elif deadline <= upcoming_limit:
            alert_type = "Upcoming"
            escalation_level = "Normal"
            days_remaining = max(0, (deadline - now).days)
            days_overdue = 0

        else:
            continue

        alerts.append({
            # Existing fields preserved
            "application_id": application.id,
            "institution_name": application.institution_name,
            "deadline": deadline.isoformat(),
            "alert_type": alert_type,
            "current_stage": application.current_stage,

            # New fields
            "assigned_officer": application.assigned_officer,
            "days_remaining": days_remaining,
            "days_overdue": days_overdue,
            "escalation_level": escalation_level
        })

    alerts.sort(
        key=lambda alert: (
            0 if alert["alert_type"] == "Overdue" else 1,
            alert["deadline"]
        )
    )

    return {
        "total_alerts": len(alerts),
        "overdue_count": sum(
            1 for alert in alerts
            if alert["alert_type"] == "Overdue"
        ),
        "upcoming_count": sum(
            1 for alert in alerts
            if alert["alert_type"] == "Upcoming"
        ),
        "alerts": alerts
    }, 200

@app.route("/api/dashboard", methods=["GET"])
def get_dashboard():
    from datetime import datetime, date
    from models import (
        Application,
        UploadedDocument,
        EVCRecord,
        Undertaking
    )

    now = datetime.utcnow()
    today = date.today()

    # 1. Application statistics, scoped to the authenticated role.
    app_query = Application.query
    if g.current_user.role == "institution":
        app_query = app_query.filter_by(institution_user_id=g.current_user.id)
    elif g.current_user.role == "committee":
        from models import EVCRecord
        assigned_ids = db.session.query(EVCRecord.application_id).filter_by(assigned_officer=g.current_user.email)
        app_query = app_query.filter(Application.id.in_(assigned_ids))
    elif g.current_user.role == "authority":
        app_query = app_query.filter(Application.current_stage.in_(["Decision Pending", "Approved", "Rejected"]))
    applications = app_query.all()
    visible_ids = [a.id for a in applications]

    total = len(applications)
    pending = sum(1 for a in applications if a.status == "Pending")
    in_progress = sum(
        1 for a in applications if a.status == "In Progress"
    )
    approved = sum(1 for a in applications if a.status == "Approved")
    rejected = sum(1 for a in applications if a.status == "Rejected")

    overdue = sum(
        1 for a in applications
        if a.deadline is not None
        and a.deadline < now
        and a.status not in ["Approved", "Rejected"]
        and a.current_stage != "Completed"
    )

    # 2. Document expiry and renewal statistics
    documents = UploadedDocument.query.filter(UploadedDocument.application_id.in_(visible_ids)).all() if visible_ids else []

    expired_documents = sum(
        1 for d in documents
        if d.expiry_date is not None
        and d.expiry_date < today
    )

    from models import RegulatoryRule
    expiry_rule = RegulatoryRule.query.filter_by(rule_key="expiry_warning_days").first()
    try:
        expiry_days = max(1, min(365, int(expiry_rule.value))) if expiry_rule else 30
    except (ValueError, TypeError):
        expiry_days = 30
    expiring_soon = sum(1 for d in documents if d.expiry_date is not None and today <= d.expiry_date <= date.fromordinal(today.toordinal() + expiry_days))

    renewals_pending_verification = sum(
        1 for d in documents
        if d.renewal_status == "Submitted"
    )

    renewals_verified = sum(
        1 for d in documents
        if d.renewal_status == "Verified"
    )

    # 3. EVC statistics
    evc_records = EVCRecord.query.filter(EVCRecord.application_id.in_(visible_ids)).all() if visible_ids else []

    evc_total = len(evc_records)

    evc_pending = sum(
        1 for e in evc_records
        if e.status == "Pending"
    )

    evc_completed = sum(
        1 for e in evc_records
        if e.status == "Completed"
    )

    evc_overdue = sum(
        1 for e in evc_records
        if e.scheduled_date is not None
        and e.scheduled_date < now
        and e.status not in ["Completed", "Cancelled"]
    )

    # 4. Undertaking compliance statistics
    undertakings = Undertaking.query.filter(Undertaking.application_id.in_(visible_ids)).all() if visible_ids else []

    undertaking_total = len(undertakings)

    undertakings_pending = sum(
        1 for u in undertakings
        if u.status == "Pending"
    )

    undertakings_verified = sum(
        1 for u in undertakings
        if u.status == "Verified"
    )

    undertakings_overdue = sum(
        1 for u in undertakings
        if u.due_date is not None
        and u.due_date < now
        and u.status != "Verified"
    )

    return {
        # Existing fields — preserved for frontend compatibility
        "total_applications": total,
        "pending": pending,
        "in_progress": in_progress,
        "approved": approved,
        "rejected": rejected,
        "overdue": overdue,

        # New document metrics
        "total_documents": len(documents),
        "expired_documents": expired_documents,
        "documents_expiring_soon": expiring_soon,
        "renewals_pending_verification": renewals_pending_verification,
        "renewals_verified": renewals_verified,

        # New EVC metrics
        "total_evc_records": evc_total,
        "evc_pending": evc_pending,
        "evc_completed": evc_completed,
        "evc_overdue": evc_overdue,

        # New undertaking metrics
        "total_undertakings": undertaking_total,
        "undertakings_pending": undertakings_pending,
        "undertakings_verified": undertakings_verified,
        "undertakings_overdue": undertakings_overdue
    }, 200

@app.route("/api/applications/<int:application_id>", methods=["GET"])
def get_application_details(application_id):
    from models import Application

    application = db.session.get(Application, application_id)

    if not application:
        return {"error": "Application not found"}, 404

    return {
        "id": application.id,
        "tracking_id": application.tracking_id,
        "institution_name": application.institution_name,
        "application_type": application.application_type,
        "state": getattr(application, "state", None),
        "contact_email": (db.session.get(__import__("models").User, application.institution_user_id).email if application.institution_user_id and db.session.get(__import__("models").User, application.institution_user_id) else None),
        "current_stage": application.current_stage,
        "status": application.status,
        "submission_date": (
            application.submission_date.isoformat()
            if application.submission_date else None
        ),
        "deadline": (
            application.deadline.isoformat()
            if application.deadline else None
        ),
        "assigned_officer": application.assigned_officer,
        "remarks": application.remarks
    }, 200

@app.route("/api/applications/<int:application_id>/assign", methods=["PUT"])
def assign_officer(application_id):
    from models import Application, AuditLog
    data = request.get_json(silent=True) or {}
    officer = str(data.get("assigned_officer", "")).strip()
    reason = str(data.get("reason", "")).strip()
    if not officer:
        return {"error": "assigned_officer is required"}, 400
    if not reason:
        return {"error": "A reason is required when assigning or reassigning an officer"}, 400
    application = db.session.get(Application, application_id)
    if not application:
        return {"error": "Application not found"}, 404
    old_officer = application.assigned_officer
    application.assigned_officer = officer
    db.session.add(AuditLog(application_id=application.id, action="Officer assignment changed", performed_by=g.current_user.email, details=f"Reason: {reason}. Assigned officer: {old_officer or 'Unassigned'} -> {officer}"))
    db.session.commit()
    return {"message": "Officer assignment saved", "application_id": application.id, "assigned_officer": application.assigned_officer}, 200

@app.route("/api/applications/<int:application_id>/remarks", methods=["PUT"])
def update_application_remarks(application_id):
    from models import Application

    application = db.session.get(Application, application_id)

    if not application:
        return {"error": "Application not found"}, 404

    data = request.get_json(silent=True) or {}
    remarks = data.get("remarks")

    if remarks is None:
        return {"error": "remarks is required"}, 400

    application.remarks = remarks
    from models import AuditLog
    db.session.add(AuditLog(application_id=application.id, action="Application remarks updated", performed_by=g.current_user.email, details=f"Remarks: {remarks}"))
    db.session.commit()

    return {
        "message": "Remarks saved successfully",
        "application_id": application.id,
        "remarks": application.remarks
    }, 200
@app.route("/api/applications", methods=["POST"])
def create_application():
    from datetime import datetime
    from models import Application, AuditLog

    data = request.get_json(silent=True) or {}

    institution_name = data.get("institution_name")
    application_type = data.get("application_type")

    if not institution_name or not application_type:
        return {
            "error": "institution_name and application_type are required"
        }, 400

    allowed_types = {"New Institution", "Extension of Approval", "Increase in Intake", "New Course", "Change of Institution Name", "Closure of Course"}
    if application_type not in allowed_types:
        return {"error": "Unsupported application type."}, 400
    supplied_state = str(data.get("state", "") or "").strip()[:80] or None
    # Drafts have no review deadline. Ignore any client-provided deadline; the
    # server assigns the demo SLA only after mandatory submission checks pass.
    # Authorized officers may later adjust it through the audited /edit workflow.
    deadline = None
    application = Application(
        institution_user_id=g.current_user.id if getattr(g, "current_user", None) and g.current_user.role == "institution" else None,
        institution_name=(g.current_user.institution_name if getattr(g, "current_user", None) and g.current_user.role == "institution" else str(institution_name).strip()),
        application_type=application_type,
        state=supplied_state,
        deadline=deadline,
        remarks=str(data.get("remarks", "")).strip() or None,
        current_stage="Draft",
        status="Draft",
        submission_date=datetime.utcnow()
    )

    db.session.add(application)
    db.session.flush()
    application.tracking_id = f"AICTE-{datetime.utcnow().year}-{application.id:06d}"
    db.session.add(AuditLog(application_id=application.id, action="Application draft created", performed_by=g.current_user.email, details=f"Type: {application_type}; state: {supplied_state or 'Not supplied'}; review deadline will be assigned by the server after successful submission; client deadline values are ignored; notes: {application.remarks or 'None'}"))
    db.session.commit()

    return {
        "message": "Application created successfully",
        "application_id": application.id,
        "tracking_id": application.tracking_id,
        "deadline": None,
        "deadline_source": "assigned_on_submission"
    }, 201


@app.route("/api/applications/<int:application_id>/submit", methods=["POST"])
def submit_application(application_id):
    from models import Application, DocumentRequirement, UploadedDocument, AuditLog
    from datetime import datetime, timedelta
    if g.current_user.role != "institution":
        return {"error": "Only the owning institution can submit or resubmit this application."}, 403
    application = db.session.get(Application, application_id)
    if not application:
        return {"error": "Application not found"}, 404
    if application.current_stage not in {"Draft", "Deficiency Raised"}:
        return {"error": "Application is not currently eligible for submission or resubmission."}, 409
    all_requirements = DocumentRequirement.query.filter_by(application_type=application.application_type).all()
    if not all_requirements:
        return {"error": "Document requirements are not configured for this application type. Contact the administrator."}, 409
    requirements = [r for r in all_requirements if r.is_mandatory]
    uploaded_documents = UploadedDocument.query.filter_by(application_id=application.id).order_by(UploadedDocument.id.asc()).all()
    latest_by_requirement = {d.requirement_id: d for d in uploaded_documents}
    uploaded_ids = set(latest_by_requirement)
    missing = [r.document_name for r in requirements if r.id not in uploaded_ids]
    deficient = [d.file_name for d in latest_by_requirement.values() if d.upload_status in {"Deficient", "Rejected"}]
    if missing:
        return {"error": "Upload all mandatory documents before submitting.", "missing_documents": missing}, 400
    if deficient:
        return {"error": "One or more documents are marked deficient. Correct or have them reviewed before submitting.", "deficient_documents": deficient}, 400
    from models import DocumentIntegrityReview, RegulatoryRule
    rule = RegulatoryRule.query.filter_by(rule_key="manual_review_all_integrity_flags").first()
    require_review = (rule.value.lower() == "true") if rule else True
    resolved_states = ["Cleared — No Malpractice Established", "Closed", "Closed — Superseded by replacement"]
    active_flags = DocumentIntegrityReview.query.filter_by(application_id=application.id).filter(DocumentIntegrityReview.status.notin_(resolved_states)).all()
    if require_review and active_flags:
        return {"error": "Officer review is still required for document-integrity flags before submission.", "open_integrity_flags": [{"id":f.id,"category":f.flag_category,"status":f.status,"reason":f.reason} for f in active_flags]}, 409
    old_stage = application.current_stage
    is_resubmission = old_stage == "Deficiency Raised"
    deadline_assigned_now = application.deadline is None
    if deadline_assigned_now:
        try:
            sla_days = int(os.environ.get("DEMO_REVIEW_SLA_DAYS", "30"))
            if not 1 <= sla_days <= 365:
                sla_days = 30
        except (TypeError, ValueError):
            sla_days = 30
        application.deadline = datetime.utcnow() + timedelta(days=sla_days)
    application.current_stage = "Resubmitted" if is_resubmission else "Submitted"
    application.status = "Resubmitted" if is_resubmission else "Pending"
    deadline_detail = (f"System assigned demo review deadline {application.deadline.isoformat()} using SLA {sla_days} days." if deadline_assigned_now else f"Existing review deadline retained: {application.deadline.isoformat() if application.deadline else 'not set'}.")
    db.session.add(AuditLog(application_id=application.id, action="Application resubmitted" if is_resubmission else "Application submitted", performed_by=g.current_user.email, details=f"{old_stage} -> {application.current_stage}; required documents and integrity checks passed. {deadline_detail}"))
    db.session.commit()
    return {"message": "Corrected application resubmitted" if is_resubmission else "Application submitted", "application_id": application.id, "tracking_id": application.tracking_id, "current_stage": application.current_stage, "status": application.status, "deadline": application.deadline.isoformat() if application.deadline else None, "deadline_source": "system_demo_sla" if deadline_assigned_now else "existing_review_deadline"}, 200


@app.route("/api/applications/<int:application_id>/edit", methods=["PUT"])
def edit_application(application_id):
    from models import Application, AuditLog
    from datetime import datetime

    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason", "")).strip()
    performed_by = str(data.get("performed_by", "")).strip()

    if not reason:
        return {"error": "reason is required"}, 400
    # Never trust a client-supplied actor string for audit identity.
    performed_by = g.current_user.email
    if not reason:
        return {"error": "reason is required"}, 400

    allowed_fields = [
        "institution_name",
        "application_type",
        "state",
        "deadline",
        "assigned_officer",
        "remarks"
    ]
    fields = [field for field in allowed_fields if field in data]

    if not fields:
        return {"error": "No editable fields provided"}, 400

    application = db.session.get(Application, application_id)
    if not application:
        return {"error": "Application not found"}, 404

    changes = []

    for field in fields:
        old_value = getattr(application, field)
        new_value = data[field]

        if field in ["institution_name", "application_type", "state"]:
            if field == "state" and (new_value is None or not str(new_value).strip()):
                new_value = None
            elif not isinstance(new_value, str) or not new_value.strip():
                return {"error": field + " cannot be empty"}, 400
            new_value = new_value.strip()

        elif field == "deadline":
            if new_value in ("", None):
                new_value = None
            else:
                try:
                    new_value = datetime.fromisoformat(str(new_value))
                except ValueError:
                    return {
                        "error": "deadline must be ISO format, e.g. 2026-12-31T17:00:00"
                    }, 400

        elif field in ["assigned_officer", "remarks"]:
            if new_value is not None and not isinstance(new_value, str):
                return {"error": field + " must be text or null"}, 400
            if isinstance(new_value, str):
                new_value = new_value.strip() or None

        old_text = old_value.isoformat() if isinstance(old_value, datetime) else old_value
        new_text = new_value.isoformat() if isinstance(new_value, datetime) else new_value

        if old_text != new_text:
            setattr(application, field, new_value)
            changes.append(f"{field}: {old_text!r} -> {new_text!r}")

    if not changes:
        return {"message": "No changes detected"}, 200

    db.session.add(AuditLog(
        application_id=application_id,
        action="Application details edited",
        performed_by=performed_by,
        details=f"Reason: {reason}. Changes: " + "; ".join(changes)
    ))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Application edit failed")
        return {"error": "Failed to save edits"}, 500

    return {
        "message": "Application updated successfully",
        "application_id": application_id,
        "changed_fields": [x.split(":")[0] for x in changes],
        "reason": reason
    }, 200


@app.route("/api/applications/<int:application_id>/evc", methods=["POST"])
def schedule_evc(application_id):
    from models import Application, EVCRecord, AuditLog
    from datetime import datetime

    data = request.get_json(silent=True) or {}
    application = db.session.get(Application, application_id)

    if not application:
        return {"error": "Application not found"}, 404

    scheduled_date = data.get("scheduled_date")
    if not scheduled_date:
        return {"error": "scheduled_date is required"}, 400

    try:
        scheduled_date = datetime.fromisoformat(scheduled_date)
    except (ValueError, TypeError):
        return {
            "error": "Use ISO format, e.g. 2026-11-15T10:00:00"
        }, 400

    from models import User
    assigned_email = str(data.get("assigned_officer", "")).strip().lower()
    if not assigned_email:
        return {"error": "Enter the email address of a registered committee account so the visit can be routed to its queue."}, 400
    committee_user = User.query.filter_by(email=assigned_email, role="committee", active=True).first()
    if not committee_user:
        return {"error": "The assigned email must belong to an active committee account. Create one with python create_user.py committee."}, 400
    record = EVCRecord(
        application_id=application_id,
        committee_name=str(data.get("committee_name", "")).strip() or "EVC Committee",
        scheduled_date=scheduled_date,
        assigned_officer=committee_user.email,
        status="Scheduled",
        remarks=str(data.get("remarks", "")).strip() or None
    )
    # Keep workflow state consistent with the scheduled visit.
    if application.status not in {"Approved", "Rejected"}:
        application.current_stage = "EVC"
        application.status = "In Progress"

    db.session.add(record)
    db.session.add(AuditLog(
        application_id=application_id,
        action="EVC scheduled",
        performed_by=g.current_user.email,
        details=f"EVC scheduled for {scheduled_date.isoformat()}; committee: {record.committee_name}"
    ))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("EVC scheduling failed")
        return {"error": "Could not schedule EVC"}, 500

    return {
        "message": "EVC scheduled successfully",
        "evc_id": record.id,
        "application_id": application_id,
        "scheduled_date": record.scheduled_date.isoformat(),
        "status": record.status
    }, 201


@app.route("/api/applications/<int:application_id>/evc", methods=["GET"])
def get_application_evc(application_id):
    from models import Application, EVCRecord

    application = db.session.get(Application, application_id)
    if not application:
        return {"error": "Application not found"}, 404

    records = EVCRecord.query.filter_by(
        application_id=application_id
    ).order_by(EVCRecord.id.desc()).all()

    return {
        "application_id": application_id,
        "evc_records": [
            {
                "id": record.id,
                "committee_name": record.committee_name,
                "scheduled_date": (
                    record.scheduled_date.isoformat()
                    if record.scheduled_date else None
                ),
                "completed_date": (
                    record.completed_date.isoformat()
                    if record.completed_date else None
                ),
                "assigned_officer": record.assigned_officer,
                "status": record.status,
                "remarks": record.remarks
            }
            for record in records
        ]
    }, 200


@app.route("/api/applications/<int:application_id>/evc/<int:evc_id>", methods=["PUT"])
def update_evc(application_id, evc_id):
    from models import Application, EVCRecord, AuditLog
    from datetime import datetime

    data = request.get_json(silent=True) or {}
    application = db.session.get(Application, application_id)

    if not application:
        return {"error": "Application not found"}, 404

    record = db.session.get(EVCRecord, evc_id)
    if not record or record.application_id != application_id:
        return {"error": "EVC record not found"}, 404

    allowed_statuses = ["Scheduled", "In Progress", "Completed", "Delayed", "Cancelled"]
    new_status = data.get("status", record.status)
    if g.current_user.role == "committee":
        disallowed = set(data) - {"status", "remarks", "completed_date"}
        if disallowed:
            return {"error": "Committee accounts may update visit progress/completion remarks only."}, 403
        if new_status not in {"In Progress", "Completed"}:
            return {"error": "Committee accounts may move an assigned visit to In Progress or Completed only."}, 403
        if new_status == "Completed" and not str(data.get("remarks", record.remarks or "")).strip():
            return {"error": "Completion remarks are required."}, 400

    if new_status not in allowed_statuses:
        return {"error": "Invalid EVC status"}, 400

    if "scheduled_date" in data:
        try:
            record.scheduled_date = (
                datetime.fromisoformat(data["scheduled_date"])
                if data["scheduled_date"] else None
            )
        except (ValueError, TypeError):
            return {"error": "Invalid scheduled_date"}, 400

    if "completed_date" in data:
        try:
            record.completed_date = (
                datetime.fromisoformat(data["completed_date"])
                if data["completed_date"] else None
            )
        except (ValueError, TypeError):
            return {"error": "Invalid completed_date"}, 400

    if new_status == "Completed":
        if record.completed_date is None:
            record.completed_date = datetime.utcnow()

        if record.completed_date > datetime.utcnow():
            return {
                "error": "Completion date cannot be in the future"
            }, 400

    if "committee_name" in data:
        record.committee_name = data["committee_name"]
    if "assigned_officer" in data:
        record.assigned_officer = data["assigned_officer"]
    if "remarks" in data:
        record.remarks = data["remarks"]

    old_status = record.status
    record.status = new_status

    db.session.add(AuditLog(
        application_id=application_id,
        action="EVC updated",
        performed_by=g.current_user.email,
        details=f"EVC ID {evc_id}: status {old_status} -> {new_status}; remarks: {record.remarks or 'None'}"
    ))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("EVC update failed")
        return {"error": "Could not update EVC"}, 500

    return {
        "message": "EVC record updated",
        "evc_id": record.id,
        "status": record.status,
        "completed_date": (
            record.completed_date.isoformat()
            if record.completed_date else None
        )
    }, 200


@app.route("/api/evc/overdue", methods=["GET"])
def get_overdue_evc():
    from models import EVCRecord
    from datetime import datetime

    now = datetime.utcnow()
    overdue_query = EVCRecord.query.filter(
        EVCRecord.scheduled_date < now,
        EVCRecord.status.notin_(["Completed", "Cancelled"])
    )
    if g.current_user.role == "committee":
        overdue_query = overdue_query.filter_by(assigned_officer=g.current_user.email)
    records = overdue_query.order_by(EVCRecord.scheduled_date.asc()).all()

    return {
        "overdue_evc": [
            {
                "evc_id": record.id,
                "application_id": record.application_id,
                "scheduled_date": record.scheduled_date.isoformat(),
                "status": record.status,
                "assigned_officer": record.assigned_officer,
                "committee_name": record.committee_name
            }
            for record in records
        ]
    }, 200

@app.route("/api/applications/<int:application_id>/undertakings", methods=["POST"])

def create_undertaking(application_id):
    from models import Application, Undertaking, AuditLog
    from datetime import datetime

    data = request.get_json(silent=True) or {}
    application = db.session.get(Application, application_id)

    if not application:
        return {"error": "Application not found"}, 404

    title = str(data.get("title", "")).strip()
    if not title:
        return {"error": "title is required"}, 400

    try:
        due_date = datetime.fromisoformat(str(data.get("due_date", "")))
    except ValueError:
        return {
            "error": "due_date is required in ISO format, e.g. 2026-12-31T23:59:00"
        }, 400

    undertaking = Undertaking(
        application_id=application_id,
        title=title,
        description=data.get("description"),
        due_date=due_date,
        status="Pending"
    )

    db.session.add(undertaking)
    db.session.add(AuditLog(
        application_id=application_id,
        action="Undertaking created",
        performed_by=g.current_user.email,
        details=f"Undertaking: {title}; due: {due_date.isoformat()}"
    ))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Undertaking creation failed")
        return {"error": "Could not create undertaking"}, 500

    return {
        "message": "Undertaking created successfully",
        "undertaking_id": undertaking.id,
        "application_id": application_id,
        "title": undertaking.title,
        "due_date": undertaking.due_date.isoformat(),
        "status": undertaking.status
    }, 201


@app.route("/api/applications/<int:application_id>/undertakings", methods=["GET"])
def get_undertakings(application_id):
    from models import Application, Undertaking

    application = db.session.get(Application, application_id)
    if not application:
        return {"error": "Application not found"}, 404

    records = Undertaking.query.filter_by(
        application_id=application_id
    ).order_by(Undertaking.due_date.asc()).all()

    return {
        "application_id": application_id,
        "undertakings": [
            {
                "id": u.id,
                "title": u.title,
                "description": u.description,
                "due_date": u.due_date.isoformat(),
                "status": u.status,
                "evidence_file": u.evidence_file,
                "submitted_at": u.submitted_at.isoformat() if u.submitted_at else None,
                "verified_by": u.verified_by,
                "verified_at": u.verified_at.isoformat() if u.verified_at else None,
                "remarks": u.remarks
            }
            for u in records
        ]
    }, 200


@app.route("/api/applications/<int:application_id>/undertakings/<int:undertaking_id>/submit", methods=["PUT"])
def submit_undertaking_evidence(application_id, undertaking_id):
    from models import Application, Undertaking, AuditLog
    from datetime import datetime

    data = request.get_json(silent=True) or {}
    application = db.session.get(Application, application_id)
    undertaking = db.session.get(Undertaking, undertaking_id)

    if not application:
        return {"error": "Application not found"}, 404
    if not undertaking or undertaking.application_id != application_id:
        return {"error": "Undertaking not found"}, 404
    if undertaking.status in ["Verified", "Rejected"]:
        return {"error": "This undertaking has already been reviewed"}, 409

    evidence_file = str(data.get("evidence_file", "")).strip()
    if not evidence_file:
        return {"error": "evidence_file is required"}, 400

    undertaking.evidence_file = evidence_file
    undertaking.submitted_at = datetime.utcnow()
    undertaking.status = "Submitted"
    undertaking.remarks = data.get("remarks")

    db.session.add(AuditLog(
        application_id=application_id,
        action="Undertaking evidence submitted",
        performed_by=g.current_user.email,
        details=f"Undertaking ID {undertaking_id}; evidence reference: {evidence_file}"
    ))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Undertaking evidence submission failed")
        return {"error": "Could not save evidence submission"}, 500

    return {
        "message": "Undertaking evidence submitted",
        "undertaking_id": undertaking.id,
        "status": undertaking.status,
        "submitted_at": undertaking.submitted_at.isoformat()
    }, 200


@app.route("/api/applications/<int:application_id>/undertakings/<int:undertaking_id>/verify", methods=["PUT"])
def verify_undertaking(application_id, undertaking_id):
    from models import Application, Undertaking, AuditLog
    from datetime import datetime

    data = request.get_json(silent=True) or {}
    decision = data.get("decision")
    performed_by = g.current_user.email
    remarks = str(data.get("remarks", "")).strip()

    if decision not in ["Verified", "Rejected"]:
        return {"error": "decision must be Verified or Rejected"}, 400
    if decision == "Rejected" and not remarks:
        return {"error": "remarks are required when rejecting evidence"}, 400

    application = db.session.get(Application, application_id)
    undertaking = db.session.get(Undertaking, undertaking_id)

    if not application:
        return {"error": "Application not found"}, 404
    if not undertaking or undertaking.application_id != application_id:
        return {"error": "Undertaking not found"}, 404
    if undertaking.status != "Submitted":
        return {"error": "Only submitted evidence can be verified"}, 409

    undertaking.status = decision
    undertaking.verified_by = performed_by
    undertaking.verified_at = datetime.utcnow()
    undertaking.remarks = remarks or None

    db.session.add(AuditLog(
        application_id=application_id,
        action=f"Undertaking evidence {decision}",
        performed_by=g.current_user.email,
        details=f"Undertaking ID {undertaking_id}; remarks: {remarks or 'None'}"
    ))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Undertaking verification failed")
        return {"error": "Could not save verification"}, 500

    return {
        "message": f"Undertaking evidence {decision.lower()}",
        "undertaking_id": undertaking.id,
        "status": undertaking.status,
        "verified_by": undertaking.verified_by,
        "verified_at": undertaking.verified_at.isoformat()
    }, 200


@app.route("/api/applications/<int:application_id>/undertakings/<int:undertaking_id>/evidence", methods=["POST"])
def upload_undertaking_evidence(application_id, undertaking_id):
    """Upload the actual evidence bytes; the older text-reference API remains supported."""
    from datetime import datetime
    from werkzeug.utils import secure_filename
    from models import Application, Undertaking, AuditLog
    application = db.session.get(Application, application_id)
    undertaking = db.session.get(Undertaking, undertaking_id)
    if not application or not undertaking or undertaking.application_id != application_id:
        return {"error": "Application or undertaking not found"}, 404
    if undertaking.status in {"Verified", "Rejected"}:
        return {"error": "This undertaking has already been reviewed"}, 409
    file = request.files.get("file")
    if not file or not file.filename:
        return {"error": "Choose a PDF, JPG or PNG evidence file"}, 400
    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return {"error": "Only PDF, JPG and PNG evidence files are supported"}, 400
    file.stream.seek(0); header = file.stream.read(16); file.stream.seek(0)
    from document_integrity import file_signature_matches
    if not file_signature_matches(ext, header):
        return {"error": "Evidence file contents do not match its extension"}, 400
    saved_name = secure_filename(f"undertaking_{undertaking.id}_{application_id}_{filename}")
    path = os.path.abspath(os.path.join(UPLOAD_FOLDER, saved_name))
    if os.path.commonpath([path, os.path.abspath(UPLOAD_FOLDER)]) != os.path.abspath(UPLOAD_FOLDER):
        return {"error": "Invalid evidence file path"}, 400
    try:
        file.save(path)
        undertaking.evidence_file = path
        undertaking.submitted_at = datetime.utcnow()
        undertaking.status = "Submitted"
        undertaking.remarks = str(request.form.get("remarks", "")).strip() or None
        db.session.add(AuditLog(application_id=application_id, action="Undertaking evidence uploaded", performed_by=g.current_user.email, details=f"Undertaking {undertaking.id}; file {filename}"))
        db.session.commit()
    except Exception:
        db.session.rollback()
        try:
            if os.path.isfile(path): os.remove(path)
        except OSError: pass
        app.logger.exception("Undertaking evidence upload failed")
        return {"error": "Could not save evidence upload"}, 500
    return {"message": "Evidence uploaded for verification", "undertaking_id": undertaking.id, "file_name": filename, "status": undertaking.status}, 201


@app.route("/api/applications/<int:application_id>/undertakings/<int:undertaking_id>/evidence/file", methods=["GET"])
def view_undertaking_evidence(application_id, undertaking_id):
    from models import Undertaking
    undertaking = db.session.get(Undertaking, undertaking_id)
    if not undertaking or undertaking.application_id != application_id or not undertaking.evidence_file:
        return {"error": "Evidence file not found"}, 404
    path = os.path.abspath(undertaking.evidence_file)
    root = os.path.abspath(UPLOAD_FOLDER)
    if os.path.commonpath([path, root]) != root or not os.path.isfile(path):
        return {"error": "Evidence file is unavailable"}, 404
    response = send_file(path, as_attachment=False, download_name=os.path.basename(path))
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@app.route("/api/undertakings/overdue", methods=["GET"])
def get_overdue_undertakings():
    from models import Undertaking
    from datetime import datetime
    if g.current_user.role not in {"officer", "authority"}:
        return {"error": "Officer or authority role required"}, 403
    now = datetime.utcnow()
    records = Undertaking.query.filter(
        Undertaking.due_date < now,
        Undertaking.status.notin_(["Verified", "Rejected"])
    ).order_by(Undertaking.due_date.asc()).all()

    return {
        "overdue_undertakings": [
            {
                "id": u.id,
                "application_id": u.application_id,
                "title": u.title,
                "due_date": u.due_date.isoformat(),
                "status": u.status
            }
            for u in records
        ]
    }, 200

from datetime import date, timedelta

@app.route("/api/applications/<int:application_id>/documents/<int:document_id>/validity", methods=["PUT"])
def update_document_validity(application_id, document_id):
    from datetime import date
    from models import Application, UploadedDocument, AuditLog
    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason", "")).strip()
    if not reason:
        return {"error": "A change reason is required"}, 400
    application = db.session.get(Application, application_id)
    document = UploadedDocument.query.filter_by(id=document_id, application_id=application_id).first()
    if not application or not document:
        return {"error": "Application or document not found"}, 404
    try:
        issue_value = data.get("issue_date")
        expiry_value = data.get("expiry_date")
        issue_date = date.fromisoformat(issue_value) if issue_value else None
        expiry_date = date.fromisoformat(expiry_value) if expiry_value else None
    except (ValueError, TypeError):
        return {"error": "Dates must use YYYY-MM-DD format"}, 400
    if issue_date and expiry_date and issue_date > expiry_date:
        return {"error": "Issue date cannot be after expiry date"}, 400
    old = f"issue={document.issue_date}; expiry={document.expiry_date}"
    document.issue_date = issue_date
    document.expiry_date = expiry_date
    db.session.add(AuditLog(application_id=application_id, action="Document validity dates updated", performed_by=g.current_user.email, details=f"Reason: {reason}. Changes: {old} -> issue={issue_date}; expiry={expiry_date}"))
    db.session.commit()
    return {"message": "Document validity dates saved", "document_id": document.id, "issue_date": issue_date.isoformat() if issue_date else None, "expiry_date": expiry_date.isoformat() if expiry_date else None}, 200


@app.route("/api/documents/expiry-alerts", methods=["GET"])
def document_expiry_alerts():
    from models import UploadedDocument

    from models import RegulatoryRule
    today = date.today()
    rule = RegulatoryRule.query.filter_by(rule_key="expiry_warning_days").first()
    try:
        warning_days = max(1, min(365, int(rule.value))) if rule else 30
    except (TypeError, ValueError):
        warning_days = 30
    cutoff = today + timedelta(days=warning_days)

    documents = UploadedDocument.query.filter(
        UploadedDocument.expiry_date.isnot(None),
        UploadedDocument.expiry_date <= cutoff
    ).order_by(UploadedDocument.expiry_date.asc()).all()

    alerts = []

    for doc in documents:
        expired = doc.expiry_date < today

        alerts.append({
            "document_id": doc.id,
            "application_id": doc.application_id,
            "file_name": doc.file_name,
            "expiry_date": doc.expiry_date.isoformat(),
            "days_remaining": (doc.expiry_date - today).days,
            "alert_type": "Expired" if expired else "Expiring Soon",
            "renewal_status": doc.renewal_status,
            "upload_status": doc.upload_status
        })

    return {
        "total_alerts": len(alerts),
        "alerts": alerts
    }, 200


@app.route("/api/documents/expired", methods=["GET"])
def expired_documents():
    from models import UploadedDocument

    today = date.today()

    documents = UploadedDocument.query.filter(
        UploadedDocument.expiry_date.isnot(None),
        UploadedDocument.expiry_date < today
    ).order_by(UploadedDocument.expiry_date.asc()).all()

    return {
        "total_expired": len(documents),
        "documents": [
            {
                "document_id": doc.id,
                "application_id": doc.application_id,
                "file_name": doc.file_name,
                "expiry_date": doc.expiry_date.isoformat(),
                "renewal_status": doc.renewal_status
            }
            for doc in documents
        ]
    }, 200

@app.route("/api/applications/<int:application_id>/documents/<int:document_id>/renew-upload", methods=["POST"])
def upload_document_renewal(application_id, document_id):
    """Upload the replacement file; current document stays active until officer verifies it."""
    from datetime import date, datetime
    from werkzeug.utils import secure_filename
    from models import Application, UploadedDocument, AuditLog
    application = db.session.get(Application, application_id)
    original = UploadedDocument.query.filter_by(id=document_id, application_id=application_id).first()
    if not application or not original:
        return {"error": "Application or document not found"}, 404
    if original.renewal_status == "Submitted":
        return {"error": "A renewal is already awaiting review"}, 409
    file = request.files.get("file")
    if not file or not file.filename:
        return {"error": "Select the renewed PDF, JPG or PNG file"}, 400
    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return {"error": "Only PDF, JPG and PNG are supported"}, 400
    file.stream.seek(0); header=file.stream.read(16); file.stream.seek(0)
    from document_integrity import file_signature_matches, sha256_stream, extract_document_text
    if not file_signature_matches(ext, header):
        return {"error": "File contents do not match the extension"}, 400
    issue_value = (request.form.get("issue_date") or "").strip()
    expiry_value = (request.form.get("expiry_date") or "").strip()
    if not expiry_value:
        return {"error": "Expiry date is required"}, 400
    try:
        issue_date = date.fromisoformat(issue_value) if issue_value else None
        expiry_date = date.fromisoformat(expiry_value)
    except ValueError:
        return {"error": "Dates must use YYYY-MM-DD"}, 400
    if expiry_date <= date.today() or (issue_date and issue_date > expiry_date):
        return {"error": "Expiry must be in the future and issue date cannot be later than expiry"}, 400
    hash_value = sha256_stream(file.stream)
    saved_name = secure_filename(f"renewal_{application_id}_{document_id}_{int(datetime.utcnow().timestamp())}_{filename}")
    path = os.path.abspath(os.path.join(UPLOAD_FOLDER, saved_name))
    try:
        file.save(path)
        try:
            extracted = extract_document_text(path)
        except Exception:
            extracted = ""
        renewed = UploadedDocument(application_id=application_id, requirement_id=original.requirement_id, file_name=filename, file_path=path, sha256=hash_value, extracted_text=extracted or None, upload_status="Renewal Pending Verification", remarks=f"Renewal of document {original.id}; awaiting officer review.")
        db.session.add(renewed); db.session.flush()
        original.renewed_document_id = renewed.id
        original.proposed_issue_date = issue_date
        original.proposed_expiry_date = expiry_date
        original.renewal_status = "Submitted"
        db.session.add(AuditLog(application_id=application_id, action="Document renewal file uploaded", performed_by=g.current_user.email, details=f"Original document {original.id}; replacement {renewed.id} ({filename}); proposed expiry {expiry_date.isoformat()}"))
        db.session.commit()
    except Exception:
        db.session.rollback()
        try:
            if os.path.isfile(path): os.remove(path)
        except OSError: pass
        app.logger.exception("Renewal upload failed")
        return {"error": "Could not save renewal document"}, 500
    return {"message": "Renewal file saved for officer verification", "document_id": original.id, "renewed_document_id": renewed.id, "renewal_status": original.renewal_status}, 201


@app.route(
    "/api/applications/<int:application_id>/documents/<int:document_id>/renew",
    methods=["PUT"]
)
def submit_document_renewal(application_id, document_id):
    from datetime import date
    from models import Application, UploadedDocument, AuditLog

    data = request.get_json(silent=True) or {}

    new_expiry = data.get("expiry_date")
    performed_by = g.current_user.email
    issue_date_value = data.get("issue_date")

    if not new_expiry:
        return {"error": "expiry_date is required (YYYY-MM-DD)"}, 400

    try:
        expiry_date = date.fromisoformat(new_expiry)
        issue_date = (
            date.fromisoformat(issue_date_value)
            if issue_date_value else None
        )
    except (ValueError, TypeError):
        return {"error": "Dates must use YYYY-MM-DD format"}, 400

    if expiry_date <= date.today():
        return {"error": "New expiry date must be in the future"}, 400

    if issue_date and issue_date > expiry_date:
        return {"error": "issue_date cannot be after expiry_date"}, 400

    application = db.session.get(Application, application_id)
    if not application:
        return {"error": "Application not found"}, 404

    document = UploadedDocument.query.filter_by(
        id=document_id,
        application_id=application_id
    ).first()

    if not document:
        return {"error": "Document not found for this application"}, 404

    old_expiry = (
        document.expiry_date.isoformat()
        if document.expiry_date else "Unknown"
    )

    # Keep current dates unchanged until the renewal is verified.
    document.proposed_expiry_date = expiry_date
    document.proposed_issue_date = issue_date
    document.renewal_status = "Submitted"

    db.session.add(AuditLog(
        application_id=application_id,
        action="Document renewal submitted",
        performed_by=performed_by,
        details=(
            f"Document ID {document.id}; "
            f"previous expiry: {old_expiry}; "
            f"submitted expiry: {expiry_date.isoformat()}"
        )
    ))

    db.session.commit()

    return {
        "message": "Document renewal submitted for verification",
        "document_id": document.id,
        "renewal_status": document.renewal_status,
        "current_expiry_date": (
            document.expiry_date.isoformat()
            if document.expiry_date else None
        ),
        "proposed_expiry_date": (
            document.proposed_expiry_date.isoformat()
            if document.proposed_expiry_date else None
        )
    }, 200


with app.app_context():
    from models import Application, WorkflowStage, AuditLog, RegulatoryRule
    db.create_all()
    # Safe SQLite additive migration for existing demo databases.
    if db.engine.dialect.name == "sqlite":
        from sqlalchemy import text as sql_text
        columns = {row[1] for row in db.session.execute(sql_text("PRAGMA table_info(application)")).all()}
        if "state" not in columns:
            db.session.execute(sql_text("ALTER TABLE application ADD COLUMN state VARCHAR(80)"))
            db.session.commit()
        alert_columns = {row[1] for row in db.session.execute(sql_text("PRAGMA table_info(persistent_alert)")).all()}
        if "escalation_level" not in alert_columns:
            db.session.execute(sql_text("ALTER TABLE persistent_alert ADD COLUMN escalation_level INTEGER NOT NULL DEFAULT 0"))
        if "escalated_to" not in alert_columns:
            db.session.execute(sql_text("ALTER TABLE persistent_alert ADD COLUMN escalated_to VARCHAR(1000)"))
        db.session.commit()
    # These are configurable sample rules, not official or verified AICTE/APH policy.
    sample_rules = [
        ("duplicate_text_similarity", "Near-duplicate text similarity threshold", "0.88", "Demo threshold from 0 to 1; lower values flag more common-template matches."),
        ("expiry_warning_days", "Document expiry warning window (days)", "30", "Configurable demo reminder window."),
        ("escalation_level_1_days", "Escalation level 1 after overdue days", "7", "Configurable local demo escalation threshold; not official policy."),
        ("escalation_level_2_days", "Escalation level 2 after overdue days", "14", "Configurable local demo escalation threshold; not official policy."),
        ("manual_review_all_integrity_flags", "Require human review for integrity flags", "true", "Do not automatically declare uploaded documents fraudulent."),
        ("email_alerts_enabled", "Email alert sending enabled", "false", "Email delivery works only after SMTP environment settings are configured."),
    ]
    
    # Fictional SIH demo applications; safe to run repeatedly.
    demo_applications = [
        {
            "tracking_id": "DEMO-AICTE-001",
            "institution_name": "Apex Institute of Technology",
            "application_type": "New Institution Approval",
            "state": "Karnataka",
            "current_stage": "Document Verification",
            "status": "Under Review",
            "assigned_officer": "Demo Review Officer",
            "remarks": "Demo case: affiliation document requires verification.",
        },
        {
            "tracking_id": "DEMO-AICTE-002",
            "institution_name": "Greenfield Engineering College",
            "application_type": "Extension of Approval",
            "state": "Tamil Nadu",
            "current_stage": "Compliance Review",
            "status": "Compliant",
            "assigned_officer": "Demo Compliance Officer",
            "remarks": "Demo case: compliance checks completed.",
        },
        {
            "tracking_id": "DEMO-AICTE-003",
            "institution_name": "Sunrise Institute of Management",
            "application_type": "New Institution Approval",
            "state": "Maharashtra",
            "current_stage": "Application Review",
            "status": "Pending",
            "assigned_officer": "Demo Review Officer",
            "remarks": "Demo case: faculty details require completion.",
        },
        {
            "tracking_id": "DEMO-AICTE-004",
            "institution_name": "Horizon Technical University",
            "application_type": "Change of Intake",
            "state": "Telangana",
            "current_stage": "Integrity Review",
            "status": "Under Review",
            "assigned_officer": "Demo Integrity Officer",
            "remarks": "Demo case: potential duplicate document; manual review required.",
        },
        {
            "tracking_id": "DEMO-AICTE-005",
            "institution_name": "Riverdale College of Engineering",
            "application_type": "Renewal",
            "state": "Kerala",
            "current_stage": "Approval Completed",
            "status": "Approved",
            "assigned_officer": "Demo Approval Officer",
            "remarks": "Fictional demo case: approval workflow completed.",
        },
    ]

    for item in demo_applications:
        existing = Application.query.filter_by(
            tracking_id=item["tracking_id"]
        ).first()

        if not existing:
            db.session.add(Application(**item))

    db.session.commit()
    
    # Demo alerts for presentation; safe to run repeatedly.
    from models import PersistentAlert

    apex = Application.query.filter_by(
        tracking_id="DEMO-AICTE-001"
    ).first()

    horizon = Application.query.filter_by(
        tracking_id="DEMO-AICTE-004"
    ).first()

    demo_alerts = []

    if apex:
        demo_alerts.append({
            "alert_key": "demo:missing-document:DEMO-AICTE-001",
            "application_id": apex.id,
            "alert_type": "Demo Missing Document",
            "title": "Affiliation document requires verification",
            "details": (
                "Demo alert: verify the affiliation document "
                "for Apex Institute of Technology."
            ),
            "status": "Open",
        })

    if horizon:
        demo_alerts.append({
            "alert_key": "demo:integrity-review:DEMO-AICTE-004",
            "application_id": horizon.id,
            "alert_type": "Document Integrity Review",
            "title": "Potential duplicate document flagged",
            "details": (
                "Demo-only flag for Horizon Technical University. "
                "Manual review is required; this is not a confirmed finding."
            ),
            "status": "Open",
        })

    for item in demo_alerts:
        existing = PersistentAlert.query.filter_by(
            alert_key=item["alert_key"]
        ).first()

        if not existing:
            db.session.add(PersistentAlert(**item))

    db.session.commit()


    for key, label, value, description in sample_rules:
        if not RegulatoryRule.query.filter_by(rule_key=key).first():
            db.session.add(RegulatoryRule(rule_key=key, label=label, value=value, description=description))
    db.session.commit()

@app.route("/api/integrity-reviews", methods=["GET"])
def list_integrity_reviews():
    """Officer-only human review queue; automated flags are advisory."""
    from models import DocumentIntegrityReview, Application, UploadedDocument
    reviews = DocumentIntegrityReview.query.order_by(DocumentIntegrityReview.created_at.desc()).all()
    result = []
    for review in reviews:
        application = db.session.get(Application, review.application_id)
        document = db.session.get(UploadedDocument, review.document_id)
        matching = db.session.get(UploadedDocument, review.matching_document_id) if review.matching_document_id else None
        result.append({
            "id": review.id,
            "application_id": review.application_id,
            "tracking_id": application.tracking_id if application else None,
            "institution_name": application.institution_name if application else "Unknown institution",
            "document_id": review.document_id,
            "document_name": document.file_name if document else "Unavailable document",
            "matching_document_id": review.matching_document_id,
            "matching_application_id": matching.application_id if matching else None,
            "matching_document_name": matching.file_name if matching else None,
            "flag_category": review.flag_category,
            "reason": review.reason,
            "status": review.status,
            "officer_remarks": review.officer_remarks,
            "assigned_officer": review.assigned_officer,
            "created_at": review.created_at.isoformat() if review.created_at else None,
            "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
        })
    return {"reviews": result}, 200


@app.route("/api/integrity-reviews/<int:review_id>", methods=["PUT"])
def update_integrity_review(review_id):
    """Prototype review action. Officer authentication is required before deployment."""
    from datetime import datetime
    from models import DocumentIntegrityReview
    data = request.get_json(silent=True) or {}
    allowed = {
        "Under Investigation", "Clarification Requested",
        "Cleared — No Malpractice Established", "Duplicate Confirmed",
        "Suspected Alteration — Escalated", "Referred for Further Verification",
        "Closed"
    }
    status = data.get("status")
    if status not in allowed:
        return {"error": "Invalid review status"}, 400
    review = db.session.get(DocumentIntegrityReview, review_id)
    if not review:
        return {"error": "Review not found"}, 404
    from models import AuditLog, Application, UploadedDocument
    old_status = review.status
    review.status = status
    review.officer_remarks = str(data.get("officer_remarks", "")).strip() or None
    review.assigned_officer = g.current_user.email
    review.reviewed_at = datetime.utcnow()

    application = db.session.get(Application, review.application_id)
    reviewed_document = db.session.get(UploadedDocument, review.document_id)
    if status == "Cleared — No Malpractice Established" and reviewed_document:
        # Keep the document under review until every active flag attached to this document is closed.
        open_statuses = ["Flagged — Pending Review", "Under Investigation", "Clarification Requested", "Duplicate Confirmed", "Suspected Alteration — Escalated", "Referred for Further Verification"]
        other_document_flags = DocumentIntegrityReview.query.filter(
            DocumentIntegrityReview.document_id == reviewed_document.id,
            DocumentIntegrityReview.id != review.id,
            DocumentIntegrityReview.status.in_(open_statuses)
        ).count()
        if other_document_flags:
            reviewed_document.upload_status = "Uploaded — Manual Review Recommended"
            reviewed_document.remarks = "One integrity flag was cleared; other flags on this document still require review."
        else:
            reviewed_document.upload_status = "Verified"
            reviewed_document.verified_by = g.current_user.email
            reviewed_document.verified_at = datetime.utcnow()
            reviewed_document.remarks = review.officer_remarks or "Integrity warning reviewed and cleared by officer."
        # Do not silently turn a deficient application into an in-review application.
        # Keep the institution's formal resubmission action available after corrections.
        if application and application.current_stage == "Deficiency Raised" and application.status == "Deficient":
            other_open = DocumentIntegrityReview.query.filter(
                DocumentIntegrityReview.application_id == application.id,
                DocumentIntegrityReview.status.in_(open_statuses)
            ).count()
            deficient_docs = UploadedDocument.query.filter(
                UploadedDocument.application_id == application.id,
                UploadedDocument.upload_status.in_(["Deficient", "Rejected"])
            ).count()
            if not other_open and not deficient_docs:
                application.remarks = "Integrity review cleared. Submit the corrected application formally to resume the workflow."

    db.session.add(AuditLog(application_id=review.application_id, action="Document integrity review updated", performed_by=g.current_user.email, details=f"Review {review.id}: {old_status} -> {status}. Remarks: {review.officer_remarks or 'None'}"))
    db.session.commit()
    return {"message": "Review updated", "review_id": review.id, "status": review.status}, 200


@app.route("/api/document-requirements", methods=["GET"])
def get_document_requirements():
    from models import DocumentRequirement

    application_type = request.args.get("application_type")

    if not application_type:
        return {
            "error": "application_type is required"
        }, 400

    requirements = DocumentRequirement.query.filter_by(
        application_type=application_type
    ).order_by(DocumentRequirement.sequence_order.asc()).all()

    return {
        "application_type": application_type,
        "documents": [
            {
                "id": doc.id,
                "document_name": doc.document_name,
                "description": doc.description,
                "is_mandatory": doc.is_mandatory,
                "sequence_order": doc.sequence_order
            }
            for doc in requirements
        ]
    }, 200


from werkzeug.utils import secure_filename
from flask import request
import os
from datetime import datetime

UPLOAD_FOLDER = os.path.join(app.root_path, "uploads")
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route(
    "/api/applications/<int:application_id>/documents/<int:document_id>/ai-validation",
    methods=["POST"]
)
def validate_document_with_ai(application_id, document_id):
    from pathlib import Path
    from models import Application, UploadedDocument
    from document_ai import (
        extract_document_text,
        inspect_document_text,
        extract_and_check_expiry,
        validate_required_fields
    )

    application = db.session.get(Application, application_id)
    if not application:
        return {"error": "Application not found"}, 404

    document = UploadedDocument.query.filter_by(
        id=document_id,
        application_id=application_id
    ).first()

    if not document:
        return {"error": "Document not found for this application"}, 404

    file_path = Path(document.file_path)
    if not file_path.is_absolute():
        file_path = Path(app.root_path) / file_path

    extraction = extract_document_text(file_path)

    result = {
        "application_id": application_id,
        "document_id": document_id,
        "file_name": document.file_name,
        "processing_status": extraction["status"],
        "reason": extraction["reason"],
        "findings": [],
        "text_length": len(extraction["text"]),
        "advisory_only": True
    }

    if not extraction["text"]:
        result["validation_status"] = "Needs Manual Review"
        result["findings"].append({
            "type": extraction["status"],
            "severity": "Review",
            "evidence": extraction["reason"] or
                        "Text extraction was unsuccessful"
        })
        return result, 200

    text = extraction["text"]

    expiry_check = extract_and_check_expiry(text)
    result["expiry_validation"] = expiry_check

    institution_checks = inspect_document_text(
        text,
        expected_institution=application.institution_name
    )

    required_checks = validate_required_fields(
        text,
        expected_institution=application.institution_name
    )

    result["institution_validation"] = institution_checks
    result["required_field_validation"] = required_checks

    # Keep all findings, but remove exact duplicate entries.
    all_findings = (
        expiry_check.get("findings", [])
        + institution_checks.get("findings", [])
        + required_checks.get("findings", [])
    )

    seen = set()
    for finding in all_findings:
        key = (
            finding.get("type"),
            finding.get("severity"),
            finding.get("evidence")
        )
        if key not in seen:
            seen.add(key)
            result["findings"].append(finding)

    if expiry_check.get("status") == "Expired":
        result["validation_status"] = "Expired - Manual Review Required"
    elif result["findings"]:
        result["validation_status"] = "Needs Manual Review"
    else:
        result["validation_status"] = "Required Fields Detected - Review Required"

    return result, 200


@app.route(
    "/api/applications/<int:application_id>/documents",
    methods=["POST"]
)
def upload_application_document(application_id):
    from models import Application, DocumentRequirement, UploadedDocument, AuditLog

    application = db.session.get(Application, application_id)
    if not application:
        return {"error": "Application not found"}, 404

    requirement_id = request.form.get("requirement_id", type=int)
    uploaded_file = request.files.get("file")

    if not requirement_id or not uploaded_file:
        return {"error": "requirement_id and file are required"}, 400

    requirement = db.session.get(DocumentRequirement, requirement_id)
    if not requirement or requirement.application_type != application.application_type:
        return {"error": "Invalid document requirement for this application"}, 400

    if not uploaded_file.filename:
        return {"error": "Please select a file"}, 400

    filename = secure_filename(uploaded_file.filename)
    if not filename or "." not in filename:
        return {"error": "Invalid filename"}, 400

    extension = filename.rsplit(".", 1)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        return {"error": "Only PDF, PNG, JPG and JPEG files are allowed"}, 400

    # Do not trust the filename extension alone. Reject files whose binary signature
    # does not match the declared format, which catches simple extension spoofing.
    try:
        uploaded_file.stream.seek(0)
        header = uploaded_file.stream.read(16)
        uploaded_file.stream.seek(0)
    except (AttributeError, OSError):
        header = b""
    from document_integrity import file_signature_matches
    if not file_signature_matches(extension, header):
        return {"error": "The file contents do not match its extension. Please upload a valid PDF, PNG or JPEG file."}, 400

    existing = UploadedDocument.query.filter_by(
        application_id=application_id,
        requirement_id=requirement_id
    ).first()

    if existing:
        return {"error": "This document has already been uploaded"}, 409

    previous_requirements = DocumentRequirement.query.filter(
        DocumentRequirement.application_type == application.application_type,
        DocumentRequirement.is_mandatory.is_(True),
        DocumentRequirement.sequence_order < requirement.sequence_order
    ).all()

    for previous in previous_requirements:
        previous_upload = UploadedDocument.query.filter_by(
            application_id=application_id,
            requirement_id=previous.id
        ).first()

        if not previous_upload:
            return {
                "error": "Upload the earlier required documents first",
                "next_required_document": previous.document_name
            }, 400

    # Hash the exact bytes for duplicate screening. A match is only a review flag,
    # not evidence of malpractice and never automatically rejects an application.
    from document_integrity import sha256_stream
    file_hash = sha256_stream(uploaded_file.stream)

    from models import DocumentIntegrityReview
    matching_document = UploadedDocument.query.filter(
        UploadedDocument.sha256 == file_hash
    ).first()

    saved_name = f"app_{application_id}_req_{requirement_id}_{filename}"
    file_path = os.path.join(UPLOAD_FOLDER, saved_name)

    try:
        uploaded_file.save(file_path)
        from document_integrity import (
            extract_document_text, similarity_ratio, screen_document_text,
            detect_requirement_type_mismatch
        )
        extracted_text = None
        processing_error = None
        try:
            extracted_text = extract_document_text(file_path)
            if not extracted_text or not extracted_text.strip():
                processing_error = "No machine-readable text was extracted; OCR may be unavailable or the file may be image-only. Manual review is required."
        except Exception as exc:
            processing_error = str(exc)[:500]
            app.logger.warning("Document text extraction failed for upload: %s", processing_error)

        text_findings = screen_document_text(extracted_text or "")
        text_findings.extend(detect_requirement_type_mismatch(
            extracted_text or "", requirement.document_name
        ))
        # Content flags with explicit placeholder/signature problems, duplicate bytes,
        # or failed extraction are high-priority deficiencies. A signature/seal label
        # alone only asks for human visual inspection and must not auto-fail a genuine file.
        high_priority_findings = [
            finding for finding in text_findings
            if finding.get("severity") == "High review priority"
            or finding.get("type") == "Unreadable Document"
        ]
        needs_review = bool(matching_document or text_findings or processing_error)
        hard_deficiency = bool(matching_document or processing_error or high_priority_findings)
        document = UploadedDocument(
            application_id=application_id,
            requirement_id=requirement_id,
            file_name=filename,
            file_path=file_path,
            sha256=file_hash,
            extracted_text=extracted_text,
            upload_status=("Deficient" if hard_deficiency else
                           "Uploaded — Manual Review Recommended" if needs_review else "Uploaded"),
            remarks=("Automated screening raised a review flag. Officer verification is required; this is not a fraud determination."
                     if needs_review else None)
        )
        db.session.add(document)
        db.session.flush()

        flagged_reasons = []
        deficiency_reasons = []
        if matching_document:
            reason = (f"SHA-256 content hash matches document {matching_document.id} "
                      f"({matching_document.file_name}) in application {matching_document.application_id}. "
                      "Human review is required; identical content alone does not establish fraud.")
            db.session.add(DocumentIntegrityReview(
                application_id=application_id,
                document_id=document.id,
                matching_document_id=matching_document.id,
                flag_category="Exact Duplicate",
                reason=reason,
                status="Flagged — Pending Review"
            ))
            flagged_reasons.append("Exact duplicate file detected")
            deficiency_reasons.append("Exact duplicate file detected")
        else:
            # Advisory near-duplicate screening based on normalized extracted text.
            possible_match = None
            best_score = 0.0
            if extracted_text and len(extracted_text.strip()) >= 80:
                candidates = UploadedDocument.query.filter(
                    UploadedDocument.id != document.id,
                    UploadedDocument.extracted_text.isnot(None)
                ).order_by(UploadedDocument.id.desc()).limit(500).all()
                for candidate in candidates:
                    score = similarity_ratio(extracted_text, candidate.extracted_text or "")
                    if score > best_score:
                        best_score, possible_match = score, candidate
            from models import RegulatoryRule
            threshold_rule = RegulatoryRule.query.filter_by(rule_key="duplicate_text_similarity").first()
            try:
                similarity_threshold = max(0.50, min(0.99, float(threshold_rule.value))) if threshold_rule else 0.88
            except (TypeError, ValueError):
                similarity_threshold = 0.88
            if possible_match and best_score >= similarity_threshold:
                db.session.add(DocumentIntegrityReview(
                    application_id=application_id,
                    document_id=document.id,
                    matching_document_id=possible_match.id,
                    flag_category="Likely Duplicate",
                    reason=(f"Normalized extracted text similarity is {best_score:.0%} (configured threshold {similarity_threshold:.0%}) against document {possible_match.id} "
                            f"({possible_match.file_name}) in application {possible_match.application_id}. "
                            "This is an automated estimate and requires human review; it does not establish malpractice."),
                    status="Flagged — Pending Review"
                ))
                flagged_reasons.append(f"Potential text duplicate ({best_score:.0%} similarity)")
                deficiency_reasons.append(f"Potential text duplicate ({best_score:.0%} similarity)")
                document.upload_status = "Deficient"
                document.remarks = "Potential near-duplicate text detected; officer review is required."

        for finding in text_findings:
            category = finding.get("type", "Document Content Warning")
            reason = finding.get("evidence", "Text-based document check requires officer review.")
            db.session.add(DocumentIntegrityReview(
                application_id=application_id,
                document_id=document.id,
                flag_category=category,
                reason=reason + " Automated text screening is advisory and cannot prove forgery.",
                status="Flagged — Pending Review"
            ))
            flagged_reasons.append(f"{category}: {reason}")
            if finding.get("severity") == "High review priority" or category == "Unreadable Document":
                deficiency_reasons.append(f"{category}: {reason}")

        if processing_error and not any(f.get("type") == "Unreadable Document" for f in text_findings):
            reason = "Automated text extraction failed. The document has not been verified; manual review is required."
            db.session.add(DocumentIntegrityReview(
                application_id=application_id,
                document_id=document.id,
                flag_category="Processing Failure",
                reason=reason,
                status="Flagged — Pending Review"
            ))
            flagged_reasons.append(reason)
            deficiency_reasons.append(reason)

        if deficiency_reasons:
            # Move the application to Deficient only for concrete screening flags.
            # Visual-only checks remain in the review queue until the officer decides.
            if application.status != "Rejected":
                application.status = "Deficient"
                application.current_stage = "Deficiency Raised"
                application.remarks = (
                    "Automated document screening requires manual review: "
                    + "; ".join(deficiency_reasons)[:1800]
                )

        db.session.add(AuditLog(
            application_id=application_id,
            action="Document uploaded",
            performed_by=g.current_user.email,
            details=f"Uploaded {requirement.document_name}"
        ))

        db.session.commit()

    except Exception:
        db.session.rollback()
        if os.path.exists(file_path):
            os.remove(file_path)
        app.logger.exception("Document upload failed")
        return {"error": "Document upload failed"}, 500

    next_requirement = DocumentRequirement.query.filter(
        DocumentRequirement.application_type == application.application_type,
        DocumentRequirement.is_mandatory.is_(True),
        DocumentRequirement.sequence_order > requirement.sequence_order
    ).order_by(DocumentRequirement.sequence_order.asc()).first()

    return {
        "message": "Document uploaded and screened; any flags require officer review",
        "document_id": document.id,
        "document_name": requirement.document_name,
        "upload_status": document.upload_status,
        "screening_flagged": bool(flagged_reasons),
        "manual_review_required": bool(flagged_reasons),
        "next_required_document": (
            next_requirement.document_name if next_requirement else None
        )
    }, 201

@app.route("/api/applications/<int:application_id>/documents/<int:document_id>/replace", methods=["POST"])
def replace_deficient_document(application_id, document_id):
    """Store a corrected version as a new immutable record and keep prior evidence for audit."""
    from datetime import datetime
    from werkzeug.utils import secure_filename
    from models import Application, UploadedDocument, DocumentRequirement, DocumentIntegrityReview, AuditLog
    application = db.session.get(Application, application_id)
    original = UploadedDocument.query.filter_by(id=document_id, application_id=application_id).first()
    if not application or not original:
        return {"error": "Application or document not found"}, 404
    if original.upload_status not in {"Deficient", "Rejected"}:
        return {"error": "Only deficient or rejected documents can be replaced"}, 409
    file = request.files.get("file")
    requirement_id = request.form.get("requirement_id", type=int)
    if not file or not file.filename or requirement_id != original.requirement_id:
        return {"error": "Select a replacement file for the same document requirement"}, 400
    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return {"error": "Only PDF, JPG and PNG files are supported"}, 400
    file.stream.seek(0); header=file.stream.read(16); file.stream.seek(0)
    from document_integrity import file_signature_matches, sha256_stream, extract_document_text, screen_document_text, detect_requirement_type_mismatch, similarity_ratio
    if not file_signature_matches(ext, header):
        return {"error": "File contents do not match the extension"}, 400
    requirement=db.session.get(DocumentRequirement, requirement_id)
    if not requirement or requirement.application_type != application.application_type:
        return {"error": "Document requirement does not match the application type"}, 400
    file_hash=sha256_stream(file.stream)
    exact_match=UploadedDocument.query.filter(UploadedDocument.sha256==file_hash, UploadedDocument.id!=original.id).first()
    saved_name=secure_filename(f"app_{application_id}_req_{requirement_id}_replacement_{int(datetime.utcnow().timestamp())}_{filename}")
    file_path=os.path.abspath(os.path.join(UPLOAD_FOLDER, saved_name))
    if os.path.commonpath([file_path, os.path.abspath(UPLOAD_FOLDER)]) != os.path.abspath(UPLOAD_FOLDER):
        return {"error": "Invalid file path"}, 400
    try:
        file.save(file_path)
        try:
            extracted=extract_document_text(file_path)
        except Exception as exc:
            app.logger.warning("Replacement text extraction failed: %s", str(exc)[:200]); extracted=""
        findings=screen_document_text(extracted or "")
        findings.extend(detect_requirement_type_mismatch(extracted or "", requirement.document_name))
        if not extracted:
            findings.append({"type":"Unreadable Document","severity":"High review priority","evidence":"No readable text was extracted from the replacement. OCR/manual review is required."})
        new_doc=UploadedDocument(application_id=application_id, requirement_id=requirement_id, file_name=filename, file_path=file_path, sha256=file_hash, extracted_text=extracted or None, upload_status="Uploaded", remarks=f"Replacement for document {original.id}; automated checks are advisory.")
        db.session.add(new_doc); db.session.flush()
        original.upload_status="Superseded — Replaced"
        original.remarks=f"Replaced by document record {new_doc.id}; original retained for audit."
        # Keep old flag records but close them as replaced, not erased.
        old_flags=DocumentIntegrityReview.query.filter_by(application_id=application_id, document_id=original.id).all()
        for flag in old_flags:
            if flag.status in {"Flagged — Pending Review", "Under Investigation", "Clarification Requested", "Duplicate Confirmed", "Suspected Alteration — Escalated", "Referred for Further Verification"}:
                flag.status="Closed — Superseded by replacement"
                flag.officer_remarks=f"Replacement document record {new_doc.id} uploaded; inspect the new record separately."
                flag.reviewed_at=datetime.utcnow()
        new_findings=list(findings)
        match_target_id = None
        candidate = None
        if exact_match:
            match_target_id = exact_match.id
            new_findings.append({"type":"Exact Duplicate","severity":"High review priority","evidence":f"SHA-256 matches existing document {exact_match.id} ({exact_match.file_name}); inspect both copies."})
        else:
            candidate=None; score=0.0
            if extracted and len(extracted.strip())>=80:
                for other in UploadedDocument.query.filter(UploadedDocument.id.notin_([original.id,new_doc.id]),UploadedDocument.extracted_text.isnot(None)).order_by(UploadedDocument.id.desc()).limit(500).all():
                    r=similarity_ratio(extracted,other.extracted_text or "")
                    if r>score: score,candidate=r,other
            from models import RegulatoryRule
            rule=RegulatoryRule.query.filter_by(rule_key="duplicate_text_similarity").first()
            try: threshold=max(0.50,min(0.99,float(rule.value))) if rule else 0.88
            except (TypeError,ValueError): threshold=0.88
            if candidate and score>=threshold:
                match_target_id = candidate.id
                new_findings.append({"type":"Likely Duplicate","severity":"High review priority","evidence":f"Text similarity {score:.0%} vs document {candidate.id}; threshold {threshold:.0%}."})
        for finding in new_findings:
            category = finding.get("type", "Document Content Warning")
            matching_id = match_target_id if category in {"Exact Duplicate", "Likely Duplicate"} else None
            db.session.add(DocumentIntegrityReview(application_id=application_id,document_id=new_doc.id,matching_document_id=matching_id,flag_category=category,reason=finding.get("evidence","Manual review required"),status="Flagged — Pending Review"))
        has_high=any(f.get("severity")=="High review priority" for f in new_findings)
        if has_high:
            new_doc.upload_status="Deficient"
            new_doc.remarks="Replacement flagged by automatic screening; officer review is required. This is not a fraud determination."
            application.status="Deficient"; application.current_stage="Deficiency Raised"; application.remarks="Corrected document was uploaded but still requires officer review."
        elif new_findings:
            new_doc.upload_status="Uploaded — Manual Review Recommended"
        else:
            application.status="Deficient"; application.current_stage="Deficiency Raised"
            application.remarks=f"Replacement document {new_doc.id} uploaded. Submit the corrected application for review."
        db.session.add(AuditLog(application_id=application_id,action="Deficient document replaced",performed_by=g.current_user.email,details=f"Document {original.id} replaced by {new_doc.id}; filename {filename}; screening flags {len(new_findings)}"))
        db.session.commit()
    except Exception:
        db.session.rollback()
        try:
            if os.path.isfile(file_path): os.remove(file_path)
        except OSError: pass
        app.logger.exception("Deficient document replacement failed")
        return {"error":"Could not save replacement document"},500
    return {"message":"Replacement document uploaded and screened","old_document_id":original.id,"document_id":new_doc.id,"upload_status":new_doc.upload_status,"manual_review_required":bool(new_findings)},201


@app.route(
    "/api/applications/<int:application_id>/documents",
    methods=["GET"]
)
def get_uploaded_documents(application_id):
    from models import Application, UploadedDocument, DocumentRequirement

    application = db.session.get(Application, application_id)
    if not application:
        return {"error": "Application not found"}, 404

    documents = UploadedDocument.query.filter_by(
        application_id=application_id
    ).order_by(UploadedDocument.id.asc()).all()

    result = []
    for document in documents:
        requirement = db.session.get(
            DocumentRequirement, document.requirement_id
        )
        result.append({
            "id": document.id,
            "requirement_id": document.requirement_id,
            "document_name": (
                requirement.document_name if requirement else "Unknown"
            ),
            "file_name": document.file_name,
            "file_size": (os.path.getsize(document.file_path) if document.file_path and os.path.isfile(document.file_path) else 0),
            "upload_status": document.upload_status,
            "uploaded_at": (
                document.uploaded_at.isoformat()
                if document.uploaded_at else None
            ),
            "verified_by": document.verified_by,
            "verified_at": (
                document.verified_at.isoformat()
                if document.verified_at else None
            ),
            "issue_date": document.issue_date.isoformat() if document.issue_date else None,
            "expiry_date": document.expiry_date.isoformat() if document.expiry_date else None,
            "proposed_issue_date": document.proposed_issue_date.isoformat() if document.proposed_issue_date else None,
            "proposed_expiry_date": document.proposed_expiry_date.isoformat() if document.proposed_expiry_date else None,
            "renewal_status": document.renewal_status,
            "sha256_prefix": document.sha256[:12] if document.sha256 else None,
            "remarks": document.remarks
        })

    return {"application_id": application_id, "documents": result}, 200


@app.route(
    "/api/applications/<int:application_id>/documents/<int:document_id>/file",
    methods=["GET"]
)
def view_uploaded_document_file(application_id, document_id):
    """Serve an uploaded document to its owning institution or an authenticated officer."""
    from models import UploadedDocument
    document = UploadedDocument.query.filter_by(
        id=document_id, application_id=application_id
    ).first()
    if not document:
        return {"error": "Uploaded document not found"}, 404
    file_path = document.file_path or ""
    if file_path and not os.path.isabs(file_path):
        file_path = os.path.join(app.root_path, file_path)
    file_path = os.path.abspath(file_path)
    uploads_root = os.path.abspath(UPLOAD_FOLDER)
    if not file_path or os.path.commonpath([file_path, uploads_root]) != uploads_root:
        return {"error": "Stored file path is invalid"}, 404
    if not os.path.isfile(file_path):
        return {"error": "Stored document file is unavailable"}, 404
    response = send_file(file_path, as_attachment=False, download_name=document.file_name)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@app.route(
    "/api/applications/<int:application_id>/documents/<int:document_id>/verify",
    methods=["PUT"]
)
def verify_uploaded_document(application_id, document_id):
    from models import Application, UploadedDocument, AuditLog
    from datetime import datetime

    data = request.get_json(silent=True) or {}

    decision = data.get("decision")
    # Actor identity always comes from the authenticated server session, never request JSON.
    performed_by = g.current_user.email
    remarks = str(data.get("remarks", "")).strip()

    if decision not in ["Verified", "Deficient", "Rejected"]:
        return {
            "error": "decision must be Verified, Deficient or Rejected"
        }, 400

    if decision in {"Rejected", "Deficient"} and not remarks:
        return {
            "error": "Remarks are required when marking a document deficient or rejecting it"
        }, 400

    application = db.session.get(Application, application_id)
    if not application:
        return {"error": "Application not found"}, 404

    document = db.session.get(UploadedDocument, document_id)
    if not document or document.application_id != application_id:
        return {"error": "Uploaded document not found"}, 404

    old_status = document.upload_status
    now = datetime.utcnow()

    document.upload_status = decision
    document.verified_by = performed_by
    document.verified_at = now
    document.remarks = str(remarks).strip() or None
    if decision in {"Deficient", "Rejected"}:
        application.status = "Deficient"
        application.current_stage = "Deficiency Raised"
        application.remarks = f"Document {document.file_name} requires correction: {document.remarks}"
    elif decision == "Verified" and application.status == "Draft":
        application.status = "In Review"
        application.current_stage = "Document Verification"

    db.session.add(AuditLog(
        application_id=application_id,
        action=f"Document {decision}",
        performed_by=performed_by,
        details=(
            f"Document ID {document.id}: "
            f"{old_status} -> {decision}. "
            f"Remarks: {document.remarks or 'None'}"
        )
    ))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Document verification failed")
        return {"error": "Could not save verification decision"}, 500

    return {
        "message": f"Document {decision.lower()} successfully",
        "application_id": application_id,
        "document_id": document.id,
        "upload_status": document.upload_status,
        "verified_by": document.verified_by,
        "verified_at": document.verified_at.isoformat(),
        "remarks": document.remarks
    }, 200


@app.route(
    "/api/applications/<int:application_id>/documents/<int:document_id>/renew/verify",
    methods=["PUT"]
)
def verify_document_renewal(application_id, document_id):
    from models import Application, UploadedDocument, AuditLog

    data = request.get_json(silent=True) or {}

    decision = data.get("decision")
    performed_by = g.current_user.email
    remarks = str(data.get("remarks", "")).strip()

    if decision not in ["Verified", "Rejected"]:
        return {"error": "decision must be Verified or Rejected"}, 400

    if decision == "Rejected" and not remarks:
        return {
            "error": "remarks are required when rejecting a renewal"
        }, 400

    application = db.session.get(Application, application_id)
    if not application:
        return {"error": "Application not found"}, 404

    document = UploadedDocument.query.filter_by(
        id=document_id,
        application_id=application_id
    ).first()

    if not document:
        return {
            "error": "Document not found for this application"
        }, 404

    if document.renewal_status != "Submitted":
        return {
            "error": "Only submitted renewals can be verified"
        }, 400

    if decision == "Verified":
        if document.proposed_expiry_date is None:
            return {
                "error": "Proposed expiry date is missing; renewal cannot be verified"
            }, 400

        # Apply the proposed dates and, when present, the verified replacement file.
        document.expiry_date = document.proposed_expiry_date
        if document.proposed_issue_date is not None:
            document.issue_date = document.proposed_issue_date
        if document.renewed_document_id:
            replacement = db.session.get(UploadedDocument, document.renewed_document_id)
            if replacement:
                document.file_name = replacement.file_name
                document.file_path = replacement.file_path
                document.sha256 = replacement.sha256
                document.extracted_text = replacement.extracted_text
                replacement.upload_status = "Archived — Renewal Source"
                replacement.remarks = f"Promoted as verified renewal for document {document.id}."
                document.remarks = f"Renewal verified by {g.current_user.email}."

    elif decision == "Rejected" and document.renewed_document_id:
        replacement = db.session.get(UploadedDocument, document.renewed_document_id)
        if replacement:
            replacement.upload_status = "Rejected"
            replacement.remarks = remarks or "Renewal rejected by officer."

    # Clear pending dates after either verification or rejection.
    document.proposed_issue_date = None
    document.proposed_expiry_date = None
    document.renewal_status = decision

    if remarks:
        document.remarks = remarks

    db.session.add(AuditLog(
        application_id=application_id,
        action=f"Document renewal {decision}",
        performed_by=performed_by,
        details=(
            f"Document ID {document.id}; "
            f"decision: {decision}; "
            f"remarks: {remarks or 'None'}"
        )
    ))

    db.session.commit()

    return {
        "message": f"Document renewal {decision.lower()}",
        "document_id": document.id,
        "renewal_status": document.renewal_status
    }, 200


@app.route("/api/reports/summary", methods=["GET"])
def get_reports_summary():
    from datetime import datetime, date, timedelta
    if g.current_user.role not in {"officer", "authority"}:
        return {"error": "Officer or authority role required"}, 403
    from models import (
        Application,
        UploadedDocument,
        EVCRecord,
        Undertaking
    )

    now = datetime.utcnow()
    today = date.today()
    from models import RegulatoryRule
    expiry_rule = RegulatoryRule.query.filter_by(rule_key="expiry_warning_days").first()
    try:
        expiry_warning_days = max(1, min(365, int(expiry_rule.value))) if expiry_rule else 30
    except (TypeError, ValueError):
        expiry_warning_days = 30
    expiry_limit = today + timedelta(days=expiry_warning_days)

    # Reports are scoped to the role's permitted case set.
    app_query = Application.query
    if g.current_user.role == "authority":
        app_query = app_query.filter(Application.current_stage.in_(["Decision Pending", "Approved", "Rejected"]))
    applications = app_query.all()
    visible_ids = [a.id for a in applications]

    applications_by_status = {}
    applications_by_stage = {}

    for application in applications:
        status = application.status or "Unknown"
        stage = application.current_stage or "Unknown"

        applications_by_status[status] = (
            applications_by_status.get(status, 0) + 1
        )
        applications_by_stage[stage] = (
            applications_by_stage.get(stage, 0) + 1
        )

    active_applications = [
        a for a in applications
        if a.status not in ["Approved", "Rejected"]
    ]

    overdue_applications = [
        a for a in active_applications
        if a.deadline is not None and a.deadline < now
        and a.current_stage != "Completed"
    ]
    # 2. Document validity
    documents = UploadedDocument.query.filter(UploadedDocument.application_id.in_(visible_ids)).all() if visible_ids else []

    expired_documents = [
        d for d in documents
        if d.expiry_date is not None and d.expiry_date < today
    ]

    expiring_soon_documents = [
        d for d in documents
        if d.expiry_date is not None
        and today <= d.expiry_date <= expiry_limit
    ]

    renewals_pending = [
        d for d in documents
        if d.renewal_status == "Submitted"
    ]

    # 3. EVC monitoring
    evc_records = EVCRecord.query.filter(EVCRecord.application_id.in_(visible_ids)).all() if visible_ids else []

    evc_by_status = {}
    for evc in evc_records:
        status = evc.status or "Unknown"
        evc_by_status[status] = evc_by_status.get(status, 0) + 1

    evc_overdue = [
        e for e in evc_records
        if e.scheduled_date is not None
        and e.scheduled_date < now
        and e.status not in ["Completed", "Cancelled"]
    ]

    # 4. Undertaking compliance
    undertakings = Undertaking.query.filter(Undertaking.application_id.in_(visible_ids)).all() if visible_ids else []

    undertakings_by_status = {}
    for undertaking in undertakings:
        status = undertaking.status or "Unknown"
        undertakings_by_status[status] = (
            undertakings_by_status.get(status, 0) + 1
        )

    overdue_undertakings = [
        u for u in undertakings
        if u.due_date is not None
        and u.due_date < now
        and u.status != "Verified"
    ]

    # 5. Officer workload
    officer_workload = {}
    regional_workload = {}
    institution_workload = {}
    committee_workload = {}
    aging_buckets = {"0-7 days": 0, "8-14 days": 0, "15-30 days": 0, "Over 30 days": 0}
    for application in active_applications:
        age_days = max(0, (now - application.submission_date).days) if application.submission_date else 0
        if age_days <= 7: aging_buckets["0-7 days"] += 1
        elif age_days <= 14: aging_buckets["8-14 days"] += 1
        elif age_days <= 30: aging_buckets["15-30 days"] += 1
        else: aging_buckets["Over 30 days"] += 1

    for application in active_applications:
        officer = application.assigned_officer or "Unassigned"
        officer_workload[officer] = officer_workload.get(officer, 0) + 1
        region = getattr(application, "state", None) or "Unspecified"
        regional_workload[region] = regional_workload.get(region, 0) + 1
        institution_workload[application.institution_name] = institution_workload.get(application.institution_name, 0) + 1

    status_by_region = {}
    status_by_institution = {}
    for application in applications:
        region = getattr(application, "state", None) or "Unspecified"
        institution = application.institution_name or "Unspecified institution"
        status_by_region.setdefault(region, {})[application.status or "Unknown"] = status_by_region.setdefault(region, {}).get(application.status or "Unknown", 0) + 1
        status_by_institution.setdefault(institution, {})[application.status or "Unknown"] = status_by_institution.setdefault(institution, {}).get(application.status or "Unknown", 0) + 1

    for evc_record in evc_records:
        committee = evc_record.committee_name or evc_record.assigned_officer or "Unassigned committee"
        committee_workload[committee] = committee_workload.get(committee, 0) + 1

    return {
        "generated_at": now.isoformat(),

        "applications": {
            "total": len(applications),
            "active": len(active_applications),
            "overdue": len(overdue_applications),
            "by_status": applications_by_status,
            "by_stage": applications_by_stage,
            "aging_buckets": aging_buckets,
            "stage_bottlenecks": {stage: count for stage, count in applications_by_stage.items() if count > 0},
            "status_by_region": status_by_region,
            "status_by_institution": status_by_institution
        },

        "documents": {
            "total": len(documents),
            "expired": len(expired_documents),
            "expiring_within_30_days": len(expiring_soon_documents),
            "expiring_within_warning_window": len(expiring_soon_documents),
            "expiry_warning_days": expiry_warning_days,
            "renewals_pending_verification": len(renewals_pending),
            "by_validity": {"Expired": len(expired_documents), "Expiring soon": len(expiring_soon_documents), "Renewal pending verification": len(renewals_pending)}
        },

        "evc": {
            "total": len(evc_records),
            "by_status": evc_by_status,
            "overdue": len(evc_overdue)
        },

        "undertakings": {
            "total": len(undertakings),
            "by_status": undertakings_by_status,
            "overdue": len(overdue_undertakings)
        },

        "officer_workload": officer_workload,
        "regional_workload": regional_workload,
        "institution_workload": institution_workload,
        "committee_workload": committee_workload
    }, 200


@app.route(
    "/api/applications/<int:application_id>/decision",
    methods=["PUT"]
)
def decide_application(application_id):
    from models import Application, AuditLog
    from datetime import datetime

    data = request.get_json(silent=True) or {}

    decision = data.get("decision")
    performed_by = g.current_user.email
    remarks = str(data.get("remarks", "")).strip()

    if decision not in ["Approved", "Rejected"]:
        return {
            "error": "decision must be Approved or Rejected"
        }, 400

    if not performed_by:
        return {"error": "performed_by is required"}, 400

    if not remarks:
        return {"error": "Decision remarks are required for both approval and rejection"}, 400

    application = db.session.get(Application, application_id)

    if not application:
        return {"error": "Application not found"}, 404

    if application.current_stage != "Decision Pending":
        return {
            "error": "Application must be at Decision Pending",
            "current_stage": application.current_stage
        }, 409

    if application.status in ["Approved", "Rejected"]:
        return {"error": "Application already has a final decision"}, 409

    old_status = application.status

    application.status = decision
    application.current_stage = decision
    application.remarks = remarks or None

    db.session.add(AuditLog(
        application_id=application.id,
        action=f"Application {decision}",
        performed_by=performed_by,
        details=(
            f"Final decision: {decision}. "
            f"Previous status: {old_status}. "
            f"Remarks: {remarks or 'None'}"
        )
    ))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Application decision failed")
        return {"error": "Could not save application decision"}, 500

    return {
        "message": f"Application {decision.lower()} successfully",
        "application_id": application.id,
        "decision": decision,
        "current_stage": application.current_stage,
        "status": application.status,
        "remarks": application.remarks
    }, 200



# ---------- Persistent alerts, case communications, summaries and demo rule settings ----------

def _smtp_settings():
    host = os.environ.get("SMTP_HOST", "").strip()
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    sender = os.environ.get("SMTP_FROM", username).strip()
    if not (host and sender):
        return None
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError:
        port = 587
    return host, port, username, password, sender


def _send_email(to_address, subject, body):
    """Send only when SMTP is explicitly configured. Returns a human-readable status."""
    from email.message import EmailMessage
    import smtplib
    cfg = _smtp_settings()
    if not cfg:
        return False, "SMTP is not configured; saved as in-app communication only."
    host, port, username, password, sender = cfg
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)
    try:
        if os.environ.get("SMTP_USE_SSL", "0") == "1":
            with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                if username: server.login(username, password)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.ehlo()
                if os.environ.get("SMTP_STARTTLS", "1") == "1":
                    server.starttls(); server.ehlo()
                if username: server.login(username, password)
                server.send_message(message)
        return True, "Email sent"
    except Exception as exc:
        app.logger.warning("Configured email delivery failed: %s", str(exc)[:300])
        return False, "Email delivery failed; see server log (no credentials exposed)."


def _build_persistent_alerts():
    """Refresh database-backed deadline/deficiency alerts and escalation levels."""
    from datetime import datetime, timedelta, date
    from models import Application, UploadedDocument, EVCRecord, Undertaking, PersistentAlert, RegulatoryRule, User, AuditLog
    now = datetime.utcnow()
    today = date.today()
    entries = []
    expiry_rule = RegulatoryRule.query.filter_by(rule_key="expiry_warning_days").first()
    try:
        expiry_days = max(1, min(365, int(expiry_rule.value))) if expiry_rule else 30
    except (TypeError, ValueError):
        expiry_days = 30

    for application in Application.query.all():
        if application.status == "Deficient" or application.current_stage == "Deficiency Raised":
            entries.append((f"deficiency:{application.id}", application.id, "Correction Required", f"Correction required: {application.institution_name}", application.remarks or "Officer review requires corrected or supporting documents.", application.deadline))
        if application.deadline and application.status not in {"Approved", "Rejected"} and application.current_stage != "Completed":
            days = (application.deadline.date() - today).days
            if days < 0:
                entries.append((f"deadline:{application.id}:{application.deadline.isoformat()}", application.id, "Overdue Deadline", f"Overdue: {application.institution_name}", f"The application deadline passed {-days} day(s) ago at stage {application.current_stage}.", application.deadline))
            elif days <= 7:
                entries.append((f"deadline:{application.id}:{application.deadline.isoformat()}", application.id, "Upcoming Deadline", f"Upcoming deadline: {application.institution_name}", f"The application is due in {days} day(s) at stage {application.current_stage}.", application.deadline))

    for doc in UploadedDocument.query.filter(UploadedDocument.expiry_date.isnot(None)).all():
        if not doc.expiry_date: continue
        days = (doc.expiry_date - today).days
        if days <= expiry_days:
            label = "Expired Document" if days < 0 else "Document Expiry"
            entries.append((f"expiry:{doc.id}:{doc.expiry_date.isoformat()}", doc.application_id, label, f"{label}: {doc.file_name}", f"Document expires on {doc.expiry_date.isoformat()} ({'expired' if days < 0 else f'{days} day(s) remaining'}); renewal status: {doc.renewal_status}.", datetime.combine(doc.expiry_date, datetime.min.time())))

    for evc in EVCRecord.query.filter(EVCRecord.scheduled_date.isnot(None), EVCRecord.status.notin_(["Completed", "Cancelled"])).all():
        if evc.scheduled_date <= now + timedelta(days=7):
            days = (evc.scheduled_date.date() - today).days
            kind = "Overdue EVC" if days < 0 else "Upcoming EVC"
            entries.append((f"evc:{evc.id}:{evc.scheduled_date.isoformat()}", evc.application_id, kind, f"{kind}: {evc.committee_name or 'Committee'}", f"EVC status {evc.status}; scheduled {evc.scheduled_date.isoformat()}.", evc.scheduled_date))

    for undertaking in Undertaking.query.filter(Undertaking.status.notin_(["Verified", "Rejected"])).all():
        if undertaking.due_date <= now + timedelta(days=7):
            days = (undertaking.due_date.date() - today).days
            kind = "Overdue Compliance" if days < 0 else "Upcoming Compliance"
            entries.append((f"undertaking:{undertaking.id}:{undertaking.due_date.isoformat()}", undertaking.application_id, kind, f"{kind}: {undertaking.title}", f"Compliance condition due {undertaking.due_date.isoformat()} with current status {undertaking.status}.", undertaking.due_date))

    authority_emails = [u.email for u in User.query.filter_by(role="authority", active=True).all()]
    active_keys = {entry[0] for entry in entries}
    for key, app_id, kind, title, details, due in entries:
        alert = PersistentAlert.query.filter_by(alert_key=key).first()
        if alert is None:
            alert = PersistentAlert(alert_key=key, application_id=app_id, alert_type=kind, title=title, details=details, due_at=due, status="Open", escalation_level=0)
            db.session.add(alert)
            db.session.flush()
        else:
            # Refresh alert details without undoing a user's explicit acknowledgement or closure.
            alert.application_id = app_id; alert.alert_type = kind; alert.title = title; alert.details = details; alert.due_at = due; alert.updated_at = now

        overdue_days = max(0, (today - due.date()).days) if due else 0
        # These are adjustable demonstration thresholds, not official escalation rules.
        level1_rule = RegulatoryRule.query.filter_by(rule_key="escalation_level_1_days").first()
        level2_rule = RegulatoryRule.query.filter_by(rule_key="escalation_level_2_days").first()
        try:
            level1_days = max(1, min(365, int(level1_rule.value))) if level1_rule else 7
        except (TypeError, ValueError):
            level1_days = 7
        try:
            level2_days = max(level1_days + 1, min(730, int(level2_rule.value))) if level2_rule else max(14, level1_days + 1)
        except (TypeError, ValueError):
            level2_days = max(14, level1_days + 1)
        computed_level = 2 if overdue_days >= level2_days else 1 if overdue_days >= level1_days else 0
        if computed_level > (alert.escalation_level or 0):
            previous_level = alert.escalation_level or 0
            alert.escalation_level = computed_level
            alert.escalated_to = ";".join(authority_emails) if authority_emails else None
            alert.status = "Open" if alert.status == "Acknowledged" else alert.status
            if app_id:
                db.session.add(AuditLog(application_id=app_id, action="Alert escalated", performed_by="system", details=f"Alert {alert.id}: escalation level {previous_level} -> {computed_level}; assigned authorities: {alert.escalated_to or 'No authority account configured'}"))
        elif (alert.escalation_level or 0) > 0 and authority_emails and not alert.escalated_to:
            alert.escalated_to = ";".join(authority_emails)

    db.session.commit()
    for old in PersistentAlert.query.filter(PersistentAlert.status.in_(["Open", "Acknowledged"])).all():
        if old.alert_type in {"Correction Required", "Overdue Deadline", "Upcoming Deadline", "Expired Document", "Document Expiry", "Overdue EVC", "Upcoming EVC", "Overdue Compliance", "Upcoming Compliance"} and old.alert_key not in active_keys:
            old.status = "Closed"; old.closed_by = "system"; old.closed_at = now; old.updated_at = now
    db.session.commit()

def _serialize_alert(a):
    return {"id": a.id, "application_id": a.application_id, "type": a.alert_type, "title": a.title, "details": a.details, "due_at": a.due_at.isoformat() if a.due_at else None, "status": a.status, "created_at": a.created_at.isoformat() if a.created_at else None, "acknowledged_by": a.acknowledged_by, "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None, "closed_by": a.closed_by, "closed_at": a.closed_at.isoformat() if a.closed_at else None, "escalation_level": a.escalation_level or 0, "escalated_to": [v for v in (a.escalated_to or "").split(";") if v]}


@app.route("/api/alerts/records", methods=["GET"])
def persistent_alerts():
    from models import PersistentAlert
    _build_persistent_alerts()
    query = PersistentAlert.query
    if g.current_user.role == "institution":
        owned_ids = [a.id for a in __import__("models").Application.query.filter_by(institution_user_id=g.current_user.id).all()]
        query = query.filter(PersistentAlert.application_id.in_(owned_ids) if owned_ids else PersistentAlert.id == -1)
    elif g.current_user.role == "committee":
        from models import EVCRecord
        assigned_ids = [row[0] for row in db.session.query(EVCRecord.application_id).filter_by(assigned_officer=g.current_user.email).distinct().all()]
        query = query.filter(PersistentAlert.application_id.in_(assigned_ids) if assigned_ids else PersistentAlert.id == -1)
    elif g.current_user.role == "authority":
        from models import Application, or_
        decision_ids = [a.id for a in Application.query.filter(Application.current_stage.in_(["Decision Pending", "Approved", "Rejected"])).all()]
        query = query.filter(or_(PersistentAlert.application_id.in_(decision_ids) if decision_ids else PersistentAlert.id == -1, PersistentAlert.escalation_level >= 1))
    rows = query.order_by(PersistentAlert.status.asc(), PersistentAlert.due_at.asc()).all()
    return {"alerts": [_serialize_alert(a) for a in rows], "open_count": sum(a.status == "Open" for a in rows), "acknowledged_count": sum(a.status == "Acknowledged" for a in rows)}, 200


@app.route("/api/alerts/records/<int:alert_id>", methods=["PUT"])
def update_persistent_alert(alert_id):
    from datetime import datetime
    from models import PersistentAlert, Application, AuditLog
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    if action not in {"acknowledge", "close", "reopen", "escalate"}:
        return {"error": "action must be acknowledge, close, reopen or escalate"}, 400
    alert = db.session.get(PersistentAlert, alert_id)
    if not alert:
        return {"error": "Alert not found"}, 404
    application = db.session.get(Application, alert.application_id) if alert.application_id else None
    if g.current_user.role == "institution":
        if action != "acknowledge": return {"error": "Institutions may acknowledge their own alerts only."}, 403
        if not application or application.institution_user_id != g.current_user.id: return {"error": "Alert not found"}, 404
    elif g.current_user.role == "committee":
        if action != "acknowledge": return {"error": "Committee accounts may acknowledge alerts only."}, 403
        from models import EVCRecord
        if not application or not EVCRecord.query.filter_by(application_id=application.id, assigned_officer=g.current_user.email).first(): return {"error": "Alert not found"}, 404
    elif g.current_user.role == "authority":
        escalated_recipients = [v.strip().lower() for v in (alert.escalated_to or "").split(";") if v.strip()]
        is_assigned_escalation = (alert.escalation_level or 0) > 0 and g.current_user.email.lower() in escalated_recipients
        if not application or (application.current_stage not in {"Decision Pending", "Approved", "Rejected"} and not is_assigned_escalation):
            return {"error": "Alert is not assigned to the authority queue."}, 404
    now = datetime.utcnow()
    previous = alert.status
    if action == "acknowledge":
        alert.status = "Acknowledged"; alert.acknowledged_by = g.current_user.email; alert.acknowledged_at = now
    elif action == "escalate":
        if g.current_user.role not in {"officer", "authority"}: return {"error": "Officer or authority role required to escalate alerts."}, 403
        from models import User
        authority_emails = [u.email for u in User.query.filter_by(role="authority", active=True).all()]
        if not authority_emails: return {"error": "Create at least one authority account before escalating: python create_user.py authority"}, 409
        alert.escalation_level = min(3, (alert.escalation_level or 0) + 1)
        alert.escalated_to = ";".join(authority_emails)
        if alert.status == "Closed": alert.status = "Open"; alert.closed_by = None; alert.closed_at = None
    elif action == "close":
        if g.current_user.role not in {"officer", "authority"}: return {"error": "Officer or authority role required"}, 403
        alert.status = "Closed"; alert.closed_by = g.current_user.email; alert.closed_at = now
    else:
        if g.current_user.role not in {"officer", "authority"}: return {"error": "Officer or authority role required"}, 403
        alert.status = "Open"; alert.closed_by = None; alert.closed_at = None
    if alert.application_id:
        detail = f"Alert {alert.id}: {previous} -> {alert.status}; {alert.title}; escalation level {alert.escalation_level or 0}; recipients {(alert.escalated_to or '').replace(';', ', ')}"
        db.session.add(AuditLog(application_id=alert.application_id, action="Alert escalated" if action == "escalate" else f"Alert {action}d", performed_by=g.current_user.email, details=detail))
    db.session.commit()
    return {"message": "Alert updated", "alert": _serialize_alert(alert)}, 200


@app.route("/api/alerts/email-digest", methods=["POST"])
def send_alert_email_digest():
    from models import PersistentAlert, Application, User, AuditLog
    if g.current_user.role != "officer": return {"error": "Officer role required"}, 403
    _build_persistent_alerts()
    from models import RegulatoryRule
    email_rule = RegulatoryRule.query.filter_by(rule_key="email_alerts_enabled").first()
    if email_rule and email_rule.value.lower() != "true": return {"error": "Demo email alerts are disabled. Enable the email_alerts_enabled setting first."}, 400
    if not _smtp_settings(): return {"error": "Email delivery is not configured. Set SMTP_HOST, SMTP_PORT, SMTP_FROM and credentials in the local .env file first."}, 400
    alerts = PersistentAlert.query.filter(PersistentAlert.status.in_(["Open", "Acknowledged"])).all()
    by_recipient = {}
    for alert in alerts:
        application = db.session.get(Application, alert.application_id) if alert.application_id else None
        user = db.session.get(User, application.institution_user_id) if application and application.institution_user_id else None
        if user and user.email:
            by_recipient.setdefault(user.email, []).append(alert)
    sent = failed = 0
    for recipient, items in by_recipient.items():
        body = "AICTEFlow demonstration alert digest\n\n" + "\n\n".join(f"{a.title}\n{a.details or ''}\nStatus: {a.status}" for a in items)
        ok, message = _send_email(recipient, "AICTEFlow: pending application/compliance alerts", body)
        if ok:
            sent += 1
            now = datetime.utcnow()
            for a in items:
                a.last_emailed_at = now
                if a.application_id:
                    db.session.add(AuditLog(application_id=a.application_id, action="Alert email sent", performed_by=g.current_user.email, details=f"Alert {a.id} digest email sent to registered user."))
        else: failed += 1
    db.session.commit()
    return {"message": "Alert digest processed", "recipient_count": len(by_recipient), "sent": sent, "failed": failed}, 200 if failed == 0 else 207


@app.route("/api/applications/<int:application_id>/communications", methods=["GET", "POST"])
def application_communications(application_id):
    from models import Application, CaseCommunication, User, AuditLog
    from datetime import datetime
    application = db.session.get(Application, application_id)
    if not application: return {"error": "Application not found"}, 404
    if request.method == "GET":
        rows = CaseCommunication.query.filter_by(application_id=application_id).order_by(CaseCommunication.created_at.asc()).all()
        return {"communications": [{"id":m.id,"sender_email":m.sender_email,"recipient_email":m.recipient_email,"template_key":m.template_key,"subject":m.subject,"body":m.body,"delivery_status":m.delivery_status,"created_at":m.created_at.isoformat() if m.created_at else None} for m in rows]}, 200
    data = request.get_json(silent=True) or {}
    template = str(data.get("template_key", "general")).strip().lower()
    templates = {
        "deficiency_notice": "Deficiency notice", "correction_update": "Correction update",
        "approval_notice": "Approval notice", "evc_notice": "EVC notice",
        "compliance_reminder": "Compliance reminder", "general": "Case communication"
    }
    if template not in templates: return {"error": "Unsupported communication template"}, 400
    subject = str(data.get("subject", "")).strip() or templates[template]
    body = str(data.get("body", "")).strip()
    if not body: return {"error": "Communication body is required"}, 400
    owner = db.session.get(User, application.institution_user_id) if application.institution_user_id else None
    if g.current_user.role == "officer":
        recipient = owner.email if owner else None
    else:
        recipient = os.environ.get("AICTE_DEFAULT_EMAIL", "").strip() or None
    delivery = "In-app only"
    if recipient and _smtp_settings():
        ok, mail_status = _send_email(recipient, subject, body)
        delivery = "Email sent" if ok else "In-app saved; email failed"
    row = CaseCommunication(application_id=application_id, sender_email=g.current_user.email, recipient_email=recipient, template_key=template, subject=subject, body=body, delivery_status=delivery)
    db.session.add(row)
    db.session.add(AuditLog(application_id=application_id, action="Case communication created", performed_by=g.current_user.email, details=f"Template: {template}; subject: {subject}; delivery: {delivery}"))
    db.session.commit()
    return {"message": "Communication saved", "id": row.id, "delivery_status": delivery}, 201


@app.route("/api/applications/<int:application_id>/case-summary", methods=["GET"])
def application_case_summary(application_id):
    from models import Application, UploadedDocument, DocumentIntegrityReview, EVCRecord, Undertaking, AuditLog, User
    application = db.session.get(Application, application_id)
    if not application: return {"error": "Application not found"}, 404
    owner = db.session.get(User, application.institution_user_id) if application.institution_user_id else None
    documents = UploadedDocument.query.filter_by(application_id=application_id).order_by(UploadedDocument.id.asc()).all()
    flags = DocumentIntegrityReview.query.filter_by(application_id=application_id).order_by(DocumentIntegrityReview.created_at.desc()).all()
    evcs = EVCRecord.query.filter_by(application_id=application_id).order_by(EVCRecord.id.desc()).all()
    undertakings = Undertaking.query.filter_by(application_id=application_id).order_by(Undertaking.due_date.asc()).all()
    audit = AuditLog.query.filter_by(application_id=application_id).order_by(AuditLog.timestamp.asc()).all()
    summary = [f"CASE SUMMARY — {application.tracking_id or application.id}", f"Institution: {application.institution_name}", f"Type: {application.application_type}", f"Region: {getattr(application, 'state', None) or 'Not recorded'}", f"Status / stage: {application.status} / {application.current_stage}", f"Assigned officer: {application.assigned_officer or 'Unassigned'}", f"Institution contact: {owner.email if owner else 'Not recorded'}", f"Deadline: {application.deadline.isoformat() if application.deadline else 'Not set'}", f"Latest remarks: {application.remarks or 'None'}", "", "DOCUMENTS:"]
    summary.extend([f"- {d.file_name}: {d.upload_status}; expiry {d.expiry_date or 'not recorded'}; reviewer {d.verified_by or 'pending'}" for d in documents] or ["- No documents uploaded"])
    summary.append("\nINTEGRITY FLAGS:")
    summary.extend([f"- {f.flag_category}: {f.status}; {f.reason}" for f in flags] or ["- No integrity flags recorded"])
    summary.append("\nEVC:")
    summary.extend([f"- {e.committee_name or 'Committee'}: {e.status}; scheduled {e.scheduled_date or 'not set'}; {e.remarks or ''}" for e in evcs] or ["- No EVC records"])
    summary.append("\nCOMPLIANCE CONDITIONS:")
    summary.extend([f"- {u.title}: {u.status}; due {u.due_date}; evidence {u.evidence_file or 'not submitted'}" for u in undertakings] or ["- No compliance conditions"])
    summary.append("\nAUDIT EVENTS:")
    summary.extend([f"- {a.timestamp.isoformat() if a.timestamp else ''}: {a.action} by {a.performed_by or 'Unknown'} — {a.details or ''}" for a in audit] or ["- No audit events"])
    return {"application_id": application.id, "tracking_id": application.tracking_id, "summary": "\n".join(summary), "counts": {"documents":len(documents),"integrity_flags":len(flags),"evc_records":len(evcs),"undertakings":len(undertakings),"audit_events":len(audit)}}, 200


@app.route("/api/regulatory-rules", methods=["GET", "PUT"])
def regulatory_rules():
    from datetime import datetime
    from models import RegulatoryRule, AuditLog, Application
    # Deliberately only an officer can access these configurable prototype rules.
    if g.current_user.role != "officer": return {"error": "Officer role required"}, 403
    if request.method == "GET":
        return {"rules": [{"key":r.rule_key,"label":r.label,"value":r.value,"description":r.description,"updated_by":r.updated_by,"updated_at":r.updated_at.isoformat() if r.updated_at else None} for r in RegulatoryRule.query.order_by(RegulatoryRule.id.asc()).all()]}, 200
    data = request.get_json(silent=True) or {}
    key = str(data.get("key", "")).strip()
    value = str(data.get("value", "")).strip()
    if key not in {"duplicate_text_similarity", "expiry_warning_days", "escalation_level_1_days", "escalation_level_2_days", "manual_review_all_integrity_flags", "email_alerts_enabled"}:
        return {"error": "This rule is not editable"}, 400
    if not value: return {"error": "Rule value is required"}, 400
    if key == "duplicate_text_similarity":
        try: number = float(value)
        except ValueError: return {"error": "Threshold must be a number from 0.50 to 0.99"}, 400
        if not 0.5 <= number <= 0.99: return {"error": "Threshold must be from 0.50 to 0.99"}, 400
        value = str(number)
    elif key == "expiry_warning_days":
        try: number = int(value)
        except ValueError: return {"error": "Expiry warning window must be an integer"}, 400
        if not 1 <= number <= 365: return {"error": "Expiry warning window must be 1 to 365 days"}, 400
        value = str(number)
    elif key in {"escalation_level_1_days", "escalation_level_2_days"}:
        try: number = int(value)
        except ValueError: return {"error": "Escalation threshold must be an integer number of days"}, 400
        if not 1 <= number <= 730: return {"error": "Escalation threshold must be from 1 to 730 days"}, 400
        other_key = "escalation_level_2_days" if key == "escalation_level_1_days" else "escalation_level_1_days"
        other_rule = RegulatoryRule.query.filter_by(rule_key=other_key).first()
        if other_rule:
            try: other_number = int(other_rule.value)
            except ValueError: other_number = 14 if other_key == "escalation_level_2_days" else 7
            if key == "escalation_level_1_days" and number >= other_number:
                return {"error": "Escalation level 1 must be earlier than level 2"}, 400
            if key == "escalation_level_2_days" and number <= other_number:
                return {"error": "Escalation level 2 must be later than level 1"}, 400
        value = str(number)
    elif key in {"manual_review_all_integrity_flags", "email_alerts_enabled"}:
        if value.lower() not in {"true", "false"}: return {"error": "Value must be true or false"}, 400
        value = value.lower()
    rule = RegulatoryRule.query.filter_by(rule_key=key).first()
    if not rule: return {"error": "Rule not found"}, 404
    before = rule.value
    rule.value = value; rule.updated_by = g.current_user.email; rule.updated_at = datetime.utcnow()
    # Regulations/settings are global, so the update is audited against a valid application where possible.
    app_record = Application.query.order_by(Application.id.desc()).first()
    if app_record:
        db.session.add(AuditLog(application_id=app_record.id, action="Demonstration rule updated", performed_by=g.current_user.email, details=f"Reason: Configurable demo setting. Changes: {key} {before} -> {value}. Not an official AICTE rule."))
    db.session.commit()
    return {"message": "Demo rule saved", "key": key, "value": value, "note": "This setting is a configurable demo rule, not an official AICTE/APH rule."}, 200


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", host="127.0.0.1", port=5002)


