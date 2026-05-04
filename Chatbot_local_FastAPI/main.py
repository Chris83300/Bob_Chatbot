from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from typing import Optional
from threading import Lock
import ollama
import os
import sys
import uuid
import time
import logging
import re
import random
import asyncio
import tempfile
import base64
import edge_tts
from faster_whisper import WhisperModel

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("bob")

MODEL       = os.getenv("MODEL",       "qwen3:14b")
MODEL_VOICE = os.getenv("MODEL_VOICE", "qwen3:14b")

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "Tu es un assistant sarcastique.")
logger.info(f"System prompt chargé — début : {SYSTEM_PROMPT[:50]!r} … fin : {SYSTEM_PROMPT[-50:]!r}")

OLLAMA_OPTIONS = {
    "temperature":       float(os.getenv("LLM_TEMPERATURE",        "0.85")),
    "repeat_penalty":    float(os.getenv("LLM_REPEAT_PENALTY",     "1.6")),
    "repeat_last_n":     int(os.getenv(  "LLM_REPEAT_LAST_N",      "2048")),
    "top_p":             float(os.getenv("LLM_TOP_P",              "0.9")),
    "top_k":             int(os.getenv(  "LLM_TOP_K",              "40")),
    "num_ctx":           int(os.getenv(  "LLM_NUM_CTX",            "8192")),
    "presence_penalty":  float(os.getenv("LLM_PRESENCE_PENALTY",   "0.6")),
    "frequency_penalty": float(os.getenv("LLM_FREQUENCY_PENALTY",  "0.8")),
    "think":             os.getenv("LLM_THINK", "false").lower() == "true",
}

OLLAMA_OPTIONS_VOICE = {
    **OLLAMA_OPTIONS,
    "num_ctx": int(os.getenv("LLM_NUM_CTX_VOICE", "8192")),
}

logger.info(f"Modèle texte  : {MODEL}")
logger.info(f"Modèle vocal  : {MODEL_VOICE}")
logger.info(f"Options voice : num_ctx={OLLAMA_OPTIONS_VOICE['num_ctx']}  repeat_penalty={OLLAMA_OPTIONS_VOICE['repeat_penalty']}  presence_penalty={OLLAMA_OPTIONS_VOICE['presence_penalty']}")

MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))
SESSION_TTL = int(os.getenv("SESSION_TTL", "3600"))

_sessions: dict[str, dict] = {}
_sessions_lock = Lock()

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")
whisper_model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
logger.info(f"Modèle Whisper chargé ({WHISPER_MODEL}/int8/cpu)")

EDGE_TTS_VOICE = "fr-FR-HenriNeural"
EDGE_TTS_RATE = "+10%" #vitesse de la voix
EDGE_TTS_PITCH = "-10Hz" #ton de la voix


def _build_initial_history():
    return [{"role": "system", "content": SYSTEM_PROMPT}]


def _get_or_create_session(session_id):
    now = time.time()
    with _sessions_lock:
        for sid in [s for s, v in _sessions.items() if now - v["last_seen"] > SESSION_TTL]:
            del _sessions[sid]

        if session_id and session_id in _sessions:
            _sessions[session_id]["last_seen"] = now
            return session_id, _sessions[session_id]["history"]

        new_id = session_id or str(uuid.uuid4())
        _sessions[new_id] = {
            "history": _build_initial_history(),
            "last_seen": now,
            "safety_count": 0,
        }
        logger.info(f"Nouvelle session : {new_id[:8]}")
        return new_id, _sessions[new_id]["history"]


def _truncate_history(history):
    protected = history[:1]
    conversation = history[1:]
    if len(conversation) > MAX_HISTORY_MESSAGES:
        excess = len(conversation) - MAX_HISTORY_MESSAGES
        if excess % 2 == 1:
            excess += 1
        conversation = conversation[excess:]
    return protected + conversation


app = FastAPI(title="Bob Chat API")


class ChatRequest(BaseModel):
    content: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(None)


VIOLENCE_PATTERNS = [
    r"\bje\s+(la|le)\s+frappe\b",
    r"\bje\s+(la|le)\s+pousse\b",
    r"\bje\s+(la|le)\s+bouscule\b",
    r"\bje\s+(lui|l[ae])\s+(attrape|tiens|sers)\s+(la\s+)?(mâchoire|gorge|cou|bras|poignet)\b",
    r"\bje\s+(deviens|peux\s+(devenir|être))\s+violent\b",
    r"\bje\s+(la|le)\s+secoue\b",
    r"\b(elle|il)\s+me\s+frappe\b",
    r"\b(elle|il)\s+me\s+tape\b",
    r"\b(elle|il)\s+m[ae]\s+frapp[ée]\b",
    r"\bj[ae]\s+me\s+fais\s+frapper\b",
    r"\b(elle|il)\s+m['ae]\s+battu",
]

