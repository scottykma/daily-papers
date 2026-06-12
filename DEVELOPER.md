# Developer Guide

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     setup.py (local)                         │
│  Google Scholar URL → profile_fetcher → interest_generator   │
│  → conversation (refine) → config.yaml                       │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                   update.py (local)                          │
│  conversation.py: natural language → config mutations        │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│               main.py (GitHub Actions, weekdays)             │
│  arxiv_fetcher → paper_filter → summarizer → notifier       │
└──────────────────────────────────────────────────────────────┘
```

## Module Roles

| Module | Responsibility | Key Dependencies |
|--------|---------------|------------------|
| `config.py` | YAML load/save/get/set, env var access | `pyyaml` |
| `arxiv_fetcher.py` | Query arXiv API, parse results into `ArxivPaper` | `arxiv` |
| `paper_filter.py` | Score papers (0-10) via DeepSeek against user interests | `openai` (DeepSeek) |
| `summarizer.py` | Generate Chinese summaries of top papers via DeepSeek | `openai` (DeepSeek) |
| `notifier.py` | Push via SMTP (Email) | `smtplib` |
| `profile_fetcher.py` | Parse Google Scholar profile, extract publications | `scholarly` |
| `interest_generator.py` | Generate keyword config from scholar profile via DeepSeek | `openai` (DeepSeek) |
| `conversation.py` | CLI conversation loop, DeepSeek parses user intent → config ops | `openai`, `rich` |

## Data Flow (Daily Run)

```
fetch_daily_papers(categories, lookback_days)
    │
    ├── Returns list[ArxivPaper]
    │
    ▼
filter_papers(papers, max_papers, min_score, seen_ids)
    │
    ├── Returns list[tuple[ArxivPaper, int, str]]  # (paper, score, reason)
    │
    ▼
summarize_papers(filtered)
    │
    ├── Returns list[dict]  # {paper, score, reason, summary, keywords}
    │
    ▼
build_report(summarized) → markdown string
    │
    ▼
send_report(title, markdown) → Email
```

## Testing

```bash
# Install dev dependencies + venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run only unit tests
pytest tests/ -v -m unit

# Run with coverage
pip install pytest-cov
pytest tests/ -v --cov=src --cov-report=html
```

### Test Structure

```
tests/
├── conftest.py           # Shared fixtures (temp_config_dir, mock_env, sample_arxiv_result)
├── test_config.py        # 9 tests: load, get, set, save, env
├── test_arxiv_fetcher.py # 10 tests: ArxivPaper, fetch_daily_papers
├── test_paper_filter.py  # 7 tests: scoring, filtering, threshold
├── test_summarizer.py    # 4 tests: summary generation, fallback
├── test_notifier.py      # 17 tests: wechat, email, markdown→html
├── test_profile_fetcher.py # 9 tests: url parsing, profile fetching
├── test_interest_generator.py # 4 tests: interest generation
├── test_conversation.py  # 14 tests: config mutation actions
└── test_main.py          # 10 tests: report building, seen_ids, integration
```

### Testing Patterns

- **Unit tests** mock all external dependencies (arXiv API, DeepSeek API, SMTP, HTTP)
- The LLM client is centralized in `llm.py` (`LLMClient`, `get_fast`, `get_pro`). All modules that use DeepSeek/OpenAI import from `src.llm`.
- **Integration test** (`test_run_full_pipeline`) mocks all submodules to verify orchestration
- **Config tests** use `temp_config_dir` fixture to create temp YAML files
- **API tests** use `mock_env` fixture to patch `os.environ` with `OPENAI_API_KEY` and `SMTP_PASSWORD`

## Adding a New Feature

1. Create module in `src/`
2. Create tests in `tests/`
3. Update `pyproject.toml` if adding new dependencies
4. Run `pytest tests/` to verify

### Example: Adding a new notification channel

```
src/notifiers/telegram.py    # send_telegram(title, content)
tests/test_telegram.py       # TestSendTelegram class
src/notifier.py              # Add to send_report() dict
```

## Configuration Secrets

All secrets are read from environment variables (GitHub Actions Secrets):

| Variable | Used by |
|----------|---------|
| `OPENAI_API_KEY` | llm.py (paper_filter, summarizer, interest_generator, conversation) |
| `SMTP_PASSWORD` | notifier (Email) |

Config values in `config.yaml` are read by `config.get("path.to.key", default)`.

## Code Conventions

- Type hints on all public functions
- Module-level `logger = logging.getLogger(__name__)`
- All external API calls wrapped in try/except with log
- No comments in source code (self-documenting)
- 3rd-party imports grouped first, then local imports
