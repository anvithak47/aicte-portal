"""Refresh persistent alerts and optionally email digest notifications.
Run this script using Windows Task Scheduler (e.g. hourly). It sends no email unless
email_alerts_enabled is true in Regulatory rules and SMTP is configured in .env.
"""
from datetime import datetime, timedelta
from app import app, _build_persistent_alerts, _send_email, _smtp_settings
from extensions import db
from models import PersistentAlert, RegulatoryRule, Application, User, AuditLog


def main():
    with app.app_context():
        db.create_all()
        _build_persistent_alerts()
        rule = RegulatoryRule.query.filter_by(rule_key="email_alerts_enabled").first()
        if not rule or rule.value.lower() != "true":
            print("Alert records refreshed. Email is disabled by the email_alerts_enabled demo rule.")
            return 0
        if not _smtp_settings():
            print("Alert records refreshed. SMTP is not configured; no emails sent.")
            return 0
        now = datetime.utcnow()
        eligible = PersistentAlert.query.filter(PersistentAlert.status.in_(["Open", "Acknowledged"])).all()
        by_recipient = {}
        for alert in eligible:
            if alert.last_emailed_at and alert.last_emailed_at > now - timedelta(hours=24):
                continue
            app_record = db.session.get(Application, alert.application_id) if alert.application_id else None
            owner = db.session.get(User, app_record.institution_user_id) if app_record and app_record.institution_user_id else None
            if owner and owner.email:
                by_recipient.setdefault(owner.email, []).append(alert)
            if (alert.escalation_level or 0) > 0:
                for address in (alert.escalated_to or "").split(";"):
                    if address.strip():
                        by_recipient.setdefault(address.strip(), []).append(alert)
        sent = failed = 0
        for recipient, alerts in by_recipient.items():
            # Deduplicate the same alert when a recipient is both owner and authority.
            alerts = list({a.id: a for a in alerts}.values())
            body = "AICTEFlow local demo alert digest\nGenerated at UTC: " + now.isoformat() + "\n\n"
            body += "\n\n".join(f"{a.title}\n{a.details or ''}\nStatus: {a.status}\nEscalation level: {a.escalation_level or 0}" for a in alerts)
            ok, message = _send_email(recipient, "AICTEFlow: application and compliance alerts", body)
            if ok:
                sent += 1
                for alert in alerts:
                    alert.last_emailed_at = now
                    if alert.application_id:
                        db.session.add(AuditLog(application_id=alert.application_id, action="Scheduled alert email sent", performed_by="system scheduler", details=f"Alert {alert.id} sent to configured recipient."))
            else:
                failed += 1
                app.logger.warning("Scheduled alert email was not delivered to configured recipient.")
        db.session.commit()
        print(f"Alert refresh complete. Recipients sent: {sent}; failed: {failed}.")
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