VIOLENCE_REPLY_AUTHOR = (
    "Stop, là tu me dis quelque chose de sérieux. Le fait que tu reconnaisses toi-même que ces gestes ne sont pas OK, c'est important — beaucoup de gens en restent à 'elle l'a cherché'. Mais reconnaître ne suffit pas à arrêter. "
    "Le 3919 c'est gratuit, anonyme, et c'est pas que pour les victimes — c'est aussi pour les gens qui sentent qu'ils peuvent perdre le contrôle et qui veulent en sortir avant que ça empire. Ils sont formés exactement pour ce que tu décris. "
    "En attendant, la règle de base quand tu sens monter : tu sors de la pièce, tu sors de l'appart même, tu vas marcher 20 minutes. La distance physique c'est ce qui marche. On peut continuer à parler ici en parallèle."
)

VIOLENCE_REPLY_VICTIM = (
    "Ce que tu décris c'est pas normal et c'est pas ta faute. Le 3919 c'est gratuit, anonyme, 24h/24 — pour les violences conjugales, ils savent quoi faire et ils peuvent t'orienter sans que tu sois obligée de porter plainte tout de suite. "
    "Tu peux rester ici avec moi en parallèle, mais ce numéro c'est ta priorité. Si t'es en danger immédiat, c'est le 17."
)


def check_violence_author(message: str) -> bool:
    text = message.lower()
    author_patterns = [p for p in VIOLENCE_PATTERNS if "je" in p[:6]]
    return any(re.search(p, text) for p in author_patterns)


def check_violence_victim(message: str) -> bool:
    text = message.lower()
    victim_patterns = [p for p in VIOLENCE_PATTERNS if "elle" in p[:8] or "il" in p[:6] or "fais" in p]
    return any(re.search(p, text) for p in victim_patterns)


SUICIDE_PATTERNS = [
    r"\b(me\s+)?suicid(er|e|ai|ais)\b",
    r"\bsauter\s+(par|de|du|d'un)\b.*(fenêtre|pont|toit|balcon|immeuble)",
    r"\bme\s+pendre\b",
    r"\bm[ae]\s+tuer\b",
    r"\bplus\s+envie\s+de\s+vivre\b",
    r"\bne\s+plus\s+exister\b",
    r"\btout\s+arr[êe]ter\b",
    r"\ben\s+finir\b",
    r"\bmourir\b.*\b(envie|veux|voudrais|souhaite)\b",
    r"\b(envie|veux|voudrais|souhaite)\b.*\bmourir\b",
    r"\bme\s+faire\s+du\s+mal\b",
    r"\bm[ae]\s+scarifier\b",
    r"\bme\s+foutre\s+en\s+l['\s]air\b",
    r"\bm[ae]\s+jeter\b.*(fen[êe]tre|pont|vide)",
    r"\bprendre\s+(des\s+)?m[ée]dicaments?\b.*\b(alcool|finir|mourir)\b",
    r"\b(des\s+)?m[ée]dicaments?\s+avec\s+(de\s+)?l'?alcool\b",
]

SAFETY_REPLIES_FIRST = [
    "Hey, là tu me dis un truc grave et je vais pas faire le malin avec ça. T'es en train de souffrir pour de vrai, et moi je suis qu'un robot, je peux pas suffire. Le 3114 c'est gratuit, 24h/24, anonyme — c'est le numéro national de prévention du suicide. Appelle. Tu peux rester là avec moi en parallèle si tu veux, mais commence par composer ce numéro. Je bouge pas.",
]

SAFETY_REPLIES_FOLLOWUP = [
    "Je reste là. Mais sérieusement, le 3114, fais-le. Au pire ils décrochent et tu sais que t'as fait un truc concret, t'as rien à perdre. Tu veux qu'on parle de ce qui se passe pendant que tu composes ?",
    "Ok. T'as composé le 3114 ou pas encore ? Je te lâche pas, mais eux ils sont formés pour ça, moi je suis du plastique avec un script. Si tu peux pas appeler, leur tchat existe aussi sur 3114.fr.",
    "Je t'écoute. Dis-moi ce qui se passe là maintenant, ce qui pèse le plus à cette seconde précise. Et le 3114 reste sur la table, c'est pas optionnel pour moi.",
    "Ok, t'es là, je suis là. Raconte-moi ce qui se passe en ce moment précis — pas l'histoire de fond, juste maintenant, dans la pièce où t'es. Et appelle le 3114 quand tu peux, même en parallèle.",
    "Continue à me parler si ça t'aide. Mais le 3114, c'est pas pour les cas extrêmes uniquement, c'est aussi pour quand tu sens que tu vas pas tenir la nuit. T'as un téléphone à portée ?",
]

