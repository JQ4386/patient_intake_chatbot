# Assort Health Chatbot

A conversational AI-powered patient intake system for scheduling medical appointments. The chatbot guides patients through a structured workflow to collect information, validate addresses, and book appointments with healthcare providers.

## Features

- **Conversational Intake**: Natural language processing using OpenAI's GPT models for flexible, human-like interactions
- **Returning Patient Recognition**: Identifies existing patients by phone, email, or name+DOB and allows quick updates
- **Address Validation**: Google Maps API integration with retry logic and address suggestions
- **Provider Matching**: Recommends providers based on insurance acceptance and conditions treated
- **Appointment Booking**: Real-time availability checking and atomic booking
- **Audit Logging**: Complete change history for all patient data modifications

## Tech Stack

- **Python 3.12+**
- **OpenAI API** - LLM for natural language understanding and response generation
- **Google Maps Address Validation API** - Address verification and standardization
- **SQLite** - Lightweight database with foreign key constraints
- **Pydantic** - Data validation and structured output parsing
- **Poetry** - Dependency management

## Architecture

### State Machine

The chatbot uses a 17-state workflow:

```
START → GREET → CHECK_PATIENT
                    ├→ (Returning) CONFIRM_RETURNING → COLLECT_MEDICAL
                    └→ (New) COLLECT_PATIENT → CONFIRM_PATIENT
                                    ↓
                            COLLECT_INSURANCE → CONFIRM_INSURANCE
                                    ↓
                            COLLECT_ADDRESS → VALIDATE_ADDRESS → CONFIRM_ADDRESS
                                    ↓
                            COLLECT_MEDICAL
                                    ↓
                            QUERY_PROVIDERS → SELECT_PROVIDER → SELECT_TIME
                                    ↓
                                CONFIRM → END
```

### Core Modules

| Module | Purpose |
|--------|---------|
| `main.py` | Entry point and state handlers |
| `state_machine.py` | State definitions and transitions |
| `conversation.py` | LLM-based response generation |
| `slot_extractor.py` | Pydantic-based data extraction from user input |
| `address_validator.py` | Google Maps API integration |
| `patient_repository.py` | Patient CRUD with audit logging |
| `provider_repository.py` | Provider queries and appointment booking |

### Database Schema

| Table | Purpose |
|-------|---------|
| `patients` | Patient demographics, address, insurance |
| `patient_change_log` | Audit trail for all patient data changes |
| `visits` | Visit history with chief complaints and symptoms |
| `providers` | Provider info, specialties, accepted insurance |
| `appointments` | Available slots and booked appointments |

## API Integrations

### OpenAI API

Used for:
- **Slot Extraction**: Parsing user input to extract structured data (names, dates, addresses, etc.)
- **Intent Classification**: Detecting affirmative/negative responses, update requests
- **Response Generation**: Creating natural, context-aware conversational responses

Model: Configurable via `LLM_MODEL` environment variable (e.g., `gpt-4o-mini`, `gpt-5-mini`)

### Google Maps Address Validation API

- Validates complete addresses
- Returns standardized address components
- Provides address suggestions when input is ambiguous
- Retry logic: 2 attempts before proceeding with unvalidated address

## Conversation Flow

### New Patient Journey

1. Greeting and identification
2. Collect basic info (name, DOB, phone)
3. Confirm patient details
4. Collect insurance (payer, member ID)
5. Confirm insurance details
6. Collect address
7. Validate and confirm address
8. Collect chief complaint (reason for visit) → auto-queries matching providers
9. Select provider
10. Select appointment time
11. Final confirmation and booking

### Returning Patient Journey

1. Greeting and identification (matched by phone/email/name+DOB)
2. Display stored info and confirm accuracy
3. Allow updates with re-validation if needed
4. Collect chief complaint → auto-queries matching providers
5. Select provider and appointment time
6. Final confirmation and booking

## Data Extraction

The slot extractor uses Pydantic models with built-in validators:

- **Date normalization**: Converts `MM/DD/YYYY`, `MM-DD-YYYY` → `YYYY-MM-DD`
- **Phone normalization**: Extracts digits, handles 10/11-digit formats
- **State normalization**: Converts full state names to 2-letter codes

## Project Structure

```
assort-health-chatbot/
├── assort_intake_bot/
│   ├── main.py                  # Entry point and state handlers
│   ├── state_machine.py         # State definitions
│   ├── conversation.py          # Response generation
│   ├── slot_extractor.py        # Data extraction
│   ├── address_validator.py     # Address validation
│   ├── tools.py                 # Tool definitions
│   └── patient_intake/
│       ├── database/
│       │   ├── connection.py    # SQLite connection
│       │   ├── schema.py        # Schema definitions
│       │   ├── patient_repository.py
│       │   └── provider_repository.py
│       └── scripts/
│           └── seed_database.py # Mock data seeding
├── tests/                       # Test suite
├── pyproject.toml              # Poetry config
├── instructions.md             # Setup instructions
└── README.md                   # This file
```

## License

MIT
