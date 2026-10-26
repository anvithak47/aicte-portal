"""Advisory document integrity helpers. Flags are evidence for human review, not findings."""
import hashlib
import re
import difflib
from pathlib import Path


def sha256_stream(stream):
    """Hash a seekable binary stream and restore its original position."""
    try:
        original_position = stream.tell()
    except (AttributeError, OSError):
        original_position = 0
    digest = hashlib.sha256()
    try:
        stream.seek(0)
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        return digest.hexdigest()
    finally:
        try:
            stream.seek(original_position)
        except (AttributeError, OSError):
            pass


def normalize_text(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (text or "").lower())).strip()


def similarity_ratio(first, second):
    """Return a normalized text similarity estimate in [0, 1]."""
    a, b = normalize_text(first), normalize_text(second)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # SequenceMatcher works well for modest certificate text and needs no model.
    return difflib.SequenceMatcher(None, a[:8000], b[:8000]).ratio()


def extract_document_text(file_path):
    """Extract text from PDFs or image files; OCR is optional and requires Tesseract."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import fitz
        chunks = []
        with fitz.open(path) as document:
            if document.is_encrypted:
                raise ValueError("Encrypted PDF cannot be read without a password")
            for page in document:
                chunks.append(page.get_text("text"))
        text = "\n".join(chunks).strip()
        if text:
            return text[:500000]
        # A scanned PDF may need OCR; keep this optional and explicit.
        try:
            import pytesseract
            from PIL import Image
            import io
            with fitz.open(path) as document:
                ocr_chunks = []
                for page in document:
                    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                    image = Image.open(io.BytesIO(pix.tobytes("png")))
                    ocr_chunks.append(pytesseract.image_to_string(image))
            return "\n".join(ocr_chunks)[:500000]
        except ImportError:
            return ""
    if suffix in {".png", ".jpg", ".jpeg"}:
        try:
            import pytesseract
            from PIL import Image
            return pytesseract.image_to_string(Image.open(path))[:500000]
        except ImportError:
            return ""
    raise ValueError("Unsupported file format")


# Deliberately conservative patterns. These identify explicit red flags in extracted
# text; they cannot prove that a document is forged, and require officer review.
_PLACEHOLDER_PATTERNS = (
    ("Explicit Placeholder Content", re.compile(
        r"\b(?:dummy(?:\s+(?:document|certificate|marksheet|mark\s*sheet|copy))?|"
        r"sample(?:\s+(?:only|document|certificate|marksheet|mark\s*sheet|copy))?|"
        r"specimen(?:\s+(?:copy|certificate|document))?|"
        r"for testing only|for demo(?:nstration)? purposes only|"
        r"not a valid document|template only|test document)\b", re.I)),
    ("Possible Alteration Marker", re.compile(
        r"\b(?:forged document|fabricated certificate|fake certificate|"
        r"not genuine|photoshopped|altered document|edited certificate)\b", re.I)),
)
_SIGNATURE_SEAL_PATTERNS = (
    ("Explicit Missing Signature", re.compile(
        r"\b(?:unsigned|not signed|no signature|without (?:an? )?signature|"
        r"signature absent|signature missing|missing signature|"
        r"signature not (?:provided|available|affixed)|pending signature|"
        r"signature to be affixed)\b", re.I)),
    ("Explicit Missing Official Seal", re.compile(
        r"\b(?:seal missing|missing seal|no (?:official )?seal|without (?:an? )?(?:official )?seal|"
        r"seal absent|stamp missing|missing stamp|"
        r"seal not (?:provided|available|affixed)|stamp not affixed|"
        r"official seal not affixed)\b", re.I)),
)


def screen_document_text(text):
    """Return advisory red flags from extracted text; never a definitive fraud verdict."""
    findings = []
    value = text or ""
    if not value.strip():
        return [{
            "type": "Unreadable Document",
            "severity": "Review",
            "evidence": "No readable text was extracted. OCR may be unavailable or this may be a scanned/image-only document.",
        }]
    for category, pattern in _PLACEHOLDER_PATTERNS:
        match = pattern.search(value)
        if match:
            findings.append({
                "type": category,
                "severity": "High review priority",
                "evidence": f"Explicit sample/test marker found in extracted text: {match.group(0)!r}.",
            })
    for category, pattern in _SIGNATURE_SEAL_PATTERNS:
        match = pattern.search(value)
        if match:
            findings.append({
                "type": category,
                "severity": "High review priority",
                "evidence": f"Text explicitly indicates a signature/seal issue: {match.group(0)!r}.",
            })
    # Plain text extraction cannot establish whether a handwritten seal/signature
    # image is actually present. If a signature/seal block is mentioned, request a
    # visual officer check rather than automatically declaring it missing.
    if (not any(f["type"].startswith("Explicit Missing") for f in findings)
            and re.search(r"\b(?:official\s+)?(?:signature|seal|stamp)\b", value, re.I)):
        findings.append({
            "type": "Signature/Seal Visual Check Required",
            "severity": "Manual review",
            "evidence": "Signature/seal wording was found, but extracted text cannot confirm that an actual handwritten/graphic signature or seal is present. Officer must inspect the original file.",
        })
    return findings


def file_signature_matches(extension, header):
    """Validate simple magic bytes for supported upload types (not authenticity)."""
    extension = (extension or "").lower().lstrip(".")
    header = header or b""
    return (
        (extension == "pdf" and header.startswith(b"%PDF-"))
        or (extension == "png" and header.startswith(b"\x89PNG\r\n\x1a\n"))
        or (extension in {"jpg", "jpeg"} and header.startswith(b"\xff\xd8\xff"))
    )


# Only compare clear document-type signatures. Generic labels such as "Supporting
# Evidence" intentionally have no hard-coded expectation.
_CONTENT_TYPE_PATTERNS = {
    "academic_record": re.compile(
        r"\b(?:marksheet|mark\s*sheet|grade\s*card|transcript|SGPA|CGPA|USN|semester\s+[IVX0-9]+)\b", re.I
    ),
    "application_form": re.compile(
        r"\b(?:application\s+form|application\s+for\s+(?:approval|establishment)|"
        r"applicant\s+details|application\s+number)\b", re.I
    ),
    "institution_identity": re.compile(
        r"\b(?:certificate\s+of\s+incorporation|institution\s+registration|"
        r"registration\s+(?:certificate|number|no\.?|id)|establishment\s+certificate)\b", re.I
    ),
    "property": re.compile(
        r"\b(?:land\s+(?:ownership|title|records?)|property\s+deed|survey\s+number|encumbrance\s+certificate)\b", re.I
    ),
    "safety_certificate": re.compile(
        r"\b(?:fire\s+safety|building\s+safety|structural\s+stability|occupancy\s+certificate)\b", re.I
    ),
    "faculty_record": re.compile(
        r"\b(?:faculty\s+(?:details|list|information)|teaching\s+staff|staff\s+qualification)\b", re.I
    ),
    "approval_letter": re.compile(
        r"\b(?:letter\s+of\s+approval|AICTE\s+approval|extension\s+of\s+approval|approval\s+letter)\b", re.I
    ),
}

_REQUIREMENT_TYPES = {
    "application": ("Application Form", re.compile(r"\bapplication\s+form\b", re.I)),
    "institution_identity": ("Institution Registration / Identity Document", re.compile(r"\b(?:registration|identity|incorporation)\b", re.I)),
    "property": ("Land / Property Document", re.compile(r"\b(?:land|property|survey|encumbrance)\b", re.I)),
    "safety_certificate": ("Safety / Building Certificate", re.compile(r"\b(?:safety|structural|occupancy)\b", re.I)),
    "faculty_record": ("Faculty Record", re.compile(r"\bfaculty\b", re.I)),
    "approval_letter": ("Approval Letter", re.compile(r"\bapproval\b", re.I)),
}


def detect_requirement_type_mismatch(text, requirement_name):
    """Flag only strong content-vs-slot mismatches; returns no verdict on authenticity."""
    value = text or ""
    label = requirement_name or ""
    expected = None
    if re.search(r"application\s+form", label, re.I):
        expected = "application_form"
    elif re.search(r"registration|identity|incorporation", label, re.I):
        expected = "institution_identity"
    elif re.search(r"land|property|survey|encumbrance", label, re.I):
        expected = "property"
    elif re.search(r"safety|building|structural|occupancy", label, re.I):
        expected = "safety_certificate"
    elif re.search(r"faculty", label, re.I):
        expected = "faculty_record"
    elif re.search(r"approval letter|letter of approval", label, re.I):
        expected = "approval_letter"
    if not expected or not value.strip():
        return []

    # It is only a mismatch if another document family is clearly present and the
    # expected family is not present. Do not make assumptions for generic evidence.
    actual_types = [kind for kind, pattern in _CONTENT_TYPE_PATTERNS.items() if pattern.search(value)]
    if expected in actual_types or not actual_types:
        return []
    # Only flag when exactly one distinct conflicting family is detected; mixed
    # multi-document PDFs are sent to a reviewer instead of being auto-failed.
    if len(actual_types) != 1:
        return []
    actual = actual_types[0]
    return [{
        "type": "Document Type Mismatch",
        "severity": "High review priority",
        "evidence": (
            f"The file appears to contain {actual.replace('_', ' ')} content, "
            f"but it was uploaded for the requirement '{label}'. Check that the correct file was selected."
        ),
    }]
