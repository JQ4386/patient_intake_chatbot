"""Tool definitions and execution for the chatbot."""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "patient_intake" / "patient_intake.db"

# Tool definitions for OpenAI API
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": """Execute a SQL query against the SQLite database.

Tables:
- patients(id, first_name, last_name, date_of_birth, phone, email, address_line1, address_line2, city, state, zip_code, address_validated, insurance_payer, insurance_plan, insurance_member_id, insurance_group_id, created_at, updated_at)
- patient_change_log(id, patient_id, field_name, old_value, new_value, change_type, changed_at, changed_by)
- visits(id, patient_id, chief_complaint, symptoms, symptom_duration, severity, status, created_at, completed_at)

Use SELECT for queries, INSERT for new records, UPDATE for modifications.""",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The SQL query to execute"
                    }
                },
                "required": ["query"],
                "additionalProperties": False
            }
        }
    }
]


def execute_sql(query: str) -> str:
    """Execute a SQL query and return results as JSON."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(query)
        if query.strip().upper().startswith("SELECT"):
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return json.dumps({"columns": columns, "rows": results})
        else:
            conn.commit()
            return json.dumps({"affected_rows": cursor.rowcount})
    except Exception as e:
        return json.dumps({"error": str(e)})
    finally:
        conn.close()


# Map function names to actual functions
AVAILABLE_FUNCTIONS = {
    "execute_sql": execute_sql
}
