"""Group selection for sending a message - Story 2, Step 2."""

import sqlite3
from pathlib import Path

from audio_utils import release_hw, acquire_hw

DB_PATH = Path(__file__).parent / "data" / "lola.db"

CONJUNCTION = {"es": "y", "de": "und", "en": "and"}

ASK_SEND_GROUP_TEXT = {
    "es": "A cual grupo quieres enviar un mensaje?",
    "de": "An welche Gruppe mochtest du eine Nachricht senden?",
    "en": "Which group do you want to send a message to?",
}
REPEAT_GROUP_TEXT = {
    "es": "No te entendi. Puedes repetir el nombre del grupo?",
    "de": "Das habe ich nicht verstanden. Kannst du den Gruppennamen wiederholen?",
    "en": "I didn't catch that. Can you repeat the group name?",
}
SINGLE_GROUP_CONFIRM_TEXT = {
    "es": "Mensaje para {name}.",
    "de": "Nachricht fur {name}.",
    "en": "Message for {name}.",
}


def get_all_active_groups(conn):
    return conn.execute("SELECT id, name FROM groups WHERE is_active = 1").fetchall()


def match_group_from_candidates(candidates, text):
    text_lower = text.lower()
    for group_id, name in candidates:
        for word in name.lower().split():
            if len(word) > 2 and word in text_lower:
                return group_id, name
    return None, None


def join_names(names, lang):
    if len(names) == 1:
        return names[0]
    conj = CONJUNCTION.get(lang, CONJUNCTION["en"])
    return ", ".join(names[:-1]) + f" {conj} " + names[-1]


def ask_group_for_sending(conn, lang, speak_fn, listen_fn):
    """Returns (group_id, group_name, reply_lang) or (None, None, reply_lang)."""
    candidates = get_all_active_groups(conn)

    if len(candidates) == 1:
        group_id, group_name = candidates[0]
        speak_fn(SINGLE_GROUP_CONFIRM_TEXT.get(lang, SINGLE_GROUP_CONFIRM_TEXT["en"]).format(name=group_name), lang, emotion="ask_group")
        return group_id, group_name, lang

    speak_fn(ASK_SEND_GROUP_TEXT.get(lang, ASK_SEND_GROUP_TEXT["en"]), lang, emotion="ask_group")
    release_hw()
    reply_lang, reply_text = listen_fn()
    acquire_hw()

    group_id, group_name = match_group_from_candidates(candidates, reply_text)
    if group_id:
        return group_id, group_name, reply_lang

    speak_fn(REPEAT_GROUP_TEXT.get(reply_lang, REPEAT_GROUP_TEXT["en"]), reply_lang, emotion="retry_group")
    release_hw()
    reply_lang, reply_text = listen_fn()
    acquire_hw()

    group_id, group_name = match_group_from_candidates(candidates, reply_text)
    return group_id, group_name, reply_lang