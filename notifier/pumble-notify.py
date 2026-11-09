#!/usr/bin/env python3
"""Claude Code -> Pumble notifier: per-task posts and an automatic daily report.

Modes
    start           UserPromptSubmit hook: snapshot git state; also posts any overdue daily report.
    stop            Stop hook: if the turn changed files or made commits, post "Claude finished" to the
                    activity channel and log the turn (commits, summary, skills used) for the daily report.
    digest [DATE]   Post the daily report for DATE (YYYY-MM-DD, default today).
    digest --due    Post every daily report that is due and not yet posted (run hourly by cron).
    Add --dry-run (or env PUMBLE_NOTIFY_DRY_RUN=1) to print instead of posting.

How it posts: through the Pumble MCP server configured in Claude Code (~/.claude.json, mcpServers.pumble,
added with `claude mcp add --scope user ... pumble`), so no extra Pumble app is needed. If that is missing,
"Claude finished" posts fall back to an incoming-webhook URL ($PUMBLE_WEBHOOK_URL or
~/.config/drivnx/pumble-webhook). Secrets never live in a repo.

Settings (no secrets): ~/.config/drivnx/pumble.json, e.g.
    {"timezone": "Asia/Ho_Chi_Minh", "report_hour": 23, "name": "Kouvuli",
     "channels": {"activity": "dev-activity", "daily": "daily-report"},
     "workspaces": ["~/Desktop/DrivnX"]}
Set "activity" to null to stop per-task posts. Errors go to ~/.claude/hooks/pumble-notify.log and never
block Claude.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import fcntl

    def lock_file(f) -> None:
        fcntl.flock(f, fcntl.LOCK_EX)
except ImportError:  # Windows
    import msvcrt

    def lock_file(f) -> None:
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)

HOME = Path.home()
STATE_DIR = HOME / ".claude" / "hooks" / "state"
DAILY_DIR = STATE_DIR / "daily"
LOG = HOME / ".claude" / "hooks" / "pumble-notify.log"
CONFIG_FILE = HOME / ".config" / "drivnx" / "pumble.json"
URL_FILE = HOME / ".config" / "drivnx" / "pumble-webhook"
CLAUDE_JSON = HOME / ".claude.json"
SUMMARY_CHARS = 300
MAX_COMMITS = 5
DEFAULTS = {
    "timezone": "UTC",
    "report_hour": 23,
    "name": "",
    "channels": {"activity": "dev-activity", "daily": "daily-report"},
    "workspaces": [],
}
DRY_RUN = bool(os.environ.get("PUMBLE_NOTIFY_DRY_RUN")) or "--dry-run" in sys.argv


def log(msg: str) -> None:
    try:
        with LOG.open("a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


def config() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    if CONFIG_FILE.is_file():
        user = json.loads(CONFIG_FILE.read_text())
        cfg["channels"].update(user.pop("channels", {}) or {})
        cfg.update(user)
    return cfg


def person(cfg: dict) -> str:
    return cfg.get("name") or git(Path.home(), "config", "--global", "user.name").strip() or "someone"


def local_tz(cfg: dict) -> tzinfo:
    try:
        return ZoneInfo(cfg["timezone"])
    except Exception:  # Windows has no tz database unless the tzdata package is installed
        return timezone(timedelta(hours=float(cfg.get("utc_offset_hours", 7))))


def now_local(cfg: dict) -> datetime:
    return datetime.now(local_tz(cfg))


# ---------------------------------------------------------------- git

def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=10)
    return r.stdout if r.returncode == 0 else ""


def repos_under(path: Path) -> list[Path]:
    found = []
    top = git(path, "rev-parse", "--show-toplevel").strip()
    if top:
        found.append(Path(top))
    try:
        for child in sorted(path.iterdir()):
            if (child / ".git").exists() and child not in found:
                found.append(child)
    except OSError:
        pass
    return found


def snapshot(repo: Path) -> dict:
    status = git(repo, "status", "--porcelain=v1", "-uall")
    diff = git(repo, "diff", "HEAD")
    return {
        "head": git(repo, "rev-parse", "HEAD").strip(),
        "fingerprint": hashlib.sha256((status + "\0" + diff).encode()).hexdigest(),
    }


def new_commits(repo: Path, since_head: str) -> list[list[str]]:
    if not since_head:
        return []
    out = git(repo, "log", "--format=%h%x09%s", f"{since_head}..HEAD").splitlines()
    return [c.split("\t", 1) for c in out if "\t" in c]


# ---------------------------------------------------------------- posting

def pumble_mcp() -> dict | None:
    try:
        srv = json.loads(CLAUDE_JSON.read_text()).get("mcpServers", {}).get("pumble")
    except (OSError, ValueError):
        return None
    return srv if srv and srv.get("url") and srv.get("headers") else None


def mcp_call(srv: dict, tool: str, args: dict) -> dict:
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "User-Agent": "claude-code-pumble-notify", **srv["headers"]}

    def rpc(body: dict, sid: str | None) -> tuple[str | None, dict]:
        h = dict(headers, **({"mcp-session-id": sid} if sid else {}))
        req = urllib.request.Request(srv["url"], data=json.dumps(body).encode(), headers=h, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            raw, sid = r.read().decode(), r.headers.get("mcp-session-id") or sid
        data = [l[5:] for l in raw.splitlines() if l.startswith("data:")]
        raw = data[-1] if data else raw
        return sid, (json.loads(raw) if raw.strip() else {})

    sid, _ = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "pumble-notify", "version": "2"}}}, None)
    rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    _, res = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                  "params": {"name": tool, "arguments": args}}, sid)
    result = res.get("result", {})
    if "error" in res or result.get("isError"):
        raise RuntimeError(f"{tool} failed: {json.dumps(res)[:300]}")
    text = "".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
    try:
        return json.loads(text)
    except ValueError:
        return {"text": text}


def channel_id(srv: dict, name: str) -> str:
    cache = STATE_DIR / "pumble-channels.json"
    ids = json.loads(cache.read_text()) if cache.is_file() else {}
    if name not in ids:
        chans = mcp_call(srv, "get_channels", {"channelTypes": ["PUBLIC", "PRIVATE"]})
        chans = chans.get("channels", []) if isinstance(chans, dict) else chans
        ids = {c["name"]: c["id"] for c in chans}
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(ids))
    if name not in ids:
        raise RuntimeError(f"Pumble channel #{name} not found")
    return ids[name]


def post(channel: str | None, text: str) -> None:
    if not channel:
        return
    if DRY_RUN:
        print(f"--- to #{channel} ---\n{text}")
        return
    srv = pumble_mcp()
    if srv:
        mcp_call(srv, "send_message", {"channelId": channel_id(srv, channel), "text": text})
        return
    url = os.environ.get("PUMBLE_WEBHOOK_URL", "").strip() or (
        URL_FILE.read_text().strip() if URL_FILE.is_file() else "")
    if url and channel == config()["channels"].get("activity"):
        req = urllib.request.Request(url, data=json.dumps({"text": text}).encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": "claude-code-pumble-notify"})
        urllib.request.urlopen(req, timeout=10).close()


# ---------------------------------------------------------------- transcript

def first_prose(text: str) -> str:
    """First plain paragraph of a markdown reply: skips tables, code, headings and lists; strips markup."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    for para in re.split(r"\n\s*\n", text):
        lines = [l.strip() for l in para.strip().splitlines() if l.strip()]
        if not lines or any(re.match(r"(\||#|>|[-*+] |\d+\. )", l) for l in lines):
            continue
        para = " ".join(lines)
        para = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", para)  # [text](url) -> text
        para = re.sub(r"(\*\*|__|`)", "", para)
        para = " ".join(para.split())
        if len(para) <= SUMMARY_CHARS:
            return para
        cut = para[:SUMMARY_CHARS]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        return cut[: end + 1] if end > 80 else cut.rstrip() + "…"
    return ""


