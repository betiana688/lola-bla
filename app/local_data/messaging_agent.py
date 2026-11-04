"""The Messaging Agent - a specialist that interprets task_description and decides
which local action to take. Called by handle_messaging_task, never talks to the child.

Normally a separate cloud LLM makes the decision. If that call fails (no credits,
expired token, no network), a small set of local keyword rules takes over so messaging
keeps working. The fallback is deliberately simple and conservative: when unsure it
only checks, and it never plays or sends unless the words are clear."""

import json
import re
import subprocess
import time
from pathlib import Path

from huggingface_hub import InferenceClient

import messaging_executor

MODEL = "meta-llama/Llama-3.3-70B-Instruct"
TOKEN_PATH = Path(__file__).parent / "hf_token"

# After a failed cloud call, skip the cloud for this long and use the local rules.
COOLDOWN_S = 300
_cloud_disabled_until = 0.0


def _load_token() -> str:
    """The Messaging Agent uses its own dedicated Hugging Face token, kept in an
    owner-only file, never the robot's shared login."""
    token = TOKEN_PATH.read_text().strip() if TOKEN_PATH.exists() else ""
    if not token:
        raise RuntimeError("Missing hf_token file for the Messaging Agent")
    return token


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_only",
            "description": "Check whether there are new messages, without playing them.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "play_messages",
            "description": "Play unplayed messages. Optionally filter to one group and/or one sender.",
            "parameters": {
                "type": "object",
                "properties": {
                    "group_name": {"type": "string", "description": "Group name to filter to, if mentioned."},
                    "sender_name": {"type": "string", "description": "Sender name to filter to, if mentioned."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "need_recording",
            "description": "The person wants to send a message. This agent cannot record audio itself - "
                            "signal that a recording is needed, with the target group if known.",
            "parameters": {
                "type": "object",
                "properties": {
                    "group_name": {"type": "string", "description": "Target group name, if the person said one."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_recording",
            "description": "The person just recorded a message and now wants to actually send it.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replay_recording",
            "description": "The person wants to hear back the message they just recorded, before deciding.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rerecord",
            "description": "The person wants to discard what they recorded and record it again.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

SYSTEM_PROMPT = (
    "You interpret what a person wants regarding family voice messages, and call exactly one tool "
    "reflecting their real intent. Be strict about this distinction: 'check', 'do I have', 'is there "
    "anything new' mean check_only - report only, do NOT play anything. Only use play_messages if the "
    "person explicitly says to play, hear, or listen to the messages. When in doubt, prefer check_only "
    "- it is always safe to ask again for play_messages afterward, but playing without being asked is "
    "not correctable. If they want to send/record a NEW message, use need_recording. If a recording was "
    "just made and they want to actually send it, use send_recording. If they want to hear back what "
    "they just recorded, use replay_recording. If they want to discard it and record again, use rerecord. "
    "Call exactly one tool."
)


def _summarize_for_agent(executor_result):
    status = executor_result.get("status")
    if status == "no_new_messages":
        return {"status": "no_new_messages"}
    if status == "found_messages":
        summary_groups = []
        for group in executor_result.get("groups", []):
            messages = group.get("messages", [])
            senders = sorted(set(m["sender"] for m in messages))
            most_recent = messages[-1] if messages else None
            summary_groups.append({
                "group_name": group["group_name"],
                "message_count": len(messages),
                "senders": senders,
                "most_recent": f"{most_recent['day']}, {most_recent['time']}" if most_recent else None,
            })
        return {"status": "found_messages", "groups": summary_groups}
    if status == "not_linked":
        return {"status": "not_linked"}
    if status == "sent":
        return {"status": "sent"}
    if status == "failed":
        return {"status": "failed"}
    return {"status": "error"}


def resolve_group(requested, names):
    """The one group name that `requested` means, or None. An exact match (ignoring case,
    '&' and 'and') wins, so 'Test' never matches 'Another test'. A partial match counts
    only if exactly one group contains it."""
    if not requested:
        return None
    want = _norm(requested)
    exact = [n for n in names if _norm(n) == want]
    if len(exact) == 1:
        return exact[0]
    partial = [n for n in names if want and want in _norm(n)]
    return partial[0] if len(partial) == 1 else None


def _play_filtered(check_result, group_name=None, sender_name=None):
    """Plays messages from check_messages()'s full result, optionally filtered.
    A message is marked played only if playback really succeeded."""
    played_any = False
    wanted = None
    if group_name:
        names = [g["group_name"] for g in messaging_executor.get_active_groups_list(accessed_by="messaging_agent")]
        wanted = resolve_group(group_name, names)
        if wanted is None:
            return False  # unknown or ambiguous group: play nothing rather than the wrong one
    for group in check_result.get("groups", []):
        if wanted and group["group_name"] != wanted:
            continue
        for message in group.get("messages", []):
            if sender_name and sender_name.lower() not in message["sender"].lower():
                continue
            play_result = subprocess.run(["aplay", "-D", "reachymini_audio_sink", message["audio_path"]])
            if play_result.returncode == 0:
                messaging_executor.mark_played(message["message_id"], accessed_by="messaging_agent")
                played_any = True
    return played_any


# ---------- Local fallback rules (English, Spanish, German) ----------

_CHECK = re.compile(r"\bcheck\w*|\bany\b|\bdo i have\b|\brevis\w*|\bchequ\w*|\bhay\b|\btengo\b|\bpr[üu]f\w*|\bgibt\b|\bhabe\b", re.I)
_PLAY = re.compile(r"\bplay\w*|\bhear\w*|\blisten\w*|\breproduc\w*|\bescuch\w*|\babspiel\w*|\banh[öo]r\w*|\bhör\w*", re.I)
_SEND = re.compile(r"\bsend(?:s|ing)?\b|\benvi\w*|\bm[aá]nd\w*|\bsenden\b|\bsende\b|\bschick\w*", re.I)
_RECORD = re.compile(r"\brecord\w*|\bgrab\w*|\baufnehm\w*|\baufnahme\w*", re.I)
_AGAIN = re.compile(r"\bagain\b|\bre-?record\w*|\bdelete\b|\bdiscard\b|otra vez|de nuevo|\bborr\w*|\bnochmal\b|noch einmal|\bl[öo]sch\w*", re.I)
_REPLAY = re.compile(r"\breplay\w*|\bback\b|\b(?:play|hear|listen)\w*\s+(?:to\s+)?(?:it|that|this)\b|\bescuch\w*|\breproduc\w*|\babspiel\w*|\banh[öo]r\w*", re.I)


def _norm(text: str) -> str:
    text = text.lower().replace("&", " ")
    text = re.sub(r"\b(and|und|y|e)\b", " ", text)
    return re.sub(r"[^\w]+", " ", text).strip()


def _group_from_text(text: str):
    """The approved group named in the text, or None if none or more than one."""
    groups = messaging_executor.get_active_groups_list(accessed_by="messaging_agent")
    haystack = " " + _norm(text) + " "
    hits = [g["group_name"] for g in groups if " " + _norm(g["group_name"]) + " " in haystack]
    hits = [h for h in hits if not any(h != o and _norm(h) in _norm(o) for o in hits)]
    return hits[0] if len(hits) == 1 else None


def _decide_with_rules(text: str, pending_recording: bool):
    if pending_recording:
        # Replay first: sending cannot be undone, so if both are mentioned, replay.
        if _REPLAY.search(text):
            return "replay_recording", {}
        if _AGAIN.search(text):
            return "rerecord", {}
        if _SEND.search(text):
            return "send_recording", {}
    # "play back the message I tried to record" points at a recording, it is not a request to record
    if (re.search(r"\brecorded\b|\btried to record\b|\bgrabad\w*|\baufgenommen\w*", text, re.I)
            and _REPLAY.search(text) and not _SEND.search(text)):
        return "replay_recording", {}
    if _SEND.search(text) or _RECORD.search(text):
        return "need_recording", {"group_name": _group_from_text(text)}
    if _CHECK.search(text):
        return "check_only", {}
    if _PLAY.search(text):
        return "play_messages", {"group_name": _group_from_text(text)}
    return "check_only", {}  # unsure: the safe choice


# ---------- Cloud decision ----------

def _decide_with_cloud(task_description: str):
    client = InferenceClient(token=_load_token(), timeout=20)
    response = client.chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task_description},
        ],
        model=MODEL,
        tools=TOOLS,
        max_tokens=200,
    )
    message = response.choices[0].message
    if not message.tool_calls:
        return "unclear", {}
    call = message.tool_calls[0]
    args = json.loads(call.function.arguments) if call.function.arguments else {}
    return call.function.name, args


def _note_fallback(error: Exception) -> None:
    code = getattr(getattr(error, "response", None), "status_code", None)
    detail = (f"Cloud assistant unavailable ({type(error).__name__}"
              f"{f', HTTP {code}' if code else ''}); using simple local rules for {COOLDOWN_S // 60} minutes")
    try:
        messaging_executor.log_event("agent_fallback", "degraded", detail)
    except Exception:
        pass


def handle_task(task_description: str, pending_recording: bool = False) -> dict:
    """Main entry point. Interprets the task, executes the right local action,
    returns a minimal summary - never raw IDs, paths, or full message content."""
    global _cloud_disabled_until
    decision = None
    if time.monotonic() >= _cloud_disabled_until:
        try:
            decision = _decide_with_cloud(task_description)
        except Exception as e:
            _cloud_disabled_until = time.monotonic() + COOLDOWN_S
            _note_fallback(e)
    if decision is None:
        decision = _decide_with_rules(task_description, pending_recording)

    fn_name, args = decision

    if fn_name == "check_only":
        return _summarize_for_agent(messaging_executor.check_messages(accessed_by="messaging_agent"))

    if fn_name == "play_messages":
        result = messaging_executor.check_messages(accessed_by="messaging_agent")
        if result.get("status") != "found_messages":
            return _summarize_for_agent(result)
        _play_filtered(result, group_name=args.get("group_name"), sender_name=args.get("sender_name"))
        return _summarize_for_agent(result)

    if fn_name == "need_recording":
        return {"status": "need_recording", "group_name": args.get("group_name")}

    if fn_name in ("send_recording", "replay_recording", "rerecord"):
        return {"status": fn_name}

    return {"status": "unclear", "detail": "Could not determine what was wanted."}
