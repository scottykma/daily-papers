import json
import logging
from datetime import datetime
from pathlib import Path

from src.pipeline.fetcher import ArxivPaper, fetch_daily_papers
from src.config import get, reload
from src.pipeline.notifier import send_report
from src.pipeline.filter import chat_final_score, keyword_prefilter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

ROOT = Path(__file__).resolve().parent.parent
SEEN_PATH = ROOT / "seen_papers.json"


def load_seen_ids() -> set[str]:
    if not SEEN_PATH.exists():
        return set()
    try:
        with open(SEEN_PATH, "r") as f:
            data = json.load(f)
            return set(data.get("ids", []))
    except (json.JSONDecodeError, KeyError):
        return set()


def save_seen_ids(papers: list[ArxivPaper], seen_ids: set[str]) -> None:
    all_ids = seen_ids | {p.arxiv_id for p in papers}
    with open(SEEN_PATH, "w") as f:
        json.dump({"ids": sorted(all_ids), "updated": datetime.now().isoformat()}, f)
    logger.info("Saved %d seen paper IDs", len(all_ids))


def _score_color(score: int) -> str:
    if score >= get("report.score_green", 8):
        return "#2ecc71"
    if score >= get("report.score_orange", 5):
        return "#f39c12"
    return "#e74c3c"


def build_report(scored: list[tuple[ArxivPaper, int, str]]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    user_name = get("profile.name") or get("user.name", "Researcher")
    categories = ", ".join(get("interests.categories", []))

    css = (
        "body{margin:0;padding:0;background:#f5f6fa;font-family:-apple-system,BlinkMacSystemFont,"
        "'Segoe UI',Helvetica,Arial,sans-serif;color:#2c3e50}"
        ".container{max-width:960px;margin:0 auto;padding:28px 0}"
        ".section{margin:0 24px}"
        ".header{background:linear-gradient(135deg,#2c3e50,#3498db);color:#fff;padding:36px 28px;"
        "border-radius:10px 10px 0 0;text-align:center}"
        ".header h1{margin:0 0 8px;font-size:26px;font-weight:700;letter-spacing:.5px}"
        ".header p{margin:0;opacity:.85;font-size:15px}"
        ".count{background:#fff;padding:18px 28px;text-align:center;border-bottom:1px solid #e8eaed}"
        ".count span{background:#ecf0f1;padding:5px 16px;border-radius:14px;font-size:14px;font-weight:600}"
        ".papers{display:grid;gap:18px;padding:24px 0}"
        ".card{background:#fff;border-radius:10px;overflow:hidden;"
        "box-shadow:0 1px 4px rgba(0,0,0,.06);transition:box-shadow .2s}"
        ".card:hover{box-shadow:0 2px 8px rgba(0,0,0,.12)}"
        ".card-top{padding:22px 28px 8px}"
        ".card h3{margin:0 0 8px;font-size:15px;line-height:1.5;color:#2c3e50;font-weight:600}"
        ".score{display:inline-block;padding:3px 12px;border-radius:4px;font-size:12px;"
        "font-weight:700;color:#fff;margin-bottom:10px;text-transform:uppercase;letter-spacing:.3px}"
        ".meta{padding:0 28px 12px}"
        ".meta li{list-style:none;margin:5px 0;font-size:13px;line-height:1.6}"
        ".meta strong{color:#2c3e50;display:inline-block;min-width:64px;font-size:12px;text-transform:uppercase;letter-spacing:.3px}"
        ".meta a{color:#3498db;text-decoration:none}"
        ".abstract{padding:14px 28px 22px;font-size:14px;line-height:1.75;color:#555;"
        "border-top:1px solid #f0f0f0;margin:0 28px}"
        ".footer{text-align:center;padding:28px 0;color:#95a5a6;font-size:12px}"
        "@media(max-width:600px){"
        ".container{padding:12px 0}"
        ".section{margin:0 8px}"
        ".header{padding:24px 16px;border-radius:6px 6px 0 0}"
        ".header h1{font-size:20px}"
        ".header p{font-size:13px}"
        ".card{border-radius:6px}"
        ".card-top{padding:16px 20px 6px}"
        ".card h3{font-size:14px}"
        ".meta{padding:0 20px 10px}"
        ".meta li{font-size:12px}"
        ".abstract{padding:12px 20px 16px;margin:0 20px;font-size:13px}"
        ".papers{padding:16px 0;gap:12px}"
        ".count{padding:14px 16px}"
        "}"
    )

    lines = [
        "<html><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
        f"<style>{css}</style></head>",
        "<body>",
        "<div class=\"container\">",
        "<div class=\"header section\">",
        "<h1>Daily arXiv Digest</h1>",
        f"<p>{today} &middot; {user_name} &middot; {categories}</p>",
        "</div>",
        "<div class=\"count section\">",
        f"<span>{len(scored)} papers selected</span>",
        "</div>",
        "<div class=\"papers section\">",
    ]

    for i, (paper, score, reason) in enumerate(scored, 1):
        lines.append("<div class=\"card\">")
        lines.append("<div class=\"card-top\">")
        lines.append(f"<div class=\"score\" style=\"background:{_score_color(score)}\">Score {score}/10</div>")
        lines.append(f"<h3>{i}. {paper.title}</h3>")
        lines.append("</div>")

        lines.append("<div class=\"meta\">")
        lines.append("<ul>")
        lines.append(f"<li><strong>Authors</strong> {', '.join(paper.authors[:5])}</li>")
        lines.append(f"<li><strong>Reason</strong> {reason}</li>")
        lines.append(f"<li><strong>arXiv</strong> <a href=\"{paper.url}\">{paper.arxiv_id}</a> &middot; {', '.join(paper.categories)}</li>")
        if paper.comment:
            lines.append(f"<li><strong>Note</strong> {paper.comment}</li>")
        lines.append("</ul></div>")

        lines.append(f"<div class=\"abstract\">{paper.abstract}</div>")
        lines.append("</div>")

    lines.extend([
        "</div>",
        "<div class=\"footer section\">",
        f"Generated by DailyPapers &middot; {today}",
        "</div>",
        "</div>",
        "</body></html>",
    ])

    return "\n".join(lines)


def run() -> None:
    reload()
    logger.info("=== DailyPapers run started ===")

    papers = fetch_daily_papers()
    if not papers:
        logger.info("No new papers found today")
        return

    seen_ids = load_seen_ids()
    papers = [p for p in papers if p.arxiv_id not in seen_ids]
    if not papers:
        logger.info("All papers already seen, nothing new")
        return
    logger.info("New unseen papers: %d", len(papers))

    pre_exclude = papers
    papers = keyword_prefilter(papers)
    if not papers:
        logger.info("No papers passed keyword filter")
        save_seen_ids(pre_exclude, seen_ids)
        return
    logger.info("After keyword filter: %d papers", len(papers))

    scored_input = [(p, 0, "") for p in papers]
    filtered = chat_final_score(scored_input)
    if not filtered:
        logger.info("No papers passed final scoring (all below threshold)")
        save_seen_ids(papers, seen_ids)
        return

    title = f"arXiv Digest - {datetime.now().strftime('%m/%d')}"
    report = build_report(filtered)

    results = send_report(title, report)
    logger.info("Email sent: %s", results.get("email", False))

    save_seen_ids(papers, seen_ids)
    logger.info("=== DailyPapers run completed ===")


if __name__ == "__main__":
    run()
