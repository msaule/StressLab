# Contributing

StressLab values small, testable changes over broad speculative refactors.

## Development loop

```bash
pip install -e .[dev]
ruff check .
pytest
stresslab run examples/healthcare/ed_basic.yml
```

## Principles

- correctness before performance
- clarity before cleverness
- deterministic runs
- one responsibility per module
- user-facing errors should explain what to change

## Pull request checklist

- add or update tests
- keep public functions typed and documented
- preserve deterministic behavior under fixed seeds
- ensure the healthcare example still runs end to end
