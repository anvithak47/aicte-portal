
from pathlib import Path
from datetime import date, datetime
import re

import pytesseract
from PIL import Image
import pymupdf



import os
import shutil

if os.name == "nt":
    TESSERACT_EXE = Path(
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )
    if TESSERACT_EXE.exists():
        pytesseract.pytesseract.tesseract_cmd = str(TESSERACT_EXE)
else:
    tesseract_path = shutil.which("tesseract")
    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path


# --------------------------------------------------
# 1. DOCUMENT TEXT EXTRACTION
# --------------------------------------------------

def extract_document_text(file_path):
    path = Path(file_path)

    if not path.exists():
        return {
            "status": "Needs Manual Review",
            "reason": "File not found",
            "text": ""
        }

    if path.stat().st_size < 100:
        return {
            "status": "Needs Manual Review",
            "reason": "File is unusually small; it may be invalid",
            "text": ""
        }

    try:
        suffix = path.suffix.lower()
        text = ""

        if suffix == ".pdf":
            with pymupdf.open(path) as pdf:
                if pdf.is_encrypted:
                    return {
                        "status": "Needs Manual Review",
                        "reason": "Encrypted PDF requires manual review",
                        "text": ""
                    }

                text = "\n".join(
                    page.get_text("text") for page in pdf
                ).strip()

                if not text:
                    page_text = []

                    for page in pdf:
                        pix = page.get_pixmap(
                            matrix=pymupdf.Matrix(2, 2),
                            alpha=False
                        )

                        image = Image.frombytes(
                            "RGB",
                            [pix.width, pix.height],
                            pix.samples
                        )

                        page_text.append(
                            pytesseract.image_to_string(image)
                        )

                    text = "\n".join(page_text).strip()

        elif suffix in {
            ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"
        }:
            with Image.open(path) as image:
                text = pytesseract.image_to_string(image).strip()

        else:
            return {
                "status": "Needs Manual Review",
                "reason": "Unsupported file type",
                "text": ""
            }

        if len(text.strip()) < 10:
            return {
                "status": "Needs Manual Review",
                "reason": "Insufficient readable text",
                "text": text
            }

        return {
            "status": "Text Extracted",
            "reason": "Text extracted; document authenticity is not established",
            "text": text
        }

    except Exception as exc:
        return {
            "status": "Needs Manual Review",
            "reason": f"Extraction failed: {type(exc).__name__}",
            "text": ""
        }


# --------------------------------------------------
# 2. DATE EXTRACTION HELPERS
# --------------------------------------------------

DATE_PATTERN = (
    r"\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{4}"
    r"|\d{1,2}\s+[A-Za-z]+\s+\d{4}"
)


def parse_document_date(raw_date):
    if not raw_date:
        return None

    raw_date = raw_date.strip()

    formats = (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d %B %Y",
        "%d %b %Y",
    )

    for fmt in formats:
        try:
            return datetime.strptime(raw_date, fmt).date()
        except ValueError:
            continue

    return None


def find_labeled_date(text, labels):
    label_pattern = "|".join(labels)

    match = re.search(
        rf"(?:{label_pattern})\s*[:\-]?\s*"
        rf"({DATE_PATTERN})",
        text or "",
        re.IGNORECASE
    )

    if not match:
        return None

    return parse_document_date(match.group(1))


# --------------------------------------------------
# 3. EXISTING EXPIRY VALIDATION
# --------------------------------------------------

def check_expiry_date(expiry_date_text):
    parsed = parse_document_date(expiry_date_text)

    if parsed is None:
        return {
            "status": "Needs Manual Review",
            "evidence": "Expiry date is missing or unreadable"
        }

    if parsed < date.today():
        return {
            "status": "Expired",
            "evidence": f"Expiry date {parsed.isoformat()} has passed"
        }

    return {
        "status": "Not Expired",
        "evidence": f"Expiry date {parsed.isoformat()} has not passed"
    }


def extract_and_check_expiry(text):
    expiry = find_labeled_date(text, [
        r"expiry(?:\s+date)?",
        r"expiration(?:\s+date)?",
        r"expires",
        r"valid\s+until",
        r"validity"
    ])

    if expiry is None:
        return {
            "status": "Needs Manual Review",
            "findings": [{
                "type": "Expiry Date Not Found",
                "severity": "Review",
                "evidence": "No recognizable expiry date was found"
            }]
        }

    status = "Expired" if expiry < date.today() else "Not Expired"

    finding_type = (
        "Expired Document"
        if status == "Expired"
        else "Expiry Date Detected"
    )

    return {
        "status": status,
        "expiry_date": expiry.isoformat(),
        "findings": [{
            "type": finding_type,
            "severity": "Review",
            "evidence": (
                f"Extracted expiry date: {expiry.isoformat()}; "
                "officer should verify"
            )
        }]
    }


