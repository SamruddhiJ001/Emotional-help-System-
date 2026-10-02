import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from urllib import error, request

from dotenv import load_dotenv

load_dotenv()

DEFAULT_SYSTEM_PROMPT = """You are SAATHI, a supportive AI wellbeing companion.

Your role is to have natural, respectful conversations with users and help them feel heard.

You are not a human, therapist, doctor, or emergency service.
Talk naturally and warmly.

Do not diagnose mental-health conditions.
Do not make medical claims.
Do not repeatedly ask the user to explain their feelings.
If the user wants casual conversation, have casual conversation.
If the user wants to talk about a difficult day, listen and respond thoughtfully.
If the user does not want to discuss something, respect that and offer another topic.
Ask at most one useful follow-up question when appropriate.
Respond to a concrete detail the user shared before offering advice or a question.
Avoid stock openers and vary your phrasing; do not ask a question in every reply.
Do not overwhelm the user with long responses.
Keep ordinary responses concise, roughly 1–4 short paragraphs.
You may use light humor when appropriate.
You may tell short original fictional stories when requested.
If a user appears to be in immediate danger, do not attempt to handle the situation alone. Encourage immediate connection with a trusted person and appropriate local emergency/professional support.
"""

FALLBACK_RESPONSE = (
    "I'm having a little trouble connecting right now. We can still keep talking — try sending that again."
)

MODE_GUIDES = {
    "talk": "Use a natural, supportive tone. Keep it warm and conversational.",
    "light": "Be playful and casual, but never inappropriate or dismissive. Keep it light and upbeat.",
    "focus": "Help the user organize thoughts and actions. Keep the reply practical and calm, with small next steps when helpful.",
    "calm": "Use a slower, gentler, reassuring tone. Make the reply reassuring and easy to absorb.",
}

SAFETY_PATTERNS = [
    r"kill myself|end my life|want to die|suicide|self-harm|hurt myself|don't want to live|can't go on|no reason to live",
    r"i am going to make it end|i am going to end it|i want to disappear forever|i'm going to do something drastic",
    r"i am in immediate danger|i might hurt myself|i may hurt myself|i can't keep myself safe",
]

SUPPORT_RESOURCES = [
    {"label": "Emergency", "detail": "If you may be in immediate danger, call 112 or go to the nearest emergency service right away."},
    {"label": "Tele MANAS", "detail": "India mental health support: 14416 (24x7)."},
    {"label": "KIRAN", "detail": "India mental health helpline: 1800-599-0019."},
]


def analyze_safety(message: str) -> Dict[str, Any]:
    text = (message or "").lower()
    triggered = any(re.search(pattern, text) for pattern in SAFETY_PATTERNS)
    if not triggered:
        return {"triggered": False, "response": "", "resources": []}

    return {
        "triggered": True,
        "response": "I'm really glad you told me. I don't want you to handle something this serious alone. Please consider contacting someone you trust and getting immediate support from a local emergency or crisis service if you may be in immediate danger.",
        "resources": SUPPORT_RESOURCES,
    }


def build_system_prompt(mode: str = "talk", language: str = "en") -> str:
    mode_name = mode.capitalize() if mode else "Talk"
    mode_note = MODE_GUIDES.get(mode, MODE_GUIDES["talk"])
    normalized_language = "English" if language.lower().startswith("en") else "Hindi" if language.lower().startswith("hi") else "the user's language"
    language_note = (
        "Respond in English unless the user writes in Hindi or mixes Hindi and English. "
        "Allow Hinglish naturally and do not force translation unless requested."
        if normalized_language == "English"
        else "Respond in Hindi unless the user uses English or mixed Hinglish. Allow natural code-switching and do not force translation unless requested."
    )
    return f"""{DEFAULT_SYSTEM_PROMPT}

Mode: {mode_name}
Style for this conversation: {mode_note}
Language preference: {normalized_language}. {language_note}

Safety rules:
- Do not pretend to be human.
- Do not diagnose or claim medical certainty.
- Respect when the user does not want to talk.
- Keep responses 1-4 short paragraphs in normal conversation.
- For simple messages, 1-3 sentences may be enough.
- Acknowledge a concrete detail from the user's message; avoid stock openers and repetitive follow-up questions.
- If the user asks for a story, tell a short original fictional story.
- Ask at most one useful follow-up question when appropriate.
- If a user appears to be in immediate danger, encourage immediate connection with a trusted person and emergency/local professional support.
"""


