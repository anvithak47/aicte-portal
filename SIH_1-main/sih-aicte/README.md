# AICTEFlow frontend

React + Vite frontend for the local AICTEFlow SIH demonstration. The existing dashboard styling is retained and connected to the Flask backend. This is not an official AICTE service.

## Setup

Requires a compatible Node.js release with npm.

```powershell
npm ci
npm run dev
```

Open the URL printed by Vite (normally `http://localhost:5173`). The Flask backend must also be running from `../AICTE_Approval` at `http://localhost:5002`, unless `VITE_API_URL` is configured differently in `.env.local`.

For a production bundle:

```powershell
npm ci
npm run build
npm run preview
```

## Roles

- Institution users register and sign in through the backend.
- AICTE officer, EVC committee, and authority users must be created by an administrator with `python create_user.py officer`, `python create_user.py committee`, or `python create_user.py authority` in the backend folder.
- Role selection in the UI does not grant a role; Flask checks the stored server account role.

## Current connected modules

Application draft and submission, required-document progression and upload, document-integrity flags and officer review, stage transitions and case history, EVC scheduling and completion, compliance evidence, document expiry/renewal, persistent alerts, standardized case communications/summaries, editable demonstration rules, and live report/CSV export are connected to backend endpoints. See the root `FEATURE_CHECKLIST.md` for the current implementation status and `TEST_REPORT.md` for unverified tests/limitations.

Document and regulatory requirements seeded by the demo are illustrative placeholders, not official AICTE/APH policy. Automated screening findings are advisory and require human review. Email delivery requires SMTP setup; OCR of scanned documents requires Tesseract.
