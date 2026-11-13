import json
import re
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "llama3.2"


def chat(messages, model=DEFAULT_MODEL, temperature=0.3):
    body = {"model": model, "stream": False, "messages": messages,
            "options": {"temperature": temperature}}
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.load(resp)["message"]["content"].strip()


RHYTHM_NUMBERS = {"0", "4", "6", "7", "8"}


def unverified_numbers(text, facts):
    src = json.dumps(facts, default=str)
    times = set(re.findall(r"\d{2}:\d{2}", src))
    nums = {str(int(x)) for x in re.findall(r"\d+", src)} | RHYTHM_NUMBERS
    bad = set()
    for tok in re.findall(r"\d{1,2}:\d{2}|\d+", text):
        if ":" in tok:
            if tok.zfill(5) not in times:
                bad.add(tok)
        elif str(int(tok)) not in nums:
            bad.add(tok)
    return sorted(bad)
