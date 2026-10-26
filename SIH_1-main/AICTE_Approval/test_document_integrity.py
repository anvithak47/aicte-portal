import hashlib
import io
import unittest

from document_integrity import sha256_stream, similarity_ratio, screen_document_text, file_signature_matches, detect_requirement_type_mismatch


class Sha256StreamTests(unittest.TestCase):
    def test_known_digest_and_restores_position(self):
        stream = io.BytesIO(b"hello world")
        stream.seek(3)
        self.assertEqual(sha256_stream(stream), hashlib.sha256(b"hello world").hexdigest())
        self.assertEqual(stream.tell(), 3)

    def test_same_content_same_hash_despite_filename_not_involved(self):
        first = io.BytesIO(b"same bytes")
        second = io.BytesIO(b"same bytes")
        self.assertEqual(sha256_stream(first), sha256_stream(second))

    def test_different_content_different_hash(self):
        self.assertNotEqual(sha256_stream(io.BytesIO(b"one")), sha256_stream(io.BytesIO(b"two")))

    def test_text_similarity_ignores_basic_formatting(self):
        self.assertEqual(similarity_ratio("Certificate No: 123\nInstitution Name", "certificate no 123 institution name"), 1.0)

    def test_text_similarity_distinguishes_unrelated_text(self):
        self.assertLess(similarity_ratio("land ownership certificate institution A", "faculty salary records institution B"), 0.8)

    def test_explicit_dummy_marker_is_flagged(self):
        findings = screen_document_text("UNIVERSITY MARKSHEET - SAMPLE DOCUMENT FOR TESTING ONLY")
        self.assertTrue(any(f["type"] == "Explicit Placeholder Content" for f in findings))

    def test_explicit_missing_signature_is_flagged(self):
        findings = screen_document_text("This document is unsigned; official seal not affixed")
        kinds = {f["type"] for f in findings}
        self.assertIn("Explicit Missing Signature", kinds)
        self.assertIn("Explicit Missing Official Seal", kinds)

    def test_explicit_alteration_marker_is_flagged(self):
        findings = screen_document_text("This is an altered document")
        self.assertTrue(any(f["type"] == "Possible Alteration Marker" for f in findings))

    def test_no_fraud_conclusion_for_ordinary_text(self):
        self.assertEqual(screen_document_text("University marksheet. Student completed course."), [])

    def test_signature_block_requires_visual_review_not_automatic_fraud(self):
        findings = screen_document_text("OFFICIAL SEAL & SIGNATURE")
        self.assertEqual(findings[0]["type"], "Signature/Seal Visual Check Required")
        self.assertEqual(findings[0]["severity"], "Manual review")

    def test_marksheet_in_application_form_slot_is_flagged(self):
        findings = detect_requirement_type_mismatch(
            "OFFICIAL GRADE CARD / MARKS SHEET Student Name USN Semester IV SGPA 8.8",
            "Application Form"
        )
        self.assertTrue(any(f["type"] == "Document Type Mismatch" for f in findings))

    def test_generic_supporting_evidence_does_not_auto_mismatch(self):
        findings = detect_requirement_type_mismatch(
            "OFFICIAL GRADE CARD / MARKS SHEET Student Name USN Semester IV",
            "Supporting Evidence"
        )
        self.assertEqual(findings, [])

    def test_file_magic_matches_extension(self):
        self.assertTrue(file_signature_matches("pdf", b"%PDF-1.7\n"))
        self.assertTrue(file_signature_matches("png", b"\x89PNG\r\n\x1a\n"))
        self.assertTrue(file_signature_matches("jpg", b"\xff\xd8\xff\xe0"))
        self.assertFalse(file_signature_matches("pdf", b"not a pdf"))

    def test_unreadable_text_needs_review(self):
        findings = screen_document_text("")
        self.assertEqual(findings[0]["type"], "Unreadable Document")


if __name__ == "__main__":
    unittest.main()
