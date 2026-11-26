"""
GeoChip CLI Terminal UI Module.
Provides arrow-key interactive menus, masked secret prompts, live spinners,
and clean cross-platform ANSI formatting.
"""

from __future__ import annotations

import getpass
import os
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

from .config import mask_secret

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
BRIGHT_CYAN = "\033[96m"
GREEN = "\033[32m"
BRIGHT_GREEN = "\033[92m"
YELLOW = "\033[33m"
BRIGHT_YELLOW = "\033[93m"
RED = "\033[31m"
WHITE = "\033[97m"
BG_BLUE = "\033[44m"


def enable_windows_ansi() -> None:
    """Enable ANSI virtual terminal processing and UTF-8 output on Windows."""
    if os.name == "nt":
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            mode.value |= 0x0004
            kernel32.SetConsoleMode(handle, mode)
        except Exception:
            pass


enable_windows_ansi()


def print_banner() -> None:
    """Display the GeoChip CLI ASCII hero banner without version numbers."""
    banner = f"""
{BRIGHT_CYAN}  ██████╗ ███████╗ ██████╗  ██████╗██╗  ██╗██╗██████╗      ██████╗██╗     ██╗
 ██╔════╝ ██╔════╝██╔═══██╗██╔════╝██║  ██║██║██╔══██╗    ██╔════╝██║     ██║
 ██║  ███╗█████╗  ██║   ██║██║     ███████║██║██████╔╝    ██║     ██║     ██║
 ██║   ██║██╔══╝  ██║   ██║██║     ██╔══██║██║██╔═══╝     ██║     ██║     ██║
 ╚██████╔╝███████╗╚██████╔╝╚██████╗██║  ██║██║██║         ╚██████╗███████╗██║
  ╚═════╝ ╚══════╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝╚═╝╚═╝          ╚═════╝╚══════╝╚═╝{RESET}
  {BOLD}{WHITE}Satellite Imagery Ingestion, Chipping & Roboflow Pipeline{RESET}
"""
    print(banner)


def print_status_bar(gee_ready: bool, roboflow_ready: bool, work_dir: Path) -> None:
    """Display connection readiness and active workspace path."""
    gee_badge = f"{BRIGHT_GREEN}Ready{RESET}" if gee_ready else f"{BRIGHT_YELLOW}Setup Required{RESET}"
    rf_badge = f"{BRIGHT_GREEN}Ready{RESET}" if roboflow_ready else f"{DIM}Optional (Not Configured){RESET}"
    print(f"  {DIM}Workspace:{RESET} {work_dir}")
    print(f"  {DIM}Earth Engine:{RESET} {gee_badge}  {DIM}|{RESET}  {DIM}Roboflow:{RESET} {rf_badge}\n")


@contextmanager
def spinner(message: str):
    """Display a live spinner during long-running network or Earth Engine calls."""
    if not sys.stdout.isatty():
        print_info(message)
        yield
        return

    from rich.console import Console

    console = Console()
    with console.status(f"[cyan]{message}[/cyan]", spinner="dots"):
        yield


def clear_lines(n: int) -> None:
    """Clear n terminal lines upwards."""
    for _ in range(n):
        sys.stdout.write("\033[F\033[K")
    sys.stdout.flush()


def _get_key_windows() -> str:
    """Read a keypress on Windows via msvcrt."""
    import msvcrt

    ch = msvcrt.getch()
    if ch in (b"\x00", b"\xe0"):
        ch2 = msvcrt.getch()
        if ch2 == b"H":
            return "UP"
        if ch2 == b"P":
            return "DOWN"
        if ch2 == b"K":
            return "LEFT"
        if ch2 == b"M":
            return "RIGHT"
    elif ch == b"\r":
        return "ENTER"
    elif ch == b"\x1b":
        return "ESC"
    elif ch == b"\x03":
        raise KeyboardInterrupt
    return ch.decode("utf-8", errors="ignore")


def _get_key_posix() -> str:
    """Read a keypress on POSIX via termios and tty."""
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                if ch3 == "A":
                    return "UP"
                if ch3 == "B":
                    return "DOWN"
                if ch3 == "C":
                    return "RIGHT"
                if ch3 == "D":
                    return "LEFT"
            return "ESC"
        if ch in ("\r", "\n"):
            return "ENTER"
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def read_key() -> str:
    """Read a single keypress cross-platform."""
    if os.name == "nt":
        return _get_key_windows()
    return _get_key_posix()


def _fit_text(text: str, max_len: int) -> str:
    """Truncate text to max_len with ellipsis if it exceeds terminal width."""
    if not text:
        return ""
    if len(text) > max_len:
        return text[: max(0, max_len - 3)] + "..."
    return text