def read_turn(payload: dict) -> tuple[str, list[str]]:
    """(summary of the last reply, skills/slash commands used in this turn)."""
    text, skills = payload.get("last_assistant_message") or "", []
    try:
        lines = Path(payload["transcript_path"]).read_text().splitlines() if payload.get("transcript_path") else []
    except OSError:
        lines = []
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        content = entry.get("message", {}).get("content", [])
        if entry.get("type") == "assistant" and isinstance(content, list):
            for c in content:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "tool_use" and c.get("name") == "Skill":
                    skills.append(str(c.get("input", {}).get("skill", "?")))
            if not text:
                parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                text = "\n".join(parts) if any(p.strip() for p in parts) else ""
        elif entry.get("type") == "user":
            prompt = content if isinstance(content, str) else " ".join(
                c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
            if prompt:  # reached the prompt that started this turn
                skills += re.findall(r"<command-name>/?([\w:.-]+)</command-name>", prompt)
                break
    return first_prose(text), skills


# ---------------------------------------------------------------- hooks

def state_file(session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_") or "unknown"
    return STATE_DIR / f"pumble-{safe}.json"


def save(session_id: str, snaps: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file(session_id).write_text(json.dumps(snaps))
    cutoff = time.time() - 7 * 86400  # tidy up old sessions
    for f in STATE_DIR.glob("pumble-*.json"):
        if f.name != "pumble-channels.json" and f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)


def on_start(payload: dict, cfg: dict) -> None:
    cwd = Path(payload.get("cwd") or os.getcwd())
    save(payload.get("session_id", "unknown"), {str(r): snapshot(r) for r in repos_under(cwd)})
    if not DRY_RUN:  # catch up on a missed daily report without slowing the prompt down
        detach = ({"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
                  if os.name == "nt" else {"start_new_session": True})
        subprocess.Popen([sys.executable, __file__, "digest", "--due"], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **detach)


def on_stop(payload: dict, cfg: dict) -> None:
    session_id = payload.get("session_id", "unknown")
    cwd = Path(payload.get("cwd") or os.getcwd())
    sf = state_file(session_id)
    before = json.loads(sf.read_text()) if sf.is_file() else {}
    now = {str(r): snapshot(r) for r in repos_under(cwd)}
    save(session_id, now)  # next turn compares against this point

    changed = [r for r, snap in now.items() if r in before and snap != before[r]]
    summary, skills = read_turn(payload)
    entries = []
    for r in changed:
        repo = Path(r)
        entries.append({
            "repo": repo.name, "path": r,
            "branch": git(repo, "branch", "--show-current").strip() or "detached",
            "commits": new_commits(repo, before[r].get("head", "")),
            "uncommitted": len(git(repo, "status", "--porcelain=v1", "-uall").splitlines()),
        })
    if entries or skills:
        day = now_local(cfg).date().isoformat()
        DAILY_DIR.mkdir(parents=True, exist_ok=True)
        with (DAILY_DIR / f"{day}.jsonl").open("a") as f:
            f.write(json.dumps({"ts": time.time(), "session": session_id, "summary": summary,
                                "skills": skills, "repos": entries}) + "\n")
    if not entries:
        return

    parts, who = [], person(cfg)
    for e in entries:
        lines = [f"**✅ Claude finished** · {who} · `{e['repo']}` · branch `{e['branch']}`"]
        if e["commits"]:
            lines.append(f"**Commits ({len(e['commits'])})**")
            lines += [f"- `{sha}` {subj}" for sha, subj in e["commits"][:MAX_COMMITS]]
            if len(e["commits"]) > MAX_COMMITS:
                lines.append(f"- … and {len(e['commits']) - MAX_COMMITS} more")
        if e["uncommitted"]:
            lines.append(f"**Uncommitted:** {e['uncommitted']} file(s)")
        parts.append("\n".join(lines))
    if summary:
        parts.append(f"> {summary}")
    post(cfg["channels"].get("activity"), "\n\n".join(parts))


# ---------------------------------------------------------------- daily report

def known_repos(cfg: dict, turns: list[dict]) -> list[Path]:
    paths = {Path(e["path"]) for t in turns for e in t.get("repos", [])}
    for ws in cfg.get("workspaces", []):
        paths.update(repos_under(Path(os.path.expanduser(ws))))
    return sorted(p for p in paths if p.is_dir())


def build_report(day: date, cfg: dict) -> str:
    start = datetime(day.year, day.month, day.day, tzinfo=local_tz(cfg))
    end = start + timedelta(days=1)
    f = DAILY_DIR / f"{day.isoformat()}.jsonl"
    turns = [json.loads(l) for l in f.read_text().splitlines() if l.strip()] if f.is_file() else []

    sections = []
    for repo in known_repos(cfg, turns):
        email = git(repo, "config", "user.email").strip()
        commits = git(repo, "log", "--all", "--no-merges", f"--author={email}", "--format=%h%x09%s",
                      f"--since={start.isoformat()}", f"--until={end.isoformat()}").splitlines() if email else []
        seen, unique = set(), []  # a squash-merge repeats the branch commit as "subject (#N)"
        for c in commits:
            key = re.sub(r"\s*\(#\d+\)$", "", c.split("\t", 1)[-1])
            if key not in seen:
                seen.add(key)
                unique.append(c)
        commits = unique
        prs = []
        try:
            r = subprocess.run(["gh", "pr", "list", "--author", "@me", "--state", "all", "--limit", "30",
                                "--json", "number,title,state,createdAt,mergedAt"],
                               cwd=repo, capture_output=True, text=True, timeout=20)
            for pr in json.loads(r.stdout or "[]"):
                for key, label in (("mergedAt", "merged"), ("createdAt", "opened")):
                    ts = pr.get(key)
                    if ts and start <= datetime.fromisoformat(ts.replace("Z", "+00:00")) < end:
                        prs.append(f"#{pr['number']} {pr['title']} ({label})")
                        break
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        tasks = sum(1 for t in turns for e in t.get("repos", []) if e["path"] == str(repo))
        if not (commits or prs or tasks):
            continue
        lines = [f"**{repo.name}**"]
        if commits:
            lines.append(f"- Commits ({len(commits)}): " + ", ".join(
                f"`{c.split(chr(9))[0]}` {c.split(chr(9), 1)[-1]}" for c in commits[:MAX_COMMITS])
                + (f", … +{len(commits) - MAX_COMMITS}" if len(commits) > MAX_COMMITS else ""))
        if prs:
            lines.append("- PRs: " + "; ".join(prs))
        if tasks:
            lines.append(f"- Claude tasks: {tasks}")
        sections.append("\n".join(lines))
    if not sections:
        return ""

    out = [f"**📋 Daily report** · {person(cfg)} · {day.strftime('%a %d %b %Y')}", *sections]
    skills = Counter(s for t in turns for s in t.get("skills", []))
    if skills:
        out.append("**Skills used:** " + ", ".join(f"{s} ×{n}" for s, n in skills.most_common()))
    highlights = [t["summary"] for t in turns if t.get("summary") and t.get("repos")][-5:]
    if highlights:
        out.append("**Highlights**\n" + "\n".join(f"- {h}" for h in highlights))
    return "\n\n".join(out)


def digest(args: list[str], cfg: dict) -> None:
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    with (DAILY_DIR / ".lock").open("w") as lock:
        lock_file(lock)
        posted_file = DAILY_DIR / "posted.json"
        posted = json.loads(posted_file.read_text()) if posted_file.is_file() else {}
        now = now_local(cfg)
        if "--due" in args:
            days = sorted(date.fromisoformat(p.stem) for p in DAILY_DIR.glob("*.jsonl"))
            days = [d for d in days if d.isoformat() not in posted and d >= now.date() - timedelta(days=7)
                    and (d < now.date() or now.hour >= int(cfg["report_hour"]))]
        else:
            explicit = [a for a in args if re.fullmatch(r"\d{4}-\d{2}-\d{2}", a)]
            days = [date.fromisoformat(explicit[0]) if explicit else now.date()]
        for d in days:
            text = build_report(d, cfg)
            if text:
                post(cfg["channels"].get("daily"), text)
            if not DRY_RUN and "--due" in args:  # manual runs don't block the automatic one
                posted[d.isoformat()] = time.time()
        if not DRY_RUN:
            posted_file.write_text(json.dumps(posted))
        for p in DAILY_DIR.glob("*.jsonl"):  # keep 30 days of logs
            if p.stat().st_mtime < time.time() - 30 * 86400:
                p.unlink(missing_ok=True)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    cfg = config()
    if mode in ("start", "stop"):
        payload = json.loads(sys.stdin.read() or "{}")
        (on_start if mode == "start" else on_stop)(payload, cfg)
    elif mode == "digest":
        digest(sys.argv[2:], cfg)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never block Claude because of a notification
        log(f"{sys.argv[1:2]} {type(e).__name__}: {e}")
        if DRY_RUN:
            raise
    sys.exit(0)
