# DailyPapers

Personalized arXiv paper digest. AI scores the latest papers by your research interests and delivers them to your inbox every morning.

## Features

- **Daily arXiv fetch** — pulls the latest papers from your chosen categories (cs.CV, cs.AI, etc.)
- **AI deep scoring** — DeepSeek Pro reads full abstracts and scores papers 0–10 at temperature 0.0 for stability
- **Keyword pre-filter** — free regex step discards irrelevant papers and ranks the rest before AI scoring
- **Beautiful email** — responsive HTML cards with score badges, works on phone and desktop
- **Interactive TUI** — conversational terminal for adjusting keywords, slash commands supported
- **Zero-infra** — runs on GitHub Actions, no server needed

## Demo

**TUI** — conversational interest management with streaming AI:

```
  DailyPapers - Interest Manager
  Keywords (5): computer vision, video generation, diffusion models, ...
  Exclude  (3): nlp, reinforcement learning, robotics
  Categories: cs.CV, cs.AI
  Max/Day: 10  |  Min Score: 5

> add DiT
  thinking... DiT (Diffusion Transformer) represents a family of generative models
  that directly apply transformer architectures to the denoising process. Adding it
  would capture an important trend in your field.

  ✅ Added: DiT

> /quit
  Saved to config.yaml.
```

**Email report** — responsive HTML with score badges, open [demo/report.html](demo/report.html) in a browser to preview.

## Quick Start

### 1. Fork & Clone

```bash
git clone https://github.com/<your-username>/DailyPapers.git
cd DailyPapers
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with at minimum:

```yaml
user:
  email: your@gmail.com

profile:
  scholar_url: ''                # optional Google Scholar URL

interests:
  keywords_include:
    - video generation
    - diffusion models
    - computer vision
  keywords_exclude:
    - nlp
    - reinforcement learning
  categories:
    - cs.CV
    - cs.AI

daily:
  max_papers: 10
  min_relevance_score: 5
```

### 3. Test Locally

```bash
export OPENAI_API_KEY="sk-your-key"
export SMTP_PASSWORD="your-gmail-app-password"
python -m src.main
```

If you receive an email, the pipeline is working.

### 4. Deploy to GitHub Actions

```bash
gh secret set OPENAI_API_KEY   < ~/your-api-key-file
gh secret set SMTP_PASSWORD    < ~/your-smtp-password-file
```

Or set them via the web UI: Settings → Secrets and variables → Actions → New repository secret.

Push to `master`. The digest runs automatically at 12:00 Beijing time (UTC 04:00) on weekdays. Test it immediately:

```bash
gh workflow run daily.yml --ref master
```

## Configuration

All settings live in `config.yaml` (gitignored). See `config.example.yaml` for the full template (tracked).

### LLM Provider

```yaml
llm:
  api_key_env: OPENAI_API_KEY
  base_url: https://api.deepseek.com
  fast_model: deepseek-v4-flash   # chat / summaries / interest gen
  pro_model: deepseek-v4-pro      # deep scoring
  pro_temperature: 0.0            # deterministic scoring
```

To switch to OpenAI:
```yaml
llm:
  base_url: https://api.openai.com/v1
  fast_model: gpt-4o-mini
  pro_model: gpt-4o
```

### Scoring Parameters

```yaml
daily:
  max_papers: 10                  # max papers per digest
  min_relevance_score: 5          # score threshold (0–10)
  lookback_days: 1                # how many days to fetch
  keyword_prefilter_top: 60       # papers kept after regex filter
```

### Keyword Weights

```yaml
keyword_prefilter:
  title_exact_weight: 3           # word-boundary match in title
  title_partial_weight: 2         # substring match in title
  abstract_weight: 1              # match in abstract
```

## Usage

### Manage interests

```bash
python update.py
```

Opens an interactive terminal with slash commands:

| Command | Description |
|---|---|
| `/add kw1, kw2` | Add interest keywords |
| `/rm kw1, kw2` | Remove keywords |
| `/exclude kw1, kw2` | Add exclusion keywords |
| `/unexclude kw1, kw2` | Remove exclusion keywords |
| `/cats cs.CV, cs.AI` | Set arXiv categories |
| `/score 5` | Set minimum relevance score |
| `/max 10` | Set max papers per day |
| `/show` | Display current config |
| `/help` | Show all commands |
| `/quit` | Save and exit |

You can also use natural language: "add DiT, remove attention mechanism" — the AI parses your intent and updates config automatically.

### Initialize from Google Scholar

```bash
python setup.py
```

If `profile.scholar_url` is set in config, it fetches and analyzes your publications to generate initial keywords. If empty, it drops directly into the interactive TUI.

### Run manually

```bash
python -m src.main
```

Or click "Run workflow" on the GitHub Actions page.

## Pipeline

```
fetch_daily_papers()          arXiv API + local cache (.cache/)
      214 papers
  ↓  deduplicate via seen_papers.json
keyword_prefilter()           regex exclude + token match → top 60
  ↓
chat_final_score()            DeepSeek Pro, batch=30, temp=0.0
      score 0–10 with calibration anchors
      keep score ≥ min_relevance_score, top max_papers
  ↓
build_report()                Python → responsive HTML with score badges
  ↓
send_email()                  Gmail SMTP
  ↓
save_seen_ids()               update seen_papers.json
```

## Project Structure

```
src/
├── config.py              # YAML read/write
├── llm.py                 # LLMClient (OpenAI-compatible protocol)
├── main.py                # daily pipeline entrypoint
├── chat/
│   ├── engine.py          # AI conversation engine
│   └── terminal.py        # stdlib TUI (ANSI + readline + streaming)
├── pipeline/
│   ├── fetcher.py         # arXiv API + ArxivPaper + file cache
│   ├── filter.py          # keyword prefilter + LLM scoring
│   ├── summarizer.py      # LLM summarizer (standby)
│   └── notifier.py        # Gmail SMTP push
└── profile/
    ├── fetcher.py          # Semantic Scholar + Google Scholar
    └── generator.py        # LLM initial interest generation
```

## Environment Variables

| Variable | Used by |
|---|---|
| `OPENAI_API_KEY` | LLM API key |
| `SMTP_PASSWORD` | Gmail app password |

## Gmail App Password

1. Enable 2-step verification: https://myaccount.google.com/security
2. Create app password: https://myaccount.google.com/apppasswords
3. Select "Mail" → "Other" → name it `DailyPapers` → Generate
4. Set the 16-character password as `SMTP_PASSWORD`

## Tech Stack

- Python 3.11+ / pytest (181 tests, 95% coverage)
- DeepSeek API via OpenAI-compatible protocol (pluggable: GPT, Claude, etc.)
- arXiv API with local file caching
- Gmail SMTP
- Zero external TUI dependencies (stdlib ANSI + readline)

## License

MIT
