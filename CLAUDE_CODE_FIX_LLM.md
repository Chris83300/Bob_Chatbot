# PROMPT CLAUDE CODE — BOB BRAIN : FIX BOUCLE LLM + LATENCE VOCALE

Projet : `C:\laragon\www\chat-ia-local`
Lis le `CLAUDE.md` en premier.

## Contexte du problème

Les logs montrent :
- STT : ~4s ✅ acceptable
- TTS : ~2s ✅ acceptable  
- LLM : 10s → 52s ❌ goulot principal, s'aggrave avec le contexte
- Bob boucle sur la même métaphore malgré repeat_penalty=1.4

## FIX 1 — Boucle LLM : durcir les pénalités de répétition

Dans `main.py`, modifier `OLLAMA_OPTIONS` (ou le `.env` FastAPI si déjà externalisé) :

```python
OLLAMA_OPTIONS = {
    "temperature":          float(os.getenv("LLM_TEMPERATURE", "0.85")),
    "repeat_penalty":       float(os.getenv("LLM_REPEAT_PENALTY", "1.6")),   # ↑ était 1.4
    "repeat_last_n":        int(os.getenv("LLM_REPEAT_LAST_N", "2048")),     # ↑ était 1024
    "top_p":                float(os.getenv("LLM_TOP_P", "0.9")),
    "top_k":                int(os.getenv("LLM_TOP_K", "40")),
    "num_ctx":              int(os.getenv("LLM_NUM_CTX", "8192")),
    "presence_penalty":     float(os.getenv("LLM_PRESENCE_PENALTY", "0.6")),  # ↑ était 0.3
    "frequency_penalty":    float(os.getenv("LLM_FREQUENCY_PENALTY", "0.8")), # ↑ était 0.5
}
```

Et dans `.env` FastAPI, mettre à jour les valeurs :
```
LLM_REPEAT_PENALTY=1.6
LLM_REPEAT_LAST_N=2048
LLM_PRESENCE_PENALTY=0.6
LLM_FREQUENCY_PENALTY=0.8
```

## FIX 2 — Latence : modèle dédié vocal plus léger

Qwen3 14B en CPU = 10-52s par requête. Trop lent pour du conversationnel vocal.

### Solution : modèle séparé pour `/chat-voice`

Utiliser un modèle plus léger UNIQUEMENT pour la voix. Le chat texte garde Qwen3 14B.

Dans `.env` FastAPI, ajouter :
```
MODEL_VOICE=qwen3:4b
```

Si `qwen3:4b` n'est pas encore téléchargé, Claude Code doit lancer dans un terminal :
```bash
ollama pull qwen3:4b
```

Dans `main.py`, charger les deux modèles :
```python
MODEL = os.getenv("MODEL", "qwen3:14b")         # chat texte
MODEL_VOICE = os.getenv("MODEL_VOICE", "qwen3:4b")  # chat vocal
```

Et dans l'endpoint `/chat-voice`, passer `MODEL_VOICE` à Ollama au lieu de `MODEL`.

### Options alternatives si qwen3:4b pas disponible (dans l'ordre de préférence)

1. `qwen3:8b` — bon compromis qualité/vitesse (~3-5s sur CPU)
2. `qwen3:1.7b` — très rapide (~1-2s) mais qualité moindre
3. `llama3.2:3b` — alternative si pas de qwen3 léger

Vérifier les modèles déjà disponibles localement avec :
```bash
ollama list
```
Choisir le plus petit déjà téléchargé, ou télécharger `qwen3:4b`.

## FIX 3 — Limiter la longueur des réponses vocales

Bob doit être encore plus court en vocal qu'en texte. Ajouter une instruction dans le
system prompt envoyé pour `/chat-voice` (pas le SYSTEM_PROMPT général — juste un suffix) :

```python
VOICE_SYSTEM_SUFFIX = "\n\nMODE VOCAL : réponses maximum 2 phrases courtes. Pas de métaphores longues. Direct."

# Dans /chat-voice, construire les messages avec le suffix :
messages = [{"role": "system", "content": SYSTEM_PROMPT + VOICE_SYSTEM_SUFFIX}] + history
messages.append({"role": "user", "content": transcription})
```

Ce suffix est hardcodé dans `main.py`, pas dans `.env` (c'est un paramètre technique, pas
de personnalité).

## FIX 4 — Réduire num_ctx pour le mode vocal

En vocal, l'historique court suffit. Moins de contexte = LLM plus rapide.

```python
OLLAMA_OPTIONS_VOICE = {
    **OLLAMA_OPTIONS,                    # hériter des options de base
    "num_ctx": int(os.getenv("LLM_NUM_CTX_VOICE", "4096")),  # ↓ moitié du contexte texte
}
```

Dans `.env` FastAPI :
```
LLM_NUM_CTX_VOICE=4096
```

Utiliser `OLLAMA_OPTIONS_VOICE` dans `/chat-voice` au lieu de `OLLAMA_OPTIONS`.

## ORDRE D'APPLICATION

1. `ollama list` → identifier quel modèle léger est disponible
2. Si aucun petit modèle → `ollama pull qwen3:4b` (laisser tourner)
3. Appliquer Fix 1 (pénalités répétition) dans main.py + .env
4. Appliquer Fix 2 (MODEL_VOICE) dans main.py + .env
5. Appliquer Fix 3 (VOICE_SYSTEM_SUFFIX) dans main.py
6. Appliquer Fix 4 (num_ctx réduit) dans main.py + .env
7. Relancer FastAPI : `uvicorn main:app --reload`
8. Test vocal : comparer les temps LLM dans les logs (objectif < 5s)

## MISE À JOUR CLAUDE.md

```
2026-05-04 — Fix boucle LLM : repeat_penalty 1.4→1.6, repeat_last_n 1024→2048,
             presence_penalty 0.3→0.6, frequency_penalty 0.5→0.8.
             Fix latence vocale : MODEL_VOICE séparé (qwen3:4b), OLLAMA_OPTIONS_VOICE
             avec num_ctx réduit à 4096, VOICE_SYSTEM_SUFFIX limite à 2 phrases.
```
