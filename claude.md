# Claude Code Guidelines

## Development Principles

### KISS (Keep It Simple, Stupid)
- Write the simplest code that solves the problem
- Avoid clever solutions when straightforward ones work
- Prefer readable code over concise code
- Each function should do one thing well

### YAGNI (You Aren't Gonna Need It)
- Only implement features that are currently needed
- Don't add abstractions for hypothetical future use cases
- Avoid premature optimization
- Delete unused code rather than commenting it out

## Code Style
- No over-engineering or unnecessary complexity
- Minimal dependencies
- Clear, self-documenting code with comments only where logic isn't obvious
- Validate at system boundaries, trust internal code

## Security
- Never read or cache the .env file

## Commands
- Run tests: `poetry run pytest`
- Run a specific test file: `poetry run python <path>`
