# Test report — updated SIH AICTE project

Date: 2026-10-25

## Checks executed in the preparation environment

- `python -m compileall -q app.py models.py document_integrity.py document_ai.py send_scheduled_alerts.py test_document_integrity.py test_backend.py`: **passed**.
- `python -m unittest -v test_document_integrity.py`: **14 tests passed**. Tests cover SHA-256, similarity, dummy/alteration/missing-signature wording, signature/seal visual review, document type mismatch, unreadable content and file magic checks.
- `typescript.transpileModule` was used as a parser/transpiler check on `sih-aicte/src/App.jsx`: **passed** (JSX syntax parsed; this is not a Vite build).
- `npm run build` / Vite build: **not completed** in the preparation environment. The included `node_modules` was partial and the Vite/Rolldown native optional binding for this Linux environment was missing; `npx esbuild` timed out trying to obtain the package.
- `python -m unittest -v test_backend.py`: **not run successfully** because Flask is not installed in the preparation environment (`ModuleNotFoundError: No module named 'flask'`). Install `requirements.txt` on Windows and rerun both backend test modules.
- Full browser end-to-end tests were not run here.
- ZIP integrity was checked after packaging.

## Run local validation on Windows

Backend (from `AICTE_Approval`, with `.venv` active):

```powershell
python -m compileall -q .
python -m unittest -v test_document_integrity.py test_backend.py
```

Frontend (from `sih-aicte`):

```powershell
npm ci
npm run build
```

Then test institution registration/login/logout, officer/committee/authority login, application draft → required uploads → submit, duplicate file upload, officer review/deficiency/correction, EVC assignment and completion, compliance evidence, document renewal, alert acknowledgement/closure, report export, cross-institution access denial, and persistence after restarting Flask.

Automated findings are risk signals only, not proof that a file is forged or genuine. OCR of scanned documents requires Tesseract. SMTP delivery requires explicitly configured credentials and `email_alerts_enabled=true`. Seeded document requirements and regulatory settings are illustrative, not official rules.

### Deadline ownership correction
- Institution deadline picker removed from the application-creation form.
- Backend ignores client-supplied deadlines when an application draft is created; the deadline remains unset until mandatory document/integrity checks pass during submission, then the server assigns the configurable demo SLA (default 30 days; `DEMO_REVIEW_SLA_DAYS`, 1–365).
- Authorized AICTE officers can change the review deadline only through the existing audited edit workflow with a mandatory change reason.
- Added a backend unit test proving a supplied institution deadline is ignored and the deadline is assigned only after successful submission. This added test is source-reviewed/compiled but could not be executed in this environment because Flask dependencies are unavailable.
