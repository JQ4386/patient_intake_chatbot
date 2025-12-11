"""Shared pytest fixtures."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def mock_llm_responses():
    """Mock LLM responses to avoid API calls during tests."""
    with patch("assort_intake_bot.conversation.generate_llm_response") as mock_llm, \
         patch("assort_intake_bot.main.generate_llm_response") as mock_llm_main, \
         patch("assort_intake_bot.conversation.interpret_selection") as mock_interpret, \
         patch("assort_intake_bot.main.interpret_selection") as mock_interpret_main:
        # Return a simple mock response that varies based on task
        def mock_response(state, user_input, task, data_to_present=None):
            # Return a contextual mock response based on the task
            task_lower = task.lower()

            if "greet" in task_lower:
                return "Hi! Welcome to Assort Health. Have you visited us before?"
            if "welcome back" in task_lower or "returning" in task_lower:
                return "Welcome back! Here's your info on file. Is this still correct?"
            if "insurance" in task_lower and "confirm" in task_lower:
                return "Here's your insurance info. Is this correct?"
            if "insurance" in task_lower:
                return "Could you share your insurance info?"
            if "address" in task_lower and "confirm" in task_lower:
                return "Here's your address. Is this correct?"
            if "address" in task_lower:
                return "What's your home address?"
            if "confirm" in task_lower and "patient" in task_lower:
                return "Here's your info. Is this correct?"
            if "registered" in task_lower or "basic info" in task_lower:
                return "Let's get you registered. What's your name, DOB, and phone?"
            if "remaining info" in task_lower:
                return "Thanks! I still need a few more details."
            if "medical" in task_lower or "reason" in task_lower or "brings" in task_lower:
                return "What brings you in today?"
            if "empathy" in task_lower or "discomfort" in task_lower:
                return "I'm sorry to hear that. Let me find you a great provider."
            if "no available" in task_lower or "has no" in task_lower:
                return "Sorry, that provider has no available slots. Please select another provider."
            if "couldn't understand" in task_lower or "couldn't tell" in task_lower:
                return "I didn't quite catch that. Please pick from the list."
            if "provider" in task_lower:
                return "Here are available providers. Please pick one."
            if "time" in task_lower:
                return "Here are available times. Please pick one."
            if "summary" in task_lower or "final" in task_lower:
                return "Here's your appointment summary. Confirm to book."
            if "thank" in task_lower or "booked" in task_lower:
                return "Your appointment is booked! Take care!"
            if "look" in task_lower and "up" in task_lower:
                return "Sure! What's your phone number or name and DOB?"
            return "How can I help you?"

        def mock_interpret_selection(user_input, options, option_type):
            """Mock selection interpretation - return selection based on input."""
            if not options:
                return None
            user_lower = user_input.lower().strip()
            # Simple number matching for tests
            for i in range(1, len(options) + 1):
                if user_lower == str(i):
                    return i - 1
            # For "yes", "first", etc., return first option
            if user_lower in ("yes", "yep", "first", "1"):
                return 0
            # Check for provider name mentions
            if option_type == "provider":
                for i, opt in enumerate(options):
                    if opt.get("name", "").lower() in user_lower:
                        return i
            # Check for date/time mentions
            if option_type == "time":
                for i, opt in enumerate(options):
                    if opt.get("date", "") in user_input or opt.get("time", "") in user_input:
                        return i
            # Invalid/unclear input - return None
            return None

        mock_llm.side_effect = mock_response
        mock_llm_main.side_effect = mock_response
        mock_interpret.side_effect = mock_interpret_selection
        mock_interpret_main.side_effect = mock_interpret_selection
        yield mock_llm
