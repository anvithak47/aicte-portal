
import sqlite3

DB_PATH = "instance/aicte.db"

connection = sqlite3.connect(DB_PATH)

columns = {
    "issue_date": "DATE",
    "expiry_date": "DATE",
    "renewal_status": "VARCHAR(50) NOT NULL DEFAULT 'Not Required'",
    "renewed_document_id": "INTEGER"
}

existing_columns = {
    row[1]
    for row in connection.execute(
        "PRAGMA table_info(uploaded_document)"
    ).fetchall()
}

for column_name, column_type in columns.items():
    if column_name not in existing_columns:
        connection.execute(
            f"ALTER TABLE uploaded_document "
            f"ADD COLUMN {column_name} {column_type}"
        )
        print(f"Added column: {column_name}")
    else:
        print(f"Already exists: {column_name}")

connection.commit()

updated_columns = [
    row[1]
    for row in connection.execute(
        "PRAGMA table_info(uploaded_document)"
    ).fetchall()
]

print("\nUpdated UploadedDocument columns:")
print(updated_columns)

connection.close()
