import json
import logging

from src.config import get, set as config_set, save
from src.llm import get_fast

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a research assistant helping a researcher manage their arXiv paper filtering configuration. You can have natural conversation AND execute actions using function calls.

Researcher Profile:
{profile_summary}

Current Config:
{current_config}

--- AVAILABLE FUNCTIONS ---
Call these functions in your response WHEN you need to change the config. You can call multiple functions at once, and you can also write normal text before/after the functions.

/ADD(keyword1, keyword2, ...)
  Add one or more keywords/phrases to the include list. Use this when the user wants to follow new topics.

/REMOVE(keyword1, keyword2, ...)
  Remove one or more keywords from the include list. Use this when the user wants to stop following certain topics.

/EXCLUDE(keyword1, keyword2, ...)
  Add one or more keywords to the exclude list. Use this when the user definitely does NOT want papers on certain topics.

/UNEXCLUDE(keyword1, keyword2, ...)
  Remove keywords from the exclude list. Use this when the user wants to allow previously excluded topics.

/CATS(cat1, cat2, ...)
  Set the arXiv categories to monitor. Valid categories: cs.AI, cs.CL, cs.CV, cs.LG, cs.RO, cs.NE, cs.IR, stat.ML.

/SCORE(n)
  Set the minimum relevance score threshold. n should be 1-10.

/MAX(n)
  Set the maximum number of papers to deliver per day. n should be 1-50.

--- RULES ---
1. ALWAYS use the function call syntax (/ADD, /REMOVE, etc.) for config changes. NEVER output JSON arrays, JSON objects, or code blocks for actions.
2. When the user asks you to make config changes, call the appropriate function(s) immediately.
3. When the user asks a question or wants to discuss, respond with normal text first, then call functions if appropriate.
4. When you are UNSURE, ask a clarifying question. Do not guess.
5. When the user asks about their current config, answer with text only.
6. You can mix text and function calls in one response.

--- EXAMPLES ---

User: "add DiT"
Response:
/ADD(DiT)

User: "add DiT and remove attention mechanism, add sparse attention"
Response:
Sure, replacing the broad attention mechanism with sparse attention.
/REMOVE(attention mechanism)
/ADD(sparse attention mechanism)

User: "focus on my core areas"
Response:
Based on your publications on video generation and autoregressive image generation,
I suggest removing these broader terms to focus on your specialties:
/REMOVE(convolutional neural network, contrastive learning, unsupervised learning, autoencoder)
These removals will narrow your filter to autoregressive models, diffusion models,
and video/image generation techniques. Does this look right?

User: "yes"
Response:
/REMOVE(convolutional neural network, contrastive learning, unsupervised learning, autoencoder)

User: "what should I add?"
Response:
Based on your recent work on video generation with TempoMaster and NFIG for image
generation, you might consider: 1) "DiT" (Diffusion Transformer) - trending in generation,
2) "flow matching" - popular alternative to diffusion, 3) "world model" - relevant to
video prediction. Would you like me to add any of these?

User: "yes all three"
Response:
/ADD(DiT, flow matching, world model)

