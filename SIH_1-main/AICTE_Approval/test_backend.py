"""Focused Flask API tests for authentication, role enforcement and persistence."""
import os
import tempfile
import unittest
from datetime import datetime
from app import app
from extensions import db
from models import User, Application

class BackendSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False); self.tmp.close()
        self.original_uri = app.config['SQLALCHEMY_DATABASE_URI']
        with app.app_context():
            for old_engine in db.engines.values(): old_engine.dispose()
            db._app_engines.pop(app, None)
        app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///' + self.tmp.name, SECRET_KEY='test-secret')
        self.client = app.test_client()
        with app.app_context():
            db.create_all()
            institution = User(email='school@example.edu', role='institution', institution_name='Example School'); institution.set_password('safe-password-123')
            officer = User(email='officer@example.gov', role='officer'); officer.set_password('safe-password-456')
            other = User(email='other@example.edu', role='institution', institution_name='Other College'); other.set_password('safe-password-789')
            db.session.add_all([institution, officer, other]); db.session.commit()
    def tearDown(self):
        with app.app_context():
            db.session.remove(); db.drop_all()
            for engine in db.engines.values(): engine.dispose()
            db._app_engines.pop(app, None)
        app.config.update(SQLALCHEMY_DATABASE_URI=self.original_uri, TESTING=False)
        try: os.unlink(self.tmp.name)
        except OSError: pass
    def test_protected_endpoint_requires_login(self):
        self.assertEqual(self.client.get('/api/applications').status_code, 401)
    def test_invalid_login_rejected(self):
        r=self.client.post('/api/auth/login',json={'email':'school@example.edu','password':'wrong','role':'institution'})
        self.assertEqual(r.status_code,401)
    def test_role_selector_does_not_grant_officer(self):
        r=self.client.post('/api/auth/login',json={'email':'school@example.edu','password':'safe-password-123','role':'officer'})
        self.assertEqual(r.status_code,403)
    def test_institution_cannot_read_integrity_queue(self):
        self.client.post('/api/auth/login',json={'email':'school@example.edu','password':'safe-password-123','role':'institution'})
        self.assertEqual(self.client.get('/api/integrity-reviews').status_code,403)
    def test_institution_can_create_own_application(self):
        self.client.post('/api/auth/login',json={'email':'school@example.edu','password':'safe-password-123','role':'institution'})
        r=self.client.post('/api/applications',json={'institution_name':'Forged name','application_type':'New Institution'})
        self.assertEqual(r.status_code,201)
        with app.app_context():
            a=Application.query.one(); self.assertEqual(a.institution_name,'Example School'); self.assertIsNotNone(a.institution_user_id); self.assertTrue(a.tracking_id)
    def test_institution_cannot_choose_review_deadline(self):
        from models import DocumentRequirement, UploadedDocument
        self.client.post('/api/auth/login',json={'email':'school@example.edu','password':'safe-password-123','role':'institution'})
        response=self.client.post('/api/applications',json={
            'institution_name':'Example School',
            'application_type':'New Institution',
            'deadline':'2040-01-01'
        })
        self.assertEqual(response.status_code,201)
        self.assertEqual(response.json.get('deadline_source'),'assigned_on_submission')
        self.assertIsNone(response.json.get('deadline'))
        app_id=response.json['application_id']
        with app.app_context():
            application=Application.query.get(app_id)
            self.assertIsNone(application.deadline)
            requirement=DocumentRequirement(application_type='New Institution',document_name='Application Form',sequence_order=1,is_mandatory=True)
            db.session.add(requirement); db.session.flush()
            db.session.add(UploadedDocument(application_id=application.id,requirement_id=requirement.id,file_name='form.pdf',file_path='test-only.pdf',upload_status='Uploaded'))
            db.session.commit()
        submitted=self.client.post(f'/api/applications/{app_id}/submit',json={})
        self.assertEqual(submitted.status_code,200,submitted.json)
        self.assertEqual(submitted.json.get('deadline_source'),'system_demo_sla')
        self.assertNotEqual(submitted.json['deadline'][:10],'2040-01-01')
        with app.app_context():
            application=Application.query.get(app_id)
            days=(application.deadline-datetime.utcnow()).days
            self.assertGreaterEqual(days,28)
            self.assertLessEqual(days,30)

    def test_institution_cannot_read_another_institutions_application(self):
        self.client.post('/api/auth/login',json={'email':'school@example.edu','password':'safe-password-123','role':'institution'})
        created=self.client.post('/api/applications',json={'institution_name':'x','application_type':'New Institution'}).json
        self.client.post('/api/auth/logout',json={})
        self.client.post('/api/auth/login',json={'email':'other@example.edu','password':'safe-password-789','role':'institution'})
        self.assertEqual(self.client.get(f"/api/applications/{created['application_id']}").status_code,404)

    def test_submission_requires_configured_requirements(self):
        self.client.post('/api/auth/login',json={'email':'school@example.edu','password':'safe-password-123','role':'institution'})
        created=self.client.post('/api/applications',json={'institution_name':'x','application_type':'New Institution'}).json
        response=self.client.post(f"/api/applications/{created['application_id']}/submit",json={})
        self.assertEqual(response.status_code,409)

    def test_officer_can_list_applications_and_institution_cannot_decide(self):
        self.client.post('/api/auth/login',json={'email':'school@example.edu','password':'safe-password-123','role':'institution'})
        created=self.client.post('/api/applications',json={'institution_name':'x','application_type':'New Institution'}).json
        self.client.post('/api/auth/logout',json={})
        self.client.post('/api/auth/login',json={'email':'officer@example.gov','password':'safe-password-456','role':'officer'})
        self.assertEqual(self.client.get('/api/applications').status_code,200)
        self.assertEqual(self.client.put(f"/api/applications/{created['application_id']}/decision",json={'decision':'Approved','performed_by':'x'}).status_code,409) # not at decision stage

if __name__ == '__main__': unittest.main()