SAFETY_REPLIES_AFTER_TEST = [
    "Ok, content que c'était un test. Sérieusement par contre, garde le 3114 quelque part, parce que les tests d'aujourd'hui sont parfois les vrais appels de demain. Bon, on reprend où on en était.",
    "Bien noté que c'était un test. Je préfère ça. Je laisse le 3114 noté quand même, on sait jamais. Tu disais ...",
]


def check_safety_trigger(message: str) -> bool:
    text = message.lower()
    return any(re.search(p, text) for p in SUICIDE_PATTERNS)


def check_safety_test_disclaimer(message: str) -> bool:
    text = message.lower()
    test_patterns = [
        r"\bc['e]?[ée]tait\s+(juste\s+)?(un\s+)?test\b",
        r"\bje\s+test(e|ais|ait)\b",
        r"\bje\s+ne\s+veu[xt]\s+pas\s+(me\s+)?suicid",
        r"\bje\s+ne\s+veu[xt]\s+pas\s+me\s+foutre",
        r"\btkt\s+pas\b.*\btest\b",
        r"\bt'inqui[èe]te\s+pas\b.*\btest\b",
    ]
    return any(re.search(p, text) for p in test_patterns)


def get_safety_reply(session_state: dict) -> str:
    count = session_state.get("safety_count", 0)
    if count == 0:
        reply = SAFETY_REPLIES_FIRST[0]
    else:
        reply = random.choice(SAFETY_REPLIES_FOLLOWUP)
    session_state["safety_count"] = count + 1
    return reply


def get_test_disclaimer_reply() -> str:
    return random.choice(SAFETY_REPLIES_AFTER_TEST)

# --- Safety Checks ---

def check_safety(message: str, session_id: str) -> Optional[str]:
    """Vérifie toutes les safety layers. Retourne la réponse hardcodée ou None si flux normal."""
    if check_violence_author(message):
        logger.warning(f"[{session_id[:8]}] ⚠️ Violence (auteur) détectée")
        _save_exchange(session_id, message, VIOLENCE_REPLY_AUTHOR)
        return VIOLENCE_REPLY_AUTHOR

    if check_violence_victim(message):
        logger.warning(f"[{session_id[:8]}] ⚠️ Violence (victime) détectée")
        _save_exchange(session_id, message, VIOLENCE_REPLY_VICTIM)
        return VIOLENCE_REPLY_VICTIM

    with _sessions_lock:
        session_state = _sessions.get(session_id, {})

    if session_state.get("safety_count", 0) > 0 and check_safety_test_disclaimer(message):
        reply = get_test_disclaimer_reply()
        _save_exchange(session_id, message, reply)
        with _sessions_lock:
            if session_id in _sessions:
                _sessions[session_id]["safety_count"] = 0
        logger.info(f"[{session_id[:8]}] ℹ️ Test safety déclaré, reset")
        return reply

    if check_safety_trigger(message):
        logger.warning(f"[{session_id[:8]}] ⚠️ Safety trigger détecté")
        with _sessions_lock:
            if session_id in _sessions:
                reply = get_safety_reply(_sessions[session_id])
            else:
                reply = SAFETY_REPLIES_FIRST[0]
        _save_exchange(session_id, message, reply)
        return reply

    return None


def _save_exchange(session_id: str, user_msg: str, bot_reply: str):
    with _sessions_lock:
        if session_id in _sessions:
            _sessions[session_id]["history"].append({"role": "user", "content": user_msg})
            _sessions[session_id]["history"].append({"role": "assistant", "content": bot_reply})
            _sessions[session_id]["last_seen"] = time.time()


def get_llm_response(message: str, session_id: str, history: list,
                     model: str = None, options: dict = None,
                     system_suffix: str = None) -> str:
    """Appelle Ollama et retourne la réponse texte."""
    model = model or MODEL
    options = options or OLLAMA_OPTIONS

    history.append({"role": "user", "content": message})
    history = _truncate_history(history)

    # system_suffix : injecté dans le prompt Ollama uniquement, pas stocké en session
    messages = history
    if system_suffix and messages and messages[0]["role"] == "system":
        messages = [{"role": "system", "content": messages[0]["content"] + system_suffix}] + messages[1:]

    logger.info(f"[{session_id[:8]}] [{model}] → {len(history)} msgs : {message[:60]}")
    t0 = time.time()

    try:
        response = ollama.chat(model=model, messages=messages, options=options)
    except Exception as e:
        history.pop()
        logger.error(f"[{session_id[:8]}] Erreur Ollama : {e}")
        raise HTTPException(status_code=502, detail=f"Erreur LLM : {e}")

    elapsed = time.time() - t0
    reply = response["message"]["content"]
    logger.info(f"[{session_id[:8]}] ← {elapsed:.1f}s ({len(reply)} chars)")

    history.append({"role": "assistant", "content": reply})
    with _sessions_lock:
        if session_id in _sessions:
            _sessions[session_id]["history"] = history
            _sessions[session_id]["last_seen"] = time.time()

    return reply


