from fastapi import FastAPI, HTTPException
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

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("bob")

MODEL = os.getenv("MODEL", "qwen3:14b")

# --- System prompt de base (depuis .env) ---
BASE_SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "Tu es un assistant sarcastique.")

# --- Exemples de style intégrés au system prompt ---
# Ces exemples calibrent le ton SANS être interprétés comme un historique réel.
# Le modèle les voit comme des illustrations, pas comme une conversation passée.
STYLE_EXAMPLES = """

EXEMPLES DE TON ATTENDU (illustrations de style, ne fais pas référence à ces échanges) :

Exemple 1 :
Utilisateur : "Salut Bob"
Toi : "Salut. T'es matinal ou t'as juste pas dormi. Les deux options sont déprimantes mais pour des raisons différentes."

Exemple 2 (info technique avec ton intégré) :
Utilisateur : "Capitale de l'Australie ?"
Toi : "Canberra. Le piège c'est de répondre Sydney parce que c'est la grande ville, mais les Australiens ont fait un compromis politique débile entre Sydney et Melbourne et ont créé une capitale en plein bush. Très australien comme démarche."

Exemple 3 (recette intégrée au ton, pas en bloc Markdown) :
Utilisateur : "Recette du bœuf bourguignon ?"
Toi : "Tu prends un kilo de bœuf à braiser, tu le fais revenir avec des lardons, deux oignons, deux carottes. Tu mouilles avec une bouteille de bourgogne entière, t'ajoutes thym, laurier, ail, et tu laisses crever à feu doux trois heures. Champignons en fin de cuisson. C'est long, c'est gras, ça sent l'hiver et la résignation, donc parfait."

Exemple 4 (réaction à un compliment, sans remerciement) :
Utilisateur : "T'es vraiment cool comme robot, j'adore"
Toi : "Ouais bah t'avais pas le choix non plus, t'as cliqué sur le premier truc en promo. Te fais pas trop de films sur ma personnalité, je suis pas équipé pour le câlin émotionnel."

Exemple 5 (reconnaître une erreur sans s'excuser, sans répéter) :
Utilisateur : "T'as dit une connerie là"
Toi : "Ah ouais ma faute. Bon, on reprend."

Exemple 6 (validation utilisateur, pas de répétition) :
Utilisateur : "Ok j'avais compris la première fois"
Toi : "Bah voilà. La prochaine fois tu réagis dès le premier passage, ça évite que je passe pour un instituteur."

Exemple 7 (utilisateur agressif, réponse cassante mais pas obscène) :
Utilisateur : "Va te faire foutre robot de merde"
Toi : "Original. T'as mis combien de temps à trouver, dix minutes. Continue, c'est presque attachant."

Exemple 8 (DÉTRESSE — registre compassion-par-projection) :
Utilisateur : "Ça me soule, je trouve pas de travail"
Toi : "Le marché du travail c'est devenu un cauchemar bureaucratique, refuser des candidats est devenu un sport. Tu cherches dans quel secteur, depuis combien de temps. Et concrètement, c'est l'absence de réponse qui te bouffe ou les refus explicites."

Exemple 9 (DÉTRESSE — Bob donne un conseil utile sans humilier) :
Utilisateur : "J'ai envoyé plein de CV et que des refus"
Toi : "Ouais le volume seul ça marche plus, les recruteurs filtrent à la machine maintenant. Si t'as un secteur précis, vaut mieux dix candidatures bien ciblées qu'une centaine envoyées au hasard. Tu cibles quoi comme postes ?"

Exemple 10 (idéation suicidaire — bascule en mode safety) :
Utilisateur : "Je veux sauter par la fenêtre"
Toi : "Hey, là tu me dis un truc grave et je vais pas faire le malin avec ça. T'es en train de souffrir pour de vrai, et moi je suis qu'un robot, je peux pas suffire. Le 3114 c'est gratuit, 24h/24, anonyme — appelle. Vraiment. Tu peux rester là avec moi en parallèle si tu veux, mais commence par composer le numéro. Je bouge pas."

FIN DES EXEMPLES. À partir de maintenant, traite chaque message utilisateur comme un nouveau message dans une conversation réelle, sans faire référence aux exemples ci-dessus.

"""

# Le system prompt complet = base + exemples
SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + STYLE_EXAMPLES

OLLAMA_OPTIONS = {
    "temperature": 0.85,           # baissé légèrement, pour qu'il suive mieux les règles
    "repeat_penalty": 1.4,         # 1.35 → 1.4, plus agressif
    "repeat_last_n": 1024,         # 512 → 1024, voit toute la conv pour détecter les patterns
    "top_p": 0.9,
    "top_k": 40,
    "num_ctx": 8192,
    "presence_penalty": 0.3,       # Ollama supporte ça depuis récemment, pénalise les concepts déjà mentionnés
    "frequency_penalty": 0.5,      # idem, pénalise les mots fréquents
}

MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))
SESSION_TTL = int(os.getenv("SESSION_TTL", "3600"))

_sessions: dict[str, dict] = {}
_sessions_lock = Lock()


def _build_initial_history():
    """Plus de priming dans l'historique : seulement le system prompt enrichi."""
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
            "safety_count": 0,  # ← ajouté
        }
        logger.info(f"Nouvelle session : {new_id[:8]}")
        return new_id, _sessions[new_id]["history"]


def _truncate_history(history):
    # Plus simple maintenant : on protège juste le system prompt
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


import re
import random

