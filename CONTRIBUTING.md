# Contributing to Dredge

We welcome contributions! Please follow these guidelines:

## Development Workflow

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes using [Conventional Commits](https://www.conventionalcommits.org/)
4. **Test** your changes (`pytest tests/`)
5. **Push** to your branch (`git push origin feature/amazing-feature`)
6. **Open** a Pull Request

## Commit Message Format

```
<type>(<scope>): <subject>

<body>
```

**Types:** feat, fix, docs, style, refactor, test, chore

**Example:**
```
feat(finops): add GCP pricing support

- Add GCP_PRICE_PER_GB constant
- Update calculate_monthly_cost() to support GCP
- Add unit tests for GCP pricing
```

## Code Style

- Follow **PEP 8** guidelines
- Use **type hints** everywhere
- Write **docstrings** for all public functions
- Maintain **100% test coverage** for new features
- Pass **all linters** (ruff, mypy, bandit)

## Testing

Before submitting a pull request, ensure all tests pass:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run code quality checks
ruff check app/
mypy app/
bandit -r app/
```

## Questions?

Open an issue on GitHub if you need help or have questions about contributing.