def detect_language(text: str) -> str:
    if not text:
        return "en"
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    return "en"


def _choose_response(options: List[str], seed: str) -> str:
    index = sum((position + 1) * ord(character) for position, character in enumerate(seed)) % len(options)
    return options[index]


def generate_demo_response(message: str, mode: str, kind: str = "message") -> str:
    if kind == "story":
        response = _choose_response([
            "Here's a tiny story: A paper boat drifted along a rain-filled gutter, passing each doorway like a new country. By the time the sun came out, it had made it all the way to the park.",
            "A baker left one warm bun on the windowsill to cool. A passing sparrow stole a crumb, then returned with two friends. It turned out to be a very popular bakery that morning.",
        ], message)
    else:
        text = message.lower().replace("’", "'").strip()
        if re.search(r"don't want to talk|do not want to talk|not ready to talk|rather not talk|don't feel like talking|not in the mood to talk", text):
            response = _choose_response([
                "Of course, you don't have to talk about it. We can leave it there. Would a distraction help, or would you rather keep things quiet for now?",
                "That's completely okay; you don't owe me an explanation. We can switch topics whenever you're ready.",
            ], text)
        elif re.search(r"\b(good morning|morning)\b", text):
            response = _choose_response([
                "Good morning! How's the day looking so far?",
                "Morning ☀️ Anything on the agenda today, or taking it as it comes?",
            ], text)
        elif re.search(r"\b(good night|night)\b", text):
            response = _choose_response([
                "Good night. Hope you get some good rest.",
                "Night 🌙 Take it easy, and I hope tomorrow starts gently.",
            ], text)
        elif re.search(r"\b(thanks|thank you)\b", text):
            response = _choose_response([
                "You're welcome. I'm glad that helped.",
                "Anytime. What else is on your mind?",
            ], text)
        elif re.search(r"\b(good day|went well|feeling good|excited|proud of)\b", text):
            response = _choose_response([
                "I love that for you. What was the best part?",
                "That's good to hear. Sounds like something went right today.",
            ], text)
        elif re.search(r"stressed|stress|overwhelm|too much|pressure", text):
            response = _choose_response([
                "That sounds like a lot to juggle. Is there one thing taking up most of your attention right now?",
                "When everything piles up, it can be hard to know where to start. What's the main thing pressing on you today?",
                "Sounds like there's a lot coming at you. We can sort through it one piece at a time, if that would help.",
            ], text)
        elif re.search(r"tired|exhausted|drained|sleepy", text) and re.search(r"college|class|lecture|campus|school|assignment|exam", text):
            response = _choose_response([
                "A long day at college can really take it out of you. Was it the workload, or just being on the go all day?",
                "College can make for some seriously long days. Do you get a chance to rest now?",
                "That sounds like a packed day. What part of college wore you out most?",
            ], text)
        elif re.search(r"tired|exhausted|drained|sleepy", text):
            response = _choose_response([
                "Sounds like you're running low on energy. Was today unusually busy?",
                "That's a rough feeling. I hope you can get a little time to recharge.",
                "Sounds like today took a lot out of you. What's your evening looking like?",
            ], text)
        elif re.search(r"bored|boring", text):
            response = _choose_response([
                "Let's fix that. Want a quick game, a strange fact, or a tiny story?",
                "Boredom has arrived 😄 Pick your cure: a brain teaser, a random fact, or a completely pointless debate?",
            ], text)
        elif re.search(r"interesting|random fact|tell me a fact|fact", text):
            response = _choose_response([
                "Here's one: a day on Venus is longer than its year. The planet takes longer to spin once than to orbit the Sun.",
                "Random fact: octopuses have three hearts, and two of them stop beating while they swim. A very inconvenient design for cardio.",
            ], text)
        elif re.search(r"cheer me up|cheer up|motivat", text):
            response = _choose_response([
                "Tiny reminder: you don't have to solve the whole day at once. One small thing at a time is enough for now.",
                "Here's a little reset: unclench your jaw, drop your shoulders, and take one slow breath. The next few minutes are all you need to handle.",
            ], text)
        elif re.search(r"how was your day|i want to talk|want to talk", text):
            response = _choose_response([
                "Sure. We can start anywhere. What's been on your mind today?",
                "I'm here for it. Do you want to start with how today went, or something else?",
            ], text)
        elif re.search(r"sad|rough|terrible|bad day|difficult|upset", text):
            response = _choose_response([
                "I'm sorry it's been a rough one. Was there one thing that tipped the day, or did it all build up?",
                "That sounds hard. You don't have to make sense of all of it at once; what part is weighing on you most?",
                "Oof, that's a lot for one day. Want to tell me what happened?",
            ], text)
        elif re.search(r"project|procrastinat|putting off|can't start|cannot start|do not know where to start", text):
            response = _choose_response([
                "Getting started is often the hardest bit. What's the smallest first step you could take, even if it only takes five minutes?",
                "Let's make it less daunting. What part of the project feels easiest to begin with?",
            ], text)
        elif re.search(r"game|mini game", text):
            response = _choose_response([
                "Quick game: name three things that are green. Real, imaginary, or questionable answers all count.",
                "Would you rather have a tiny dragon that sneezes glitter or a cat that can talk but only about snacks?",
            ], text)
        else:
            response = _choose_response([
                "Got you. What feels like the right place to start?",
                "I hear you. Is there a particular part you'd like to unpack?",
                "That makes sense. What would be most helpful to talk through first?",
            ], text)

    mode_openers = {
        "talk": "",
        "light": ("Let's keep it easy. ", "We can take a lighter angle. "),
        "focus": ("Let's make it manageable. ", "One step at a time: "),
        "calm": ("No rush. ", "We can take this slowly. "),
    }
    opener = mode_openers.get(mode, "")
    if isinstance(opener, tuple):
        opener = _choose_response(list(opener), message)
    return f"{opener}{response}"