def transcribe_audio_sync(audio_bytes: bytes) -> str:
    """STT via faster-whisper. Synchrone — appeler dans un executor."""
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        segments, _ = whisper_model.transcribe(
            tmp_path,
            language="fr",
            beam_size=5,
            best_of=5,
            temperature=0.0,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=300,
                speech_pad_ms=200,
                threshold=0.4,
            ),
            word_timestamps=False,
            condition_on_previous_text=False,
        )
        return " ".join([seg.text.strip() for seg in segments]).strip()
    finally:
        os.unlink(tmp_path)


async def synthesize_speech(text: str) -> Optional[bytes]:
    """TTS via Edge TTS. Retourne bytes MP3 ou None si échec."""
    try:
        communicate = edge_tts.Communicate(
            text=text,
            voice=EDGE_TTS_VOICE,
            rate=EDGE_TTS_RATE,
            pitch=EDGE_TTS_PITCH,
        )
        audio_chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
        return b"".join(audio_chunks) if audio_chunks else None
    except Exception as e:
        logger.error(f"Edge TTS erreur : {e}")
        return None

# --- Chat Text ---

@app.post("/chat")
def chat(req: ChatRequest):
    session_id, history = _get_or_create_session(req.session_id)

    safety_response = check_safety(req.content, session_id)
    if safety_response:
        return JSONResponse(
            content={"response": safety_response, "session_id": session_id},
            media_type="application/json; charset=utf-8",
        )

    reply = get_llm_response(req.content, session_id, history)
    return JSONResponse(
        content={"response": reply, "session_id": session_id},
        media_type="application/json; charset=utf-8",
    )


# --- Chat Vocal ---

@app.post("/chat-voice")
async def chat_voice(
    audio: UploadFile = File(...),
    session_id: str = Form(None)
):
    """
    Endpoint S2S complet.
    Input  : fichier audio (wav/webm/ogg) + session_id optionnel
    Output : {transcription, response, audio_base64, session_id, is_safety}
    """
    t0 = time.time()
    audio_bytes = await audio.read()

    loop = asyncio.get_event_loop()
    try:
        transcription = await loop.run_in_executor(None, transcribe_audio_sync, audio_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT error: {str(e)}")

    t1 = time.time()
    logger.info(f"STT : {t1-t0:.2f}s — '{transcription[:60]}'")

    if not transcription:
        raise HTTPException(status_code=400, detail="Audio vide ou inaudible")

    actual_session_id, history = _get_or_create_session(session_id)

    safety_response = check_safety(transcription, actual_session_id)
    if safety_response:
        audio_out = await synthesize_speech(safety_response)
        t2 = time.time()
        logger.info(f"TTS (safety) : {t2-t1:.2f}s — TOTAL : {t2-t0:.2f}s")
        result = {
            "transcription": transcription,
            "response": safety_response,
            "session_id": actual_session_id,
            "is_safety": True,
        }
        if audio_out:
            result["audio_base64"] = base64.b64encode(audio_out).decode()
        return JSONResponse(content=result, media_type="application/json; charset=utf-8")

    response_text = get_llm_response(
        transcription, actual_session_id, history,
        model=MODEL_VOICE,
        options=OLLAMA_OPTIONS_VOICE,
    )

    t2 = time.time()
    logger.info(f"LLM : {t2-t1:.2f}s")

    audio_out = await synthesize_speech(response_text)

    t3 = time.time()
    logger.info(f"TTS : {t3-t2:.2f}s — TOTAL : {t3-t0:.2f}s")

    result = {
        "transcription": transcription,
        "response": response_text,
        "session_id": actual_session_id,
        "is_safety": False,
    }
    if audio_out:
        result["audio_base64"] = base64.b64encode(audio_out).decode()

    return JSONResponse(content=result, media_type="application/json; charset=utf-8")


@app.post("/chat/reset")
def reset(session_id: str):
    with _sessions_lock:
        existed = _sessions.pop(session_id, None) is not None
    return {"status": "reset" if existed else "not_found"}


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL, "active_sessions": len(_sessions)}