def select(
    title: str,
    choices: list,
    default_index: int = 0,
    help_text: str = "Use ↑/↓ arrow keys to navigate, press ENTER to confirm",
) -> int:
    """Interactive select menu with arrow keys and numbered fallback."""
    if not sys.stdin.isatty():
        print(f"\n{BOLD}{CYAN}? {title}{RESET}")
        for idx, item in enumerate(choices, 1):
            label = item if isinstance(item, str) else item.get("name", str(item))
            print(f"  [{idx}] {label}")
        while True:
            try:
                raw = input(f"Select [1-{len(choices)}] (default {default_index + 1}): ").strip()
                if not raw:
                    return default_index
                val = int(raw) - 1
                if 0 <= val < len(choices):
                    return val
            except (ValueError, KeyboardInterrupt):
                pass
            print(f"{RED}Invalid choice, please try again.{RESET}")

    current_idx = default_index
    num_choices = len(choices)
    has_any_desc = any(isinstance(c, dict) and bool(c.get("desc")) for c in choices)

    print(f"\n{BOLD}{BRIGHT_CYAN}? {title}{RESET}")
    if help_text:
        print(f"  {DIM}{help_text}{RESET}")

    lines_to_clear = num_choices + (2 if has_any_desc else 0)
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

    try:
        while True:
            cols = shutil.get_terminal_size(fallback=(80, 24)).columns
            max_label_width = max(20, cols - 12)

            for idx, item in enumerate(choices):
                raw_label = item.get("name", str(item)) if isinstance(item, dict) else str(item)
                label = _fit_text(raw_label, max_label_width)
                if idx == current_idx:
                    print(f"  {BRIGHT_CYAN}❯ [{idx + 1}]{RESET} {BOLD}{WHITE}{label}{RESET}")
                else:
                    print(f"  {DIM}  [{idx + 1}] {label}{RESET}")

            if has_any_desc:
                max_desc_width = max(20, cols - 8)
                curr_item = choices[current_idx]
                raw_desc = curr_item.get("desc", "") if isinstance(curr_item, dict) else ""
                desc = _fit_text(raw_desc, max_desc_width) if raw_desc else ""
                print()
                if desc:
                    print(f"  {CYAN}ℹ {desc}{RESET}")
                else:
                    print(f"  {DIM}ℹ (No additional description){RESET}")

            try:
                key = read_key()
            except KeyboardInterrupt:
                print("\n")
                sys.exit(0)

            if key in ("UP", "k", "K"):
                current_idx = (current_idx - 1) % num_choices
                clear_lines(lines_to_clear)
            elif key in ("DOWN", "j", "J"):
                current_idx = (current_idx + 1) % num_choices
                clear_lines(lines_to_clear)
            elif key == "ENTER":
                clear_lines(lines_to_clear)
                chosen = choices[current_idx]
                chosen_label = chosen if isinstance(chosen, str) else chosen.get("name", str(chosen))
                print(f"  {BRIGHT_GREEN}✔ Selected: {BOLD}{chosen_label}{RESET}")
                return current_idx
            elif key.isdigit():
                digit = int(key) - 1
                if 0 <= digit < num_choices:
                    current_idx = digit
                    clear_lines(lines_to_clear)
                    chosen = choices[current_idx]
                    chosen_label = chosen if isinstance(chosen, str) else chosen.get("name", str(chosen))
                    print(f"  {BRIGHT_GREEN}✔ Selected: {BOLD}{chosen_label}{RESET}")
                    return current_idx
                clear_lines(lines_to_clear)
            else:
                clear_lines(lines_to_clear)
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


def prompt_input(message: str, default: str | None = None, validator=None) -> str:
    """Prompt user for text input with optional default value and validator."""
    prompt_str = f"{BOLD}{CYAN}? {message}{RESET}"
    if default is not None:
        prompt_str += f" {DIM}(default: {default}){RESET}"
    prompt_str += ": "

    while True:
        try:
            val = input(prompt_str).strip()
            if not val and default is not None:
                val = str(default)
            if validator:
                ok, err = validator(val)
                if not ok:
                    print(f"  {RED}✖ {err}{RESET}")
                    continue
            return val
        except KeyboardInterrupt:
            print("\n")
            sys.exit(0)


def prompt_secret(message: str, existing_value: str | None = None) -> str:
    """Prompt for a secret without echoing it or leaking raw existing values."""
    hint = f" {DIM}(press Enter to keep {mask_secret(existing_value)}){RESET}" if existing_value else ""
    prompt_str = f"{BOLD}{CYAN}? {message}{hint}: {RESET}"

    while True:
        try:
            entered = getpass.getpass(prompt_str).strip()
            if entered:
                return entered
            if existing_value:
                return existing_value
            print(f"  {RED}✖ Input cannot be empty.{RESET}")
        except KeyboardInterrupt:
            print("\n")
            sys.exit(0)


def prompt_number(
    message: str,
    default: int | float | None = None,
    min_val: int | float | None = None,
    max_val: int | float | None = None,
    is_float: bool = False,
) -> int | float:
    """Prompt user for a validated integer or float."""

    def validator(v: str) -> tuple[bool, str]:
        try:
            num = float(v) if is_float else int(v)
            if min_val is not None and num < min_val:
                return False, f"Minimum allowed value is {min_val}"
            if max_val is not None and num > max_val:
                return False, f"Maximum allowed value is {max_val}"
            return True, ""
        except ValueError:
            return False, "Input must be a valid number"

    raw = prompt_input(message, default=str(default) if default is not None else None, validator=validator)
    return float(raw) if is_float else int(raw)


def prompt_confirm(message: str, default: bool = True) -> bool:
    """Prompt user for Yes/No confirmation."""
    def_str = "Y/n" if default else "y/N"
    raw = prompt_input(f"{message} [{def_str}]", default="y" if default else "n").lower()
    return raw in ("y", "yes")


def print_step(title: str) -> None:
    """Print a visually distinct workflow step banner."""
    print(f"\n{BOLD}{BG_BLUE}{WHITE}  {title.upper()}  {RESET}\n")


def print_success(message: str) -> None:
    """Print success message."""
    print(f"{BRIGHT_GREEN}✔ {message}{RESET}")


def print_error(message: str) -> None:
    """Print error message."""
    print(f"{RED}✖ {message}{RESET}")


def print_warning(message: str) -> None:
    """Print warning message."""
    print(f"{BRIGHT_YELLOW}⚠ {message}{RESET}")


def print_info(message: str) -> None:
    """Print informative message."""
    print(f"{CYAN}ℹ {message}{RESET}")
