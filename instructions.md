# Setup and Run Instructions

## Prerequisites

- Python 3.12 or higher
- [Poetry](https://python-poetry.org/) for dependency management
- OpenAI API key
- Google Maps API key (with Address Validation API enabled)

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd assort-health-chatbot
```

### 2. Install Dependencies

```bash
poetry install
```

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```bash
OPENAI_API_KEY=your_openai_api_key_here
MAP_API_KEY=your_google_maps_api_key_here
LLM_MODEL=gpt-5-mini  # Optional, defaults to gpt-4o-mini
```

**API Key Setup:**

- **OpenAI API Key**: Get one from [OpenAI Platform](https://platform.openai.com/api-keys)
- **Google Maps API Key**:
  1. Go to [Google Cloud Console](https://console.cloud.google.com/)
  2. Create a project or select an existing one
  3. Enable the "Address Validation API"
  4. Create an API key in "Credentials"

### 4. Seed the Database

Populate the database with sample providers and appointment slots:

```bash
poetry run python assort_intake_bot/patient_intake/scripts/seed_database.py
```

This creates:
- Sample healthcare providers with various specialties
- Available appointment slots for the next 14 days
- Test patient records (optional)

## Running the Chatbot

Start the interactive chatbot:

```bash
poetry run python assort_intake_bot/main.py
```

Type `quit` or `exit` to end the session.

---

## Complete Conversation Flow Example

The chatbot follows a state machine with 17 states. Below is a complete example conversation for a **new patient** going through the entire intake process.

### State Machine Overview

```
START → GREET → CHECK_PATIENT
                    ├→ (Returning) CONFIRM_RETURNING → COLLECT_MEDICAL ─┐
                    └→ (New) COLLECT_PATIENT → CONFIRM_PATIENT          │
                                    ↓                                   │
                            COLLECT_INSURANCE → CONFIRM_INSURANCE       │
                                    ↓                                   │
                            COLLECT_ADDRESS → VALIDATE_ADDRESS          │
                                    ↓                                   │
                            CONFIRM_ADDRESS → COLLECT_MEDICAL ──────────┤
                                                                        ↓
                                              (auto-query) → SELECT_PROVIDER → SELECT_TIME
                                                                        ↓
                                                                    CONFIRM → END
```

Note: After collecting the chief complaint, the system automatically queries providers
and transitions directly to SELECT_PROVIDER (skipping the explicit QUERY_PROVIDERS state).

### New Patient Complete Journey

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  STATE: GREET → CHECK_PATIENT                                               │
└─────────────────────────────────────────────────────────────────────────────┘

Bot: Hello! Welcome to Assort Health. I'm here to help you schedule an
     appointment. Have you visited us before?

You: No, I'm a new patient

┌─────────────────────────────────────────────────────────────────────────────┐
│  STATE: CHECK_PATIENT → COLLECT_PATIENT                                     │
│  (User identified as new patient)                                           │
└─────────────────────────────────────────────────────────────────────────────┘

Bot: Great! Let's get you set up. Could you please provide your first name,
     last name, date of birth, and phone number?

You: I'm Jane Smith, born May 20 1988, my phone is 555-987-6543

┌─────────────────────────────────────────────────────────────────────────────┐
│  STATE: COLLECT_PATIENT → CONFIRM_PATIENT                                   │
│  (All required fields collected: first_name, last_name, date_of_birth,      │
│   phone)                                                                    │
└─────────────────────────────────────────────────────────────────────────────┘

Bot: Thanks! Let me confirm your information:

     - Name: Jane Smith
     - Date of Birth: May 20, 1988
     - Phone: (555) 987-6543

     Is this correct?

You: yes

┌─────────────────────────────────────────────────────────────────────────────┐
│  STATE: CONFIRM_PATIENT → COLLECT_INSURANCE                                 │
└─────────────────────────────────────────────────────────────────────────────┘

Bot: Now I'll need your insurance information. What is your insurance provider
     and member ID?

You: Blue Cross PPO, member ID BC987654

┌─────────────────────────────────────────────────────────────────────────────┐
│  STATE: COLLECT_INSURANCE → CONFIRM_INSURANCE                               │
│  (Required fields: insurance_payer, insurance_member_id)                    │
└─────────────────────────────────────────────────────────────────────────────┘

Bot: Got it! Here's what I have for your insurance:

     - Insurance: Blue Cross PPO
     - Member ID: BC987654

     Is this correct?

You: yes

┌─────────────────────────────────────────────────────────────────────────────┐
│  STATE: CONFIRM_INSURANCE → COLLECT_ADDRESS                                 │
└─────────────────────────────────────────────────────────────────────────────┘

Bot: Now I'll need your address. Please provide your street address, city,
     state, and ZIP code.

You: 456 Oak Street, San Francisco CA 94110

┌─────────────────────────────────────────────────────────────────────────────┐
│  STATE: COLLECT_ADDRESS → VALIDATE_ADDRESS                                  │
│  (Google Maps API validates address)                                        │
└─────────────────────────────────────────────────────────────────────────────┘

Bot: Your address has been verified. Here's what I have:

     - Address: 456 Oak Street
     - City: San Francisco
     - State: CA
     - ZIP: 94110

     Is this correct?

You: yes

┌─────────────────────────────────────────────────────────────────────────────┐
│  STATE: CONFIRM_ADDRESS → COLLECT_MEDICAL                                   │
└─────────────────────────────────────────────────────────────────────────────┘

Bot: What brings you in today? Please describe your symptoms or reason for
     the visit.

You: I've been having back pain for about a week

┌─────────────────────────────────────────────────────────────────────────────┐
│  STATE: COLLECT_MEDICAL → SELECT_PROVIDER                                   │
│  (Chief complaint recorded, auto-queries providers and shows results)       │
└─────────────────────────────────────────────────────────────────────────────┘

Bot: I understand you're experiencing back pain. Let me find providers who
     can help...

     I found these providers who accept Blue Cross and treat back pain:

     1. Dr. Sarah Johnson - Family Medicine (Rating: 4.9)
     2. Dr. Michael Chen - Internal Medicine (Rating: 4.7)
     3. Dr. Emily Brown - Family Medicine (Rating: 4.8)

     Please select a provider by number or name.

You: 1

┌─────────────────────────────────────────────────────────────────────────────┐
│  STATE: SELECT_PROVIDER → SELECT_TIME                                       │
│  (Provider selected, fetching available appointments)                       │
└─────────────────────────────────────────────────────────────────────────────┘

Bot: Great choice! Dr. Sarah Johnson is an excellent provider.

     Here are the available appointment times:

     1. Tomorrow, December 4 at 9:00 AM
     2. Tomorrow, December 4 at 10:00 AM
     3. Tomorrow, December 4 at 2:00 PM
     4. Friday, December 6 at 11:00 AM
     5. Friday, December 6 at 3:00 PM

     Which time works best for you?

You: 2

┌─────────────────────────────────────────────────────────────────────────────┐
│  STATE: SELECT_TIME → CONFIRM                                               │
│  (Time slot selected, ready for final confirmation)                         │
└─────────────────────────────────────────────────────────────────────────────┘

Bot: Please confirm your appointment:

     **Patient:** Jane Smith
     **Provider:** Dr. Sarah Johnson
     **Date:** Tomorrow, December 4, 2024
     **Time:** 10:00 AM
     **Reason:** Back pain

     **Address on file:**
     456 Oak Street
     San Francisco, CA 94110

     **Insurance:** Blue Cross PPO (BC987654)

     Is everything correct?

You: yes

┌─────────────────────────────────────────────────────────────────────────────┐
│  STATE: CONFIRM → END                                                       │
│  (Patient and visit records saved, appointment booked)                      │
└─────────────────────────────────────────────────────────────────────────────┘

Bot: Your appointment has been confirmed! You're all set to see Dr. Sarah
     Johnson on December 4 at 10:00 AM.

     Please arrive 15 minutes early to complete any paperwork. If you need
     to reschedule, please call our office.

     Thank you for choosing Assort Health!
```

### Returning Patient Journey (Shorter Flow)

Returning patients skip the basic info collection:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  STATE: CHECK_PATIENT → CONFIRM_RETURNING                                   │
└─────────────────────────────────────────────────────────────────────────────┘

Bot: Hello! Welcome to Assort Health. Have you visited us before?

You: Yes, my phone number is 555-123-4567

Bot: Welcome back, John! I found your records:

     - Name: John Doe
     - Address: 123 Main St, San Francisco, CA 94102
     - Insurance: Blue Cross (BC123456)

     Is this information still correct, or would you like to update anything?

You: I have a new phone number: 555-999-8888

Bot: Got it! I've updated your phone number to (555) 999-8888.
     Anything else to update?

You: No, that's all

┌─────────────────────────────────────────────────────────────────────────────┐
│  STATE: CONFIRM_RETURNING → COLLECT_MEDICAL                                 │
│  (Skips patient, insurance, and address collection)                         │
└─────────────────────────────────────────────────────────────────────────────┘

Bot: What brings you in today?

You: I have a headache

┌─────────────────────────────────────────────────────────────────────────────┐
│  STATE: COLLECT_MEDICAL → SELECT_PROVIDER                                   │
│  (Auto-queries providers based on insurance + condition)                    │
└─────────────────────────────────────────────────────────────────────────────┘

Bot: I understand you're experiencing a headache. Let me find providers...

     I found these providers who can help:

     1. Dr. Sarah Johnson - Family Medicine (Rating: 4.9)
     2. Dr. Michael Chen - Internal Medicine (Rating: 4.7)

     Please select a provider by number or name.

[...continues to SELECT_TIME → CONFIRM → END]
```

### Address Validation with Correction

When address validation fails:

```
You: 123 Mian Street, San Francisco CA 94102

Bot: The address "123 Mian Street, San Francisco, CA 94102" could not be verified.

     Did you mean: **123 Main Street, San Francisco, CA 94102, USA**?

     Reply 'yes' to use this address, or provide the correct address.

You: yes

Bot: Great! I've updated your address to: 123 Main Street, San Francisco, CA 94102

     Is this correct?
```

---

## Running Tests

Run the full test suite:

```bash
poetry run pytest
```

Run a specific test file:

```bash
poetry run pytest tests/test_conversation_flows.py
```

Run with verbose output:

```bash
poetry run pytest -v
```

### Test Coverage

The test suite covers:

| Test File | Coverage |
|-----------|----------|
| `test_main.py` | State handlers and transitions |
| `test_conversation_flows.py` | End-to-end patient journeys |
| `test_patient_repository.py` | Patient CRUD and audit logging |
| `test_provider_repository.py` | Provider queries and appointments |
| `test_address_validator.py` | Address validation logic |

---

## Troubleshooting

### "OPENAI_API_KEY not set"

Ensure your `.env` file exists in the project root and contains a valid API key.

### "Address validation failed"

- Check that your `MAP_API_KEY` is valid
- Ensure the Address Validation API is enabled in Google Cloud Console
- The chatbot will proceed after 2 failed validation attempts

### "No providers found"

Run the database seed script to populate providers:

```bash
poetry run python assort_intake_bot/patient_intake/scripts/seed_database.py
```

### Database Issues

Delete the database file to reset:

```bash
rm assort_intake_bot/patient_intake/patient_intake.db
poetry run python assort_intake_bot/patient_intake/scripts/seed_database.py
```

---

## Development

### Project Structure

- `assort_intake_bot/` - Main application code
- `tests/` - Test suite
- `pyproject.toml` - Dependencies and project config
- `CLAUDE.md` - Development guidelines

### Adding New States

1. Add state to `State` enum in `state_machine.py`
2. Create handler function in `main.py`
3. Register handler in `STATE_HANDLERS` dict
4. Update transition logic in `get_next_state()`

### Modifying Data Extraction

Edit `slot_extractor.py` to:
- Add new fields to `ExtractedSlots` model
- Add validators for new field types
- Update extraction prompts
