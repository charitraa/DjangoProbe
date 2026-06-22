# Contributing to DjangoProbe

Thanks for your interest in improving DjangoProbe! Contributions of all kinds
are welcome — bug reports, feature ideas, docs, and code.

## Getting set up

```bash
git clone https://github.com/charitraa/DjangoProbe.git
cd DjangoProbe
python3 -m venv env && source env/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env   # then add at least one provider API key
```

## Running the tool

```bash
djangoprobe /path/to/a/django/project
```

DjangoProbe operates on a cached copy of the target under
`~/.djangoprobe/cache/<name>` — your original project is never modified.

## Repo "tests"

The scripts under `tests/` are standalone smoke/integration scripts, **not**
pytest/unittest suites. Run them directly:

```bash
python tests/test_providers.py
```

Note that `tests/test_enhanced_analysis.py` and
`tests/test_django_specific_improvements.py` are not hermetic — they hardcode a
cached target path and require a configured AI provider.

## Pull requests

1. Fork the repo and create a feature branch (`git checkout -b feat/my-change`).
2. Keep changes focused; match the surrounding code style.
3. Describe **what** changed and **why** in the PR description.
4. If you change the data that flows between pipeline stages, update the
   dataclasses in `ai_tester/models.py` carefully — every stage depends on them.

## Where things live

- Pipeline orchestration: `ai_tester/cli.py`
- Endpoint discovery: `ai_tester/endpoint_scanner.py`
- Project analysis: `ai_tester/project_analyzer.py`
- Test generation (the core): `ai_tester/enhanced_test_generator.py`
- Test execution: `ai_tester/app_test_runner.py`
- Providers: `ai_tester/providers/`

See [CLAUDE.md](CLAUDE.md) for a deeper architecture walkthrough.

## Reporting bugs

Open a [GitHub issue](https://github.com/charitraa/DjangoProbe/issues) with:

- The command you ran and the target project layout (flat vs `apps.<name>`)
- The provider you used
- Relevant output (redact any API keys)

## License

By contributing, you agree that your contributions are licensed under the
project's [MIT License](LICENSE).
