# AGENTS.md

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

All commands below assume the venv is active.

## Run Tests

```bash
pytest tests/ -v                          # all 230 tests
pytest tests/ -v -m unit                  # skip integration
pip install pytest-cov && pytest tests/ --cov=src --cov-fail-under=95
```

### Coverage

- **95%+ line coverage** mandatory across all of `src/`.
- New module → new `tests/test_<module>.py`.
- New public function → at least one test.
- All tests must pass before push.

### Test Structure

- One test class per feature: `Test<Feature>` with `@pytest.mark.unit` or `@pytest.mark.integration`.
- Shared fixtures in `tests/conftest.py` (`temp_config_dir`, `mock_env`, `sample_arxiv_result`).
- External I/O (arXiv, LLM, SMTP, HTTP) always mocked in unit tests.
- Integration tests mock sub-module boundaries, verify pipeline orchestration.

## Common Commands

```bash
python setup.py               # setup wizard (reads profile.scholar_url from config.yaml)
python update.py              # conversational interest management (TUI)
python -m src.main            # manual daily run (needs OPENAI_API_KEY + SMTP_PASSWORD)
```

## Architecture

```
src/
├── config.py              # YAML read/write (get/set/save), env var helpers
├── llm.py                 # LLMClient (OpenAI-compatible), get_fast/get_pro singletons
├── main.py                # daily pipeline entrypoint
├── chat/
│   ├── engine.py          # conversation agent (system prompt + streaming + actions)
│   ├── screen.py          # ANSI Screen class (incremental rendering, no full clears)
│   └── terminal.py        # TUI using Screen (ANSI + readline + streaming output)
├── pipeline/
│   ├── fetcher.py         # arXiv API + ArxivPaper + file cache (.cache/)
│   ├── filter.py          # keyword_prefilter (regex) + chat_final_score (LLM pro)
│   ├── summarizer.py      # LLM paper summarizer (standby, not used in daily run)
│   └── notifier.py        # Gmail SMTP email push
└── profile/
    ├── fetcher.py          # Semantic Scholar + Google Scholar profile fetching
    └── generator.py        # LLM interest keyword generation
```

### Pipeline Flow

```
fetch_daily_papers()         arXiv + .cache/ file cache (same-day reuse)
    ↓ 去重 seen_papers.json
keyword_prefilter()          regex: exclude keywords → discard; include token match → score → top 60
    ↓
chat_final_score()           LLM pro, batch=30, temp=0.0, 5-level calibration anchors
    ↓                          score ≥ min_relevance_score, top max_papers
build_report()               Python → HTML template (card layout, score badges, responsive)
    ↓
send_email()                 Gmail SMTP
    ↓
save_seen_ids()              seen_papers.json
```

### TUI

- `Screen` class (`chat/screen.py`) manages incremental ANSI rendering — no `_clear_screen()`.
  - `render_header()` prints config once (no-op on subsequent calls).
  - `show_thinking()` / `hide_thinking()` display/dismiss "Thinking..." indicator.
  - `write()` / `writeln()` stream tokens incrementally.
  - `show_actions()` prints action results with icons.
  - `show_config_status()` prints compact status bar after config changes.
- `_stream_ai_response()` accepts optional `screen` parameter. Reasoning content is suppressed.
- `httpx` logger set to `WARNING` in all entry points (`main.py`, `setup.py`, `update.py`).

### Config

- `config.yaml` is **gitignored** (contains personal data). `config.example.yaml` is tracked as template.
- Read: `config.get("path.to.key", default)`, write: `config.set(...)` then `config.save()`.
- `config.py` caches YAML. Call `reload()` before fresh pipeline runs (`main.py` does this).
- All tunables (LLM models, temperatures, batch sizes, weights, paths, SMTP) are in `config.yaml`.

## Environment Variables

| Variable | Used by |
|---|---|
| `OPENAI_API_KEY` | `src/llm.py` (all LLM calls) |
| `SMTP_PASSWORD` | `src/pipeline/notifier.py` (email push) |

No module-level API key constants. They read from env via `config.get_env()`.

## Testing Gotchas

- `LLMClient` reads `OPENAI_API_KEY` from `os.environ` at init. `mock_env` fixture sets this.
- `get_fast()` / `get_pro()` return **cached singletons**. Reset `src.llm._fast_instance = None` before tests that mock them.
- Mock LLM clients by patching the **importing module's** `get_fast`/`get_pro` (e.g. `monkeypatch.setattr("src.pipeline.filter.get_fast", lambda: mock)`), not `src.llm.get_fast` directly.
- The `parse_response_stream` and `_parse_stream` functions in `chat/engine.py` are often mocked directly in tui tests rather than mocking the LLM client.
- `sample_arxiv_result` creates author mocks with explicit `.name = "..."` (not `MagicMock(name=...)`), since `MagicMock.name` returns a MagicMock.
- Profile fetcher tests must mock `requests.get` (Semantic Scholar) and `_fetch_from_google_scholar`.

## Development Style

- Python 3.11+, type hints on public function signatures.
- `logger = logging.getLogger(__name__)`, never `print` (except TUI which uses `print`/`input` by design).
- Third-party imports first, then stdlib, then local `src.*` imports (blank line between groups).
- No comments in source code. Self-documenting names.
- Functions over classes (exceptions: `ArxivPaper`, `ScholarProfile`, `LLMClient`).

## Security

- `config.yaml` is gitignored. Never commit it.
- API keys via environment variables only, never in source or config.
- No hardcoded local paths; all paths configurable in `config.yaml` under `paths.*`.
- Git history was cleaned of personal data; force push required if rewriting.
