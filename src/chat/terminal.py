import logging
import os

from src.config import get, save
from src.chat.engine import build_system_prompt, execute_action, parse_response_stream
from src.chat.screen import Screen, _action_icon, _bold, _dim, _green, _cyan, _yellow

logger = logging.getLogger(__name__)

SLASH_COMMANDS = {
    "/add": "add_keywords", "/rm": "remove_keywords",
    "/exclude": "add_exclude", "/unexclude": "remove_exclude",
    "/cats": "set_categories", "/score": "set_min_score",
    "/max": "set_max_papers",
}


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


def _print_header() -> None:
    include = get("interests.keywords_include", [])
    exclude = get("interests.keywords_exclude", [])
    categories = get("interests.categories", [])
    print(_bold("  DailyPapers - Interest Manager"))
    print(f"  {_cyan('Keywords')} ({len(include)}): {', '.join(include) if include else '(none)'}")
    print(f"  {_cyan('Exclude')}  ({len(exclude)}): {', '.join(exclude) if exclude else '(none)'}")
    print(f"  {_cyan('Categories')}: {', '.join(categories) if categories else '(none)'}")
    print(f"  {_cyan('Max/Day')}: {get('daily.max_papers', 20)}  |  {_cyan('Min Score')}: {get('daily.min_relevance_score', 7)}")
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


def _stream_ai_response(messages: list[dict], screen: Screen | None = None) -> None:
    printed_text = 0
    final_chat = ""
    final_actions = []

    if screen is not None:
        screen.show_thinking()

    try:
        for reasoning, text, chat, actions, is_final in parse_response_stream(messages):
            if len(text) > printed_text:
                new = text[printed_text:]
                printed_text = len(text)
                if screen is not None:
                    screen.write(new)
                else:
                    print(new, end="", flush=True)

            if is_final:
                final_chat = chat
                final_actions = actions
    except Exception:
        raise

    if screen is not None:
        screen.writeln()
    else:
        if printed_text:
            print()

    if final_actions:
        for action in final_actions:
            results = execute_action(action)
            if screen is not None:
                screen.show_actions(action, results)
            else:
                for _color, msg in results:
                    print(f"    {_action_icon(action.get('action', ''))} {msg}")
        if screen is not None and final_actions:
            screen.show_config_status()

    messages.append({"role": "assistant", "content": final_chat})


def run_tui(initial_messages: list[dict] | None = None) -> None:
    _init_readline()

    messages: list[dict] = [{"role": "system", "content": build_system_prompt()}]
    if initial_messages:
        messages = initial_messages + messages[1:]

    screen = Screen()
    screen.render_header()

    if initial_messages:
        screen.render_message_history(initial_messages)

    while True:
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
                continue
            if action.get("action") == "show_config":
                _print_header()
                continue
            results = execute_action(action)
            for _color, msg in results:
                print(f"  {_action_icon(action.get('action', ''))} {msg}")
            screen.show_config_status()
            continue

        messages[0] = {"role": "system", "content": build_system_prompt()}
        messages.append({"role": "user", "content": user_input})

        try:
            _stream_ai_response(messages, screen)
        except Exception as e:
            print(f"\n  {_yellow('Error:')} {e}\n")
            print(_dim("Press Enter to continue..."))
            input("")
            if messages and messages[-1]["role"] == "user":
                messages.pop()