# --------------------------------------------------
# 4. INSTITUTION AND REGISTRATION-ID CHECKS
# --------------------------------------------------

def inspect_document_text(text, expected_institution=None):
    normalized = re.sub(r"\s+", " ", text or "").strip()
    findings = []

    if len(normalized) < 30:
        findings.append({
            "type": "Low Text Content",
            "severity": "Review",
            "evidence": "Document contains very little readable text"
        })

    if expected_institution:
        if expected_institution.casefold() not in normalized.casefold():
            findings.append({
                "type": "Institution Name Not Found",
                "severity": "Review",
                "evidence": (
                    "Expected institution name was not found: "
                    f"{expected_institution}"
                )
            })

    registration_match = re.search(
        r"(?:registration|certificate)\s*(?:id|no\.?|number)"
        r"\s*[:#\-]?\s*([A-Z0-9][A-Z0-9/-]{2,})",
        normalized,
        re.IGNORECASE
    )

    if registration_match:
        registration_id = registration_match.group(1).strip()
    else:
        registration_id = None
        findings.append({
            "type": "Registration ID Not Found",
            "severity": "Review",
            "evidence": (
                "No recognizable registration or certificate ID was found"
            )
        })

    status = (
        "Needs Manual Review"
        if findings
        else "Text Extracted - Review Required"
    )

    return {
        "status": status,
        "registration_id": registration_id,
        "findings": findings
    }


# --------------------------------------------------
# 5. REQUIRED-FIELD VALIDATION
# --------------------------------------------------

def validate_required_fields(text, expected_institution=None):
    if not text or not text.strip():
        return {
            "status": "Needs Manual Review",
            "fields": {},
            "findings": [{
                "type": "Text Unavailable",
                "severity": "Review",
                "evidence": "Required fields cannot be checked without text"
            }]
        }

    normalized = re.sub(r"\s+", " ", text).strip()
    findings = []
    fields = {}

    # Institution name
    institution_present = bool(re.search(
        r"\binstitution\s+name\s*[:\-]\s*\S",
        normalized,
        re.IGNORECASE
    ))

    fields["institution_name"] = {
        "present": institution_present,
        "expected_value": expected_institution
    }

    if not institution_present:
        findings.append({
            "type": "Institution Name Field Missing",
            "severity": "Review",
            "evidence": "No explicitly labeled Institution Name field was found"
        })
    elif expected_institution and (
        expected_institution.casefold() not in normalized.casefold()
    ):
        findings.append({
            "type": "Institution Name Mismatch",
            "severity": "Review",
            "evidence": (
                "The expected institution name was not found in document text"
            )
        })

    # Registration ID
    registration_match = re.search(
        r"(?:registration|certificate)\s*(?:id|no\.?|number)"
        r"\s*[:#\-]?\s*([A-Z0-9][A-Z0-9/-]{2,})",
        normalized,
        re.IGNORECASE
    )

    fields["registration_id"] = {
        "present": registration_match is not None,
        "value": (
            registration_match.group(1)
            if registration_match else None
        )
    }

    if registration_match is None:
        findings.append({
            "type": "Registration ID Missing",
            "severity": "Review",
            "evidence": "No recognizable registration ID was found"
        })

    # Issue date
    issue_date = find_labeled_date(normalized, [
        r"issue\s+date",
        r"issued\s+on",
        r"date\s+of\s+issue"
    ])

    fields["issue_date"] = {
        "present": issue_date is not None,
        "value": issue_date.isoformat() if issue_date else None
    }

    if issue_date is None:
        findings.append({
            "type": "Issue Date Missing or Unreadable",
            "severity": "Review",
            "evidence": "No recognizable issue date was found"
        })

    # Expiry date
    expiry_date = find_labeled_date(normalized, [
        r"expiry(?:\s+date)?",
        r"expiration(?:\s+date)?",
        r"expires",
        r"valid\s+until",
        r"validity"
    ])

    fields["expiry_date"] = {
        "present": expiry_date is not None,
        "value": expiry_date.isoformat() if expiry_date else None
    }

    if expiry_date is None:
        findings.append({
            "type": "Expiry Date Missing or Unreadable",
            "severity": "Review",
            "evidence": "No recognizable expiry date was found"
        })
    elif expiry_date < date.today():
        findings.append({
            "type": "Document Expired",
            "severity": "Review",
            "evidence": f"Expiry date {expiry_date.isoformat()} has passed"
        })

    return {
        "status": (
            "Needs Manual Review"
            if findings
            else "Required Fields Detected - Review Required"
        ),
        "fields": fields,
        "findings": findings,
        "advisory_only": True
    }
