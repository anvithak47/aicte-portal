from reportlab.pdfgen import canvas

file_name = "sample_institution_certificate.pdf"
c = canvas.Canvas(file_name)
c.setTitle("Sample Institution Certificate")
c.setFont("Helvetica-Bold", 16)
c.drawString(70, 760, "SAMPLE INSTITUTION REGISTRATION CERTIFICATE")
c.setFont("Helvetica", 12)
c.drawString(70, 710, "Institution Name: Demo Engineering College")
c.drawString(70, 680, "Registration ID: DEMO-2026-001")
c.drawString(70, 650, "Issue Date: 01 January 2026")
c.drawString(70, 620, "Expiry Date: 31 December 2028")
c.drawString(70, 580, "FOR SOFTWARE TESTING ONLY - NOT AN OFFICIAL CERTIFICATE")
c.save()
print(f"Created: {file_name}")
