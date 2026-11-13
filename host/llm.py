"""Shared local-LLM helpers (Ollama). Used by reflect.py and ask.py.

Everything runs on this machine: health data never leaves it.
No extra dependency: Ollama's HTTP API via the standard library.
"""
import json
import re
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "llama3.2"


def chat(messages, model=DEFAULT_MODEL, temperature=0.3):
    """Send a chat (list of {role, content}) and return the reply text.
    Raises OSError if Ollama is not reachable."""
    body = {"model": model, "stream": False, "messages": messages,
            "options": {"temperature": temperature}}
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.load(resp)["message"]["content"].strip()


RHYTHM_NUMBERS = {"0", "4", "6", "7", "8"}   # numbers in rhythm names (4-7-8, 4-0-6-0)


def unverified_numbers(text, facts):
    """Lists times (09:42) and numbers in the reply that don't appear in the facts.
    facts: anything JSON-serializable (dict of facts, list of query rows...)."""
    src = json.dumps(facts, default=str)
    times = set(re.findall(r"\d{2}:\d{2}", src))
    nums = {str(int(x)) for x in re.findall(r"\d+", src)} | RHYTHM_NUMBERS
    bad = set()
    for tok in re.findall(r"\d{1,2}:\d{2}|\d+", text):
        if ":" in tok:
            if tok.zfill(5) not in times:          # '9:42' -> '09:42'
                bad.add(tok)
        elif str(int(tok)) not in nums:            # '09' and '9' are the same number
            bad.add(tok)
    return sorted(bad)
