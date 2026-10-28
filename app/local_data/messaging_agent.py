"""The Messaging Agent - a specialist LLM that interprets task_description
and decides which local action to actually take. Called by handle_messaging_task,
never talks to the child directly."""

import json
from huggingface_hub import InferenceClient

import messaging_executor

MODEL = "meta-llama/Llama-3.3-70B-Instruct"

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
    if status == "sent":
        return {"status": "sent"}
    if status == "failed":
        return {"status": "failed"}
    return {"status": "error"}


def _play_filtered(check_result, group_name=None, sender_name=None):
    """Plays messages from check_messages()'s full result, optionally filtered."""
    played_any = False
    for group in check_result.get("groups", []):
        if group_name and group_name.lower() not in group["group_name"].lower():
            continue
        for message in group.get("messages", []):
            if sender_name and sender_name.lower() not in message["sender"].lower():
                continue
            import subprocess
            play_result = subprocess.run(["aplay", "-D", "reachymini_audio_sink", message["audio_path"]])
            if play_result.returncode == 0:
                messaging_executor.mark_played(message["message_id"], accessed_by="messaging_agent")
                played_any = True
            else:
                # Playback failed - do NOT mark as played, so it's not silently lost.
                pass
    return played_any


def handle_task(task_description: str) -> dict:
    """Main entry point. Interprets the task, executes the right local action,
    returns a minimal summary - never raw IDs, paths, or full message content."""
    client = InferenceClient()
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
        return {"status": "unclear", "detail": "Could not determine what was wanted."}

    call = message.tool_calls[0]
    fn_name = call.function.name
    args = json.loads(call.function.arguments) if call.function.arguments else {}

    if fn_name == "check_only":
        result = messaging_executor.check_messages(accessed_by="messaging_agent")
        return _summarize_for_agent(result)

    if fn_name == "play_messages":
        result = messaging_executor.check_messages(accessed_by="messaging_agent")
        if result.get("status") != "found_messages":
            return _summarize_for_agent(result)
        _play_filtered(result, group_name=args.get("group_name"), sender_name=args.get("sender_name"))
        return _summarize_for_agent(result)

    if fn_name == "need_recording":
        return {"status": "need_recording", "group_name": args.get("group_name")}

    if fn_name == "send_recording":
        return {"status": "send_recording"}

    if fn_name == "replay_recording":
        return {"status": "replay_recording"}

    if fn_name == "rerecord":
        return {"status": "rerecord"}

    return {"status": "unclear"}