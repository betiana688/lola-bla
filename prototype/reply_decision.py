"""Stop -> replay/send/delete decision loop - Story 2, Step 3."""

import subprocess

from audio_utils import AUDIO_DEVICE

REPLAY_PHRASES = {
    "es": ["repite", "escuchar", "reproducir"],
    "de": ["wiederholen", "abspielen"],
    "en": ["replay", "play"],
}
SEND_PHRASES = {
    "es": ["envia", "enviar", "manda"],
    "de": ["senden", "schicken"],
    "en": ["send"],
}
DELETE_PHRASES = {
    "es": ["borra", "borrar", "elimina"],
    "de": ["loschen", "verwerfen"],
    "en": ["delete", "discard"],
}

ASK_CHOICE_TEXT = {
    "es": "Repetir, enviar, o borrar?",
    "de": "Wiederholen, senden, oder loschen?",
    "en": "Replay, send, or delete?",
}
REPEAT_CHOICE_TEXT = {
    "es": "No te entendi. Repetir, enviar, o borrar?",
    "de": "Das habe ich nicht verstanden. Wiederholen, senden, oder loschen?",
    "en": "I didn't catch that. Replay, send, or delete?",
}
DELETED_TEXT = {
    "es": "Mensaje borrado.",
    "de": "Nachricht geloscht.",
    "en": "Message deleted.",
}


def match_choice(text, lang):
    text_lower = text.lower()
    if any(w in text_lower for w in REPLAY_PHRASES.get(lang, REPLAY_PHRASES["en"])):
        return "replay"
    if any(w in text_lower for w in SEND_PHRASES.get(lang, SEND_PHRASES["en"])):
        return "send"
    if any(w in text_lower for w in DELETE_PHRASES.get(lang, DELETE_PHRASES["en"])):
        return "delete"
    return None


def ask_choice(lang, speak_fn, listen_fn, retry_text_used=False):
    """Asks replay/send/delete, with one retry. Returns the choice or None."""
    prompt = REPEAT_CHOICE_TEXT if retry_text_used else ASK_CHOICE_TEXT
    speak_fn(prompt.get(lang, prompt["en"]), lang, emotion="ask_choice")
    reply_lang, reply_text = listen_fn()
    choice = match_choice(reply_text, reply_lang)
    return choice, reply_lang


def run_decision_loop(recording_path, lang, speak_fn, listen_fn, release_hw_fn, acquire_hw_fn):
    """Returns 'send', 'delete', or None (gave up after retry)."""
    retry_used = False
    while True:
        release_hw_fn()
        choice, reply_lang = ask_choice(lang, speak_fn, listen_fn, retry_text_used=retry_used)
        acquire_hw_fn()

        if choice == "replay":
            release_hw_fn()
            subprocess.run(["aplay", "-D", AUDIO_DEVICE, str(recording_path)])
            acquire_hw_fn()
            retry_used = False
            lang = reply_lang
            continue  # back to the same choice

        if choice == "send":
            return "send", reply_lang

        if choice == "delete":
            speak_fn(DELETED_TEXT.get(reply_lang, DELETED_TEXT["en"]), reply_lang, emotion="deleted")
            return "delete", reply_lang

        if retry_used:
            return None, reply_lang  # unrecognized twice - give up

        retry_used = True
        lang = reply_lang