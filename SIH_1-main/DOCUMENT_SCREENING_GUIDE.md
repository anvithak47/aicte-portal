# Document duplicate / suspicious-content screening guide

## What it checks

- **Exact duplicate:** SHA-256 hash of the uploaded file matches a prior upload.
- **Likely duplicate:** normalized extracted text is at least 88% similar to a prior document. This can flag templates and repeated wording as well as problematic copies.
- **Explicit placeholder indicators:** text says sample, dummy, specimen, test document, not a valid document, or similar configured phrases.
- **Wrong document type:** strong document-type text (for example, a marksheet/grade card) conflicts with a specific required slot such as Application Form. Generic slots like Supporting Evidence are not hard-coded.
- **Explicit signature/seal issues:** text explicitly says unsigned, signature missing, seal missing, not affixed, or similar configured phrases.
- **Signature/seal visual review:** if the text contains a signature/seal label, it creates a visual review item because OCR text alone cannot establish whether the graphic/handwritten mark is present.
- **File format spoofing:** upload is rejected if file bytes do not match the PDF/PNG/JPEG extension.
- **Unreadable file:** extraction/OCR failure is sent for manual review and the application is marked deficient for follow-up.

## Officer workflow

1. Sign in as an officer and select **Document verification**.
2. In **Potential integrity flags**, select **Open uploaded file** and, when offered, **Open possible match**.
3. Use **Investigate** to keep a flag open while checking it.
4. Use **Mark deficient** only when the officer decides the institution must correct or replace the file. This writes an audit entry and marks the application deficient.
5. Use **Clear flag** only after human review. This records the review result. The system never automatically declares a person or document fraudulent.

## Limits

These are heuristic risk checks, not a forgery classifier or digital-signature validation system. Similar text is not proof of duplication or malpractice; legitimate institutions may use common templates. To authenticate a real certificate, compare it with the issuing authority's records or verify a supported cryptographic signature. Scanned image OCR requires Tesseract installed and available on PATH.