--- END EXAMPLES ---"""


def build_system_prompt() -> str:
    profile_name = get("profile.name", "Researcher")
    profile_affiliation = get("profile.affiliation", "")
    profile_interests = get("profile.interests", [])
    profile_pubs = get("profile.recent_papers", [])

    pub_lines = []
    for pub in profile_pubs[:10]:
        pub_lines.append(f"  - [{pub.get('year', '?')}] {pub.get('title', '')}")
    pubs_text = "\n".join(pub_lines) if pub_lines else "  (none)"

    profile_summary = (
        f"Name: {profile_name}\n"
        f"Affiliation: {profile_affiliation}\n"
        f"Stated interests: {', '.join(profile_interests) if profile_interests else '(none)'}\n"
        f"Recent publications:\n{pubs_text}"
    )

    current = [
        f"keywords_include: {get('interests.keywords_include', [])}",
        f"keywords_exclude: {get('interests.keywords_exclude', [])}",
        f"categories: {get('interests.categories', [])}",
        f"max_papers: {get('daily.max_papers', 20)}",
        f"min_score: {get('daily.min_relevance_score', 7)}",
    ]
    return SYSTEM_PROMPT.format(
        profile_summary=profile_summary,
        current_config="\n".join(current),
    )


def parse_response(messages: list[dict]) -> tuple[str, list[dict], str]:
    reasoning = ""
    full_text = ""
    for r, t, _ in _parse_stream(messages):
        reasoning = r
        full_text = t
    return _split_response(full_text, reasoning)


def parse_response_stream(messages: list[dict]):
    for reasoning, text, is_final in _parse_stream(messages):
        if is_final:
            chat, actions, _ = _split_response(text, reasoning)
        else:
            chat, actions = "", []
        yield reasoning, text, chat, actions, is_final


def _parse_stream(messages: list[dict]):
    client = get_fast()

    stream = client.call(
        messages,
        max_tokens=4096,
        stream=True,
        thinking=True,
    )

    reasoning = ""
    full_text = ""
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.reasoning_content:
            reasoning += delta.reasoning_content
        if delta.content:
            full_text += delta.content
        yield reasoning, full_text, False

    yield reasoning, full_text, True


def _split_response(full_text: str, reasoning: str) -> tuple[str, list[dict], str]:
    chat_lines = []
    actions = []
    for line in full_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        action = _parse_function_call(line)
        if action:
            actions.append(action)
        else:
            chat_lines.append(line)

    if not actions:
        actions = _try_parse_json_actions(full_text)
        if actions:
            chat_lines = [l for l in chat_lines if not any(l.strip().startswith(c) for c in ("[", "{", "```"))]

    if not chat_lines and not actions:
        chat_text = "Sorry, I had trouble processing that. Could you rephrase?"
    else:
        chat_text = "\n".join(chat_lines)

    return chat_text, actions, reasoning


def _try_parse_json_actions(text: str) -> list[dict]:
    try:
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(text)
        if isinstance(parsed, list) and all(isinstance(a, dict) and "action" in a for a in parsed):
            return parsed
        if isinstance(parsed, dict) and "action" in parsed:
            return [parsed]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def execute_action(action: dict) -> list[tuple[str, str]]:
    act = action.get("action", "none")
    results: list[tuple[str, str]] = []

    if act == "add_keywords":
        kw_list = action.get("keywords", [])
        current = set(get("interests.keywords_include", []))
        added = [k for k in kw_list if k not in current]
        if added:
            config_set("interests.keywords_include", sorted(current | set(kw_list)))
            results.append(("green", f"Added: {', '.join(added)}"))
        else:
            results.append(("yellow", "Already in list"))

    elif act == "remove_keywords":
        kw_list = action.get("keywords", [])
        current = set(get("interests.keywords_include", []))
        removed = [k for k in kw_list if k in current]
        if removed:
            config_set("interests.keywords_include", sorted(current - set(kw_list)))
            results.append(("green", f"Removed: {', '.join(removed)}"))
        else:
            results.append(("yellow", "Not found in list"))

    elif act == "add_exclude":
        kw_list = action.get("keywords", [])
        current = set(get("interests.keywords_exclude", []))
        added = [k for k in kw_list if k not in current]
        if added:
            config_set("interests.keywords_exclude", sorted(current | set(kw_list)))
            results.append(("green", f"Excluded: {', '.join(added)}"))
        else:
            results.append(("yellow", "Already excluded"))

    elif act == "remove_exclude":
        kw_list = action.get("keywords", [])
        current = set(get("interests.keywords_exclude", []))
        removed = [k for k in kw_list if k in current]
        if removed:
            config_set("interests.keywords_exclude", sorted(current - set(kw_list)))
            results.append(("green", f"Un-excluded: {', '.join(removed)}"))
        else:
            results.append(("yellow", "Not in exclude list"))

    elif act == "set_categories":
        cat_list = action.get("categories", [])
        config_set("interests.categories", cat_list)
        results.append(("green", f"Categories set to: {', '.join(cat_list)}"))

    elif act == "set_max_papers":
        val = action.get("value", 10)
        if val is None:
            results.append(("red", "Invalid number"))
        else:
            config_set("daily.max_papers", int(val))
            results.append(("green", f"Max papers set to {val}"))

    elif act == "set_min_score":
        val = action.get("value", 7)
        if val is None:
            results.append(("red", "Invalid number"))
        else:
            config_set("daily.min_relevance_score", int(val))
            results.append(("green", f"Min score set to {val}"))

    return results


def _parse_function_call(line: str) -> dict | None:
    line = line.strip()

    func_patterns = {
        "/ADD(": "add_keywords",
        "/REMOVE(": "remove_keywords",
        "/EXCLUDE(": "add_exclude",
        "/UNEXCLUDE(": "remove_exclude",
        "/CATS(": "set_categories",
        "/SCORE(": "set_min_score",
        "/MAX(": "set_max_papers",
    }

    for prefix, action_name in func_patterns.items():
        if line.upper().startswith(prefix):
            inner = line[len(prefix):].rstrip(")")
            if action_name in ("set_max_papers", "set_min_score"):
                try:
                    return {"action": action_name, "value": int(inner.strip())}
                except (ValueError, TypeError):
                    return None
            elif action_name == "set_categories":
                cats = [c.strip() for c in inner.split(",") if c.strip()]
                return {"action": action_name, "categories": cats}
            else:
                keywords = [k.strip() for k in inner.split(",") if k.strip()]
                return {"action": action_name, "keywords": keywords}

    return None