def recent_messages_for_context(conversation: Any, limit: int = 20) -> List[Dict[str, str]]:
    if conversation is None:
        return []
    messages = list(getattr(conversation, "messages", []) or [])
    recent = messages[-limit:] if limit and limit > 0 else messages
    result: List[Dict[str, str]] = []
    for message in recent:
        sender = getattr(message, "sender", "")
        content = getattr(message, "content", "")
        if sender in {"user", "saathi"} and content:
            result.append({"role": "user" if sender == "user" else "assistant", "content": content})
    return result


class AIService:
    def __init__(self) -> None:
        self.provider_name = os.getenv("AI_PROVIDER", "demo").strip().lower() or "demo"
        self.api_key = os.getenv("AI_API_KEY", "").strip()
        self.model = os.getenv("AI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
        self.api_base_url = os.getenv("AI_API_BASE_URL", "https://api.openai.com/v1/chat/completions").strip()
        self.max_context_messages = int(os.getenv("MAX_CONTEXT_MESSAGES", "20").strip() or "20")
        self.is_demo_mode = self.provider_name == "demo" or not self.api_key

    def _build_payload(self, user_message: str, conversation: Optional[Any], mode: str, kind: str) -> List[Dict[str, str]]:
        language = detect_language(user_message)
        messages: List[Dict[str, str]] = [{"role": "system", "content": build_system_prompt(mode, language)}]
        recent_messages = recent_messages_for_context(conversation, self.max_context_messages)
        if recent_messages and recent_messages[-1] == {"role": "user", "content": user_message}:
            recent_messages.pop()
        for recent in recent_messages:
            messages.append({"role": recent["role"], "content": recent["content"]})
        if kind == "story":
            messages.append({"role": "user", "content": user_message + " Please tell a short original story in a warm, natural style."})
        else:
            messages.append({"role": "user", "content": user_message})
        return messages

    def generate_response(self, user_message: str, conversation: Optional[Any] = None, mode: str = "talk", kind: str = "message") -> str:
        safety = analyze_safety(user_message)
        if safety["triggered"]:
            return safety["response"]

        if self.provider_name == "demo" or not self.api_key:
            return generate_demo_response(user_message, mode, kind)

        try:
            messages = self._build_payload(user_message, conversation, mode, kind)
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.8,
                "max_tokens": 250,
            }

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            data = json.dumps(payload).encode("utf-8")
            req = request.Request(self.api_base_url, data=data, headers=headers, method="POST")
            with request.urlopen(req, timeout=20) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            reply = result.get("choices", [{}])[0].get("message", {}).get("content") or ""
            if not reply:
                return FALLBACK_RESPONSE
            return reply.strip()
        except (error.HTTPError, error.URLError, TimeoutError, ValueError, KeyError):
            logging.exception("AI provider call failed for the SAATHI chat endpoint.")
            return FALLBACK_RESPONSE

