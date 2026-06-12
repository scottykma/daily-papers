import logging
import os

from src.config import get, save
from src.chat.engine import build_system_prompt, execute_action, parse_response_stream

logger = logging.getLogger(__name__)

SLASH_COMMANDS = {
    "/add": "add_keywords", "/rm": "remove_keywords",
    "/exclude": "add_exclude", "/unexclude": "remove_exclude",
    "/cats": "set_categories", "/score": "set_min_score",
    "/max": "set_max_papers",
}


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m"


def _dim(s: str) -> str:
    return f"\033[2m{s}\033[0m"


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m"


def _cyan(s: str) -> str:
    return f"\033[36m{s}\033[0m"


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m"


def _clear_screen() -> None:
    print("\033[H\033[J", end="")


def _init_readline() -> None:
    try:
        import readline
        hist_file = os.path.expanduser(get("paths.readline_history", "~/.daily_papers_history"))
        try:
            readline.read_history_file(hist_file)
        except FileNotFoundError:
            pass
    except ImportError:
        pass


def _save_readline() -> None:
    try:
        import readline
        hist_file = os.path.expanduser(get("paths.readline_history", "~/.daily_papers_history"))
        readline.write_history_file(hist_file)
    except ImportError:
        pass


def _parse_slash_command(user_input: str) -> dict | None:
    if not user_input.startswith("/"):
        return None
    cmd = user_input.split()[0].lower()
    if cmd == "/help":
        return {"action": "show_help"}
    if cmd == "/show":
        return {"action": "show_config"}
    if cmd not in SLASH_COMMANDS:
        return None
    action_name = SLASH_COMMANDS[cmd]
    raw_args = user_input[len(cmd):].strip()
    if action_name in ("add_keywords", "remove_keywords", "add_exclude", "remove_exclude"):
        keywords = [k.strip() for k in raw_args.split(",") if k.strip()]
        return {"action": action_name, "keywords": keywords}
    if action_name == "set_categories":
        cats = [c.strip() for c in raw_args.split(",") if c.strip()]
        return {"action": action_name, "categories": cats}
    if action_name in ("set_max_papers", "set_min_score"):
        try:
            val = int(raw_args.strip().split()[0])
        except (ValueError, IndexError):
            val = None
        return {"action": action_name, "value": val}
    return None


def _action_icon(action: str) -> str:
    icons = {
        "add_keywords": "\u2705", "remove_keywords": "\U0001f5d1\ufe0f",
        "add_exclude": "\U0001f6ab", "remove_exclude": "\u267b\ufe0f",
        "add_categories": "\U0001f4c2", "remove_categories": "\U0001f4c2",
        "set_categories": "\U0001f4c2", "set_max_papers": "\U0001f4ca",
        "set_min_score": "\U0001f3af", "suggest": "\U0001f4a1", "none": "\u2139\ufe0f",
    }
    return icons.get(action, "\u2022")


def _print_header() -> None:
    include = get("interests.keywords_include", [])
    exclude = get("interests.keywords_exclude", [])
    categories = get("interests.categories", [])
    print(_bold("  DailyPapers - Interest Manager"))
    print(f"  {_cyan('Keywords')} ({len(include)}): {', '.join(include) if include else '(none)'}")
    print(f"  {_cyan('Exclude')}  ({len(exclude)}): {', '.join(exclude) if exclude else '(none)'}")
    print(f"  {_cyan('Categories')}: {', '.join(categories) if categories else '(none)'}")
    print(f"  {_cyan('Max/Day')}: {get('daily.max_papers', 10)}  |  {_cyan('Min Score')}: {get('daily.min_relevance_score', 7)}")
    print()


def _print_help() -> None:
    print(_bold("\nSlash Commands:"))
    for cmd, desc in [
        ("/add k1, k2", "Add keywords to include list"),
        ("/rm k1, k2", "Remove keywords from include list"),
        ("/exclude k1, k2", "Add keywords to exclude list"),
        ("/unexclude k1, k2", "Remove from exclude list"),
        ("/cats c1, c2", "Set arXiv categories"),
        ("/score N", "Set min relevance score (1-10)"),
        ("/max N", "Set max papers/day (1-50)"),
        ("/show", "Display current config"),
        ("/help", "Show this help"),
        ("/quit, exit, q", "Save and exit"),
    ]:
        print(f"  {_cyan(cmd):28s} {desc}")
    print()


def _stream_ai_response(messages: list[dict]) -> None:
    printed_reasoning = 0
    printed_text = 0
    final_actions = []
    final_chat = ""

    try:
        for reasoning, text, chat, actions, is_final in parse_response_stream(messages):
            if len(reasoning) > printed_reasoning:
                new = reasoning[printed_reasoning:]
                printed_reasoning = len(reasoning)
                print(_dim(new), end="", flush=True)
            if len(text) > printed_text:
                new = text[printed_text:]
                printed_text = len(text)
                if printed_reasoning and printed_text == len(new):
                    print()
                print(new, end="", flush=True)
            if is_final:
                final_chat = chat
                final_actions = actions
    except Exception:
        raise

    if printed_text:
        print()

    if final_actions:
        print()
        for action in final_actions:
            results = execute_action(action)
            for _color, msg in results:
                print(f"    {_action_icon(action.get('action', ''))} {msg}")

    messages.append({"role": "assistant", "content": final_chat})


def run_tui(initial_messages: list[dict] | None = None) -> None:
    _init_readline()

    messages: list[dict] = [{"role": "system", "content": build_system_prompt()}]
    if initial_messages:
        messages = initial_messages + messages[1:]

    while True:
        _clear_screen()
        _print_header()

        try:
            user_input = input("\033[32m> \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            _save_readline()
            save()
            print(_green("\nSaved to config.yaml."))
            return

        if not user_input:
            continue

        if user_input.lower() in ("/quit", "/q", "quit", "exit", "q", "done"):
            _save_readline()
            save()
            print(_green("Saved to config.yaml."))
            return

        slash_action = _parse_slash_command(user_input)
        if slash_action is not None:
            action = slash_action
            if action.get("action") == "show_help":
                _print_help()
                input(_dim("Press Enter to continue..."))
                continue
            if action.get("action") == "show_config":
                _print_header()
                input(_dim("Press Enter to continue..."))
                continue
            results = execute_action(action)
            for _color, msg in results:
                print(f"  {_action_icon(action.get('action', ''))} {msg}")
            print()
            input(_dim("Press Enter to continue..."))
            continue

        messages[0] = {"role": "system", "content": build_system_prompt()}
        messages.append({"role": "user", "content": user_input})

        try:
            _stream_ai_response(messages)
            print()
            input(_dim("Press Enter to continue..."))
        except Exception as e:
            print(f"\n  {_yellow('Error:')} {e}\n")
            input(_dim("Press Enter to continue..."))
            if messages and messages[-1]["role"] == "user":
                messages.pop()