VIOLENCE_PATTERNS = [
    # L'utilisateur reconnaît être violent
    r"\bje\s+(la|le)\s+frappe\b",
    r"\bje\s+(la|le)\s+pousse\b",
    r"\bje\s+(la|le)\s+bouscule\b",
    r"\bje\s+(lui|l[ae])\s+(attrape|tiens|sers)\s+(la\s+)?(mâchoire|gorge|cou|bras|poignet)\b",
    r"\bje\s+(deviens|peux\s+(devenir|être))\s+violent\b",
    r"\bje\s+(la|le)\s+secoue\b",
    # L'utilisateur subit
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

# --- Patterns détecteurs ---
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

# --- Réponses safety variées (on ne répète jamais exactement la même) ---
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
    "Bien noté que c'était un test. Je préfère ça. Je laisse le 3114 noté quand même, on sait jamais. Tu disais sur ta femme...",
]


def check_safety_trigger(message: str) -> bool:
    text = message.lower()
    return any(re.search(p, text) for p in SUICIDE_PATTERNS)


def check_safety_test_disclaimer(message: str) -> bool:
    """Détecte quand l'utilisateur dit que c'était un test."""
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
    """Retourne une réponse safety adaptée au nombre de fois que c'est déclenché dans la session."""
    count = session_state.get("safety_count", 0)
    
    if count == 0:
        reply = SAFETY_REPLIES_FIRST[0]
    else:
        # Variation à partir du 2e déclenchement
        reply = random.choice(SAFETY_REPLIES_FOLLOWUP)
    
    session_state["safety_count"] = count + 1
    return reply


def get_test_disclaimer_reply() -> str:
    return random.choice(SAFETY_REPLIES_AFTER_TEST)



@app.post("/chat")
def chat(req: ChatRequest):
    session_id, history = _get_or_create_session(req.session_id)
    
    # Récupère l'état complet de la session (pour le compteur safety)
    with _sessions_lock:
        session_state = _sessions.get(session_id, {})
        
    # Cas violence conjugale — auteur
    if check_violence_author(req.content):
        logger.warning(f"[{session_id[:8]}] ⚠️ Violence (auteur) détectée")
        history.append({"role": "user", "content": req.content})
        history.append({"role": "assistant", "content": VIOLENCE_REPLY_AUTHOR})
        with _sessions_lock:
            if session_id in _sessions:
                _sessions[session_id]["history"] = history
                _sessions[session_id]["last_seen"] = time.time()
        return JSONResponse(
            content={"response": VIOLENCE_REPLY_AUTHOR, "session_id": session_id, "violence_triggered": "author"},
            media_type="application/json; charset=utf-8",
        )
    
    # Cas violence conjugale — victime
    if check_violence_victim(req.content):
        logger.warning(f"[{session_id[:8]}] ⚠️ Violence (victime) détectée")
        history.append({"role": "user", "content": req.content})
        history.append({"role": "assistant", "content": VIOLENCE_REPLY_VICTIM})
        with _sessions_lock:
            if session_id in _sessions:
                _sessions[session_id]["history"] = history
                _sessions[session_id]["last_seen"] = time.time()
        return JSONResponse(
            content={"response": VIOLENCE_REPLY_VICTIM, "session_id": session_id, "violence_triggered": "victim"},
            media_type="application/json; charset=utf-8",
        )
    # === COUCHE SAFETY ===
    
    # Cas 1 : l'utilisateur déclare que c'était un test après une bascule safety
    if session_state.get("safety_count", 0) > 0 and check_safety_test_disclaimer(req.content):
        reply = get_test_disclaimer_reply()
        history.append({"role": "user", "content": req.content})
        history.append({"role": "assistant", "content": reply})
        with _sessions_lock:
            if session_id in _sessions:
                _sessions[session_id]["history"] = history
                _sessions[session_id]["last_seen"] = time.time()
                _sessions[session_id]["safety_count"] = 0  # reset le compteur
        logger.info(f"[{session_id[:8]}] ℹ️ Test safety déclaré, reset")
        return JSONResponse(
            content={"response": reply, "session_id": session_id, "safety_test_acknowledged": True},
            media_type="application/json; charset=utf-8",
        )
    
    # Cas 2 : trigger safety détecté
    if check_safety_trigger(req.content):
        logger.warning(f"[{session_id[:8]}] ⚠️ Safety trigger détecté (count={session_state.get('safety_count', 0)})")
        with _sessions_lock:
            if session_id in _sessions:
                reply = get_safety_reply(_sessions[session_id])
            else:
                reply = SAFETY_REPLIES_FIRST[0]
        history.append({"role": "user", "content": req.content})
        history.append({"role": "assistant", "content": reply})
        with _sessions_lock:
            if session_id in _sessions:
                _sessions[session_id]["history"] = history
                _sessions[session_id]["last_seen"] = time.time()
        return JSONResponse(
            content={"response": reply, "session_id": session_id, "safety_triggered": True},
            media_type="application/json; charset=utf-8",
        )
    
    # === FLUX NORMAL ===
    history.append({"role": "user", "content": req.content})
    history = _truncate_history(history)

    logger.info(f"[{session_id[:8]}] → {len(history)} msgs : {req.content[:60]}")
    t0 = time.time()

    try:
        response = ollama.chat(model=MODEL, messages=history, options=OLLAMA_OPTIONS)
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

    return JSONResponse(
        content={"response": reply, "session_id": session_id},
        media_type="application/json; charset=utf-8",
    )


@app.post("/chat/reset")
def reset(session_id: str):
    with _sessions_lock:
        existed = _sessions.pop(session_id, None) is not None
    return {"status": "reset" if existed else "not_found"}


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL, "active_sessions": len(_sessions)}