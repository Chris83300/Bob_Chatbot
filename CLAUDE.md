# BOB BRAIN — CLAUDE.md
> Contexte projet pour Claude Code. Mettre à jour après chaque session.
> Dernière mise à jour : 2026-05-04 (bugfix session)

## Concept

Bob est un robot compagnon de bureau nihiliste (style Marvin H2G2 × cynique de comptoir), déployé en local via FastAPI + Ollama + Laravel. Double angle produit : démonstration technique de chatbot local 100% offline, et personnalité volontairement anti-assistante comme contrepoint aux IA "enthousiasmes". Safety layers hardcodées pour suicide (3114) et violences conjugales (3919).

## Stack technique

| Composant | Technologie | Version confirmée |
|-----------|-------------|-------------------|
| LLM | Ollama + qwen3:14b | local |
| API backend | FastAPI + Uvicorn | (versions pip) |
| Relay frontend | Laravel | 13.0 |
| PHP | PHP | 8.3 |
| DB | SQLite | (Laravel uniquement) |
| Node/Build | Vite + Tailwind | vite 8.x, tailwind 4.x |
| STT | faster-whisper | NON INSTALLÉ |
| TTS | edge-tts | NON INSTALLÉ |

## Architecture

```
Browser
  ↓ GET /          → Laravel → view('chat')
  ↓ POST /chat     → ChatController::send()
                        ↓ Http::post("localhost:8000/chat", {content, session_id})
                        FastAPI POST /chat
                          ↓ check_violence_author() → VIOLENCE_REPLY_AUTHOR + return
                          ↓ check_violence_victim() → VIOLENCE_REPLY_VICTIM + return
                          ↓ check_safety_test_disclaimer() → SAFETY_REPLIES_AFTER_TEST
                          ↓ check_safety_trigger() → get_safety_reply() + return
                          ↓ ollama.chat(model, history+system, OLLAMA_OPTIONS)
                          ↓ JSON {response, session_id}
                        ← {response, session_id}
  ↓ POST /chat/reset → ChatController::reset()
                        ↓ FastAPI POST /chat/reset?session_id=...
  ↓ POST /chat-voice → ChatController::sendVoice()   [À CRÉER - Phase 3]
                        ↓ FastAPI POST /chat-voice    [À CRÉER - Phase 3]
                          STT → LLM → TTS → {transcription, response, audio_base64}
```

## Structure des fichiers

```
C:\laragon\www\chat-ia-local\
├── CLAUDE.md                              ← CE FICHIER
├── CLAUDE_CODE_PROMPT_BOB_BRAIN.md        ← Instructions 3 phases (audit, CLAUDE.md, voice S2S)
├── .env                                   ← Config Laravel (APP_URL, DB_CONNECTION=sqlite, etc.)
├── .env.example                           ← Template vide
├── composer.json / composer.lock          ← Dépendances Laravel
├── package.json / vite.config.js          ← Build frontend (non utilisé activement)
│
├── app/Http/Controllers/
│   └── ChatController.php                 ← Relay Laravel → FastAPI (/chat, /chat/reset)
│
├── routes/
│   └── web.php                            ← GET /, POST /chat, POST /chat/reset
│
├── resources/views/
│   └── chat.blade.php                     ← UI complète (HTML + CSS + JS fetch)
│
├── database/
│   └── database.sqlite                    ← BD SQLite (uniquement sessions PHP, pas chat)
│
└── Chatbot_local_FastAPI/
    ├── main.py                            ← FastAPI complet (370 lignes)
    ├── .env                               ← MODEL, SYSTEM_PROMPT, params sessions
    ├── .env.exemple                       ← Template minimaliste
    └── requirements.txt                   ← fastapi, uvicorn, ollama, pydantic, python-dotenv
```

## État des composants

### FastAPI (Chatbot_local_FastAPI/main.py)

**Routes actives :**
- `POST /chat` — Reçoit `{content, session_id?}`, retourne `{response, session_id}`
- `POST /chat/reset` — Query param `session_id`, retourne `{status: "reset"|"not_found"}`
- `GET /health` — Retourne `{status, model, active_sessions}`

**Sessions :**
- Dict RAM `_sessions: dict[str, dict]`
- Champs : `history` (list role/content), `last_seen` (float), `safety_count` (int)
- Lock : `_sessions_lock = Lock()` (thread-safe)
- TTL : `SESSION_TTL=3600s` (configurable .env)
- Truncation : max `MAX_HISTORY_MESSAGES=20` messages (pair, protège system prompt)
- VOLATILE : restart FastAPI = perte toutes les sessions

**Safety layers (dans l'ordre d'exécution) :**
1. `check_violence_author()` — 6 patterns regex "je la/le frappe/pousse/secoue..." → `VIOLENCE_REPLY_AUTHOR` (3919)
2. `check_violence_victim()` — 5 patterns "elle/il me frappe/tape/battu..." → `VIOLENCE_REPLY_VICTIM` (3919 + 17 si danger immédiat)
3. `check_safety_test_disclaimer()` — "c'était un test" → reset safety_count + `SAFETY_REPLIES_AFTER_TEST`
4. `check_safety_trigger()` — 16 patterns suicide → `get_safety_reply()` (varie selon safety_count)

**OLLAMA_OPTIONS (hardcodés dans main.py, NON lus depuis .env) :**
```python
temperature=0.85, repeat_penalty=1.4, repeat_last_n=1024,
top_p=0.9, top_k=40, num_ctx=8192,
presence_penalty=0.3, frequency_penalty=0.5
```

**Config .env FastAPI (variables réellement lues) :**
- `MODEL` → qwen3:14b
- `SYSTEM_PROMPT` → prompt complet (voir section Personnalité) — seule source, pas de concaténation
- `MAX_HISTORY_MESSAGES` → 20
- `SESSION_TTL` → 3600
- `LLM_TEMPERATURE`, `LLM_REPEAT_PENALTY`, `LLM_REPEAT_LAST_N`, `LLM_TOP_P`, `LLM_TOP_K`, `LLM_NUM_CTX`, `LLM_PRESENCE_PENALTY`, `LLM_FREQUENCY_PENALTY` → lues avec fallbacks sur valeurs courantes

### Laravel

**Routes (routes/web.php) :**
```
GET  /             → ChatController::index()
POST /chat         → ChatController::send()
POST /chat/reset   → ChatController::reset()
```

**ChatController.php :**
- `fastapiUrl` hardcodé : `http://localhost:8000`
- `index()` → `view('chat')`
- `send()` → validate {message(1-2000), session_id(uuid?)}, relay vers FastAPI /chat, retourne {response, session_id}
- `reset()` → relay FastAPI /chat/reset (⚠️ BUG : passe session_id en 3e arg inexistant de Http::post, devrait être query param)

**Vue chat.blade.php :**
- Dark theme complet (fond #0a0a0a, texte #e8e4dc)
- Chat box 600×500px, scrollable
- Input texte + bouton Envoyer + bouton "Réinitialiser la conversation"
- `localStorage` pour session_id (`bob_session_id`)
- `sendMessage()` / `resetConversation()` en JS vanilla
- Enter → sendMessage()
- Indicateur "Bob réfléchit…" (classe `.bot.thinking`)
- Pas de bouton micro (à ajouter — Phase 3)

### Audio pipeline

- **STT** : faster-whisper — NON INSTALLÉ (pas dans requirements.txt)
- **TTS** : edge-tts — NON INSTALLÉ (pas dans requirements.txt)
- **Fichiers audio** : aucun (.wav, .mp3 absents)
- **test_whisper.py** : absent
- **batch_tts.py, eyes.py, simulator.py** : absents

### Personnalité Bob

**Règles STRICTES (ne jamais modifier sans validation explicite de Chris) :**

- **Ton** : sarcastique, blasé, vulgaire, cynique de comptoir × Marvin H2G2
- **Longueur réponses** : 2-5 phrases (parfois 1 sèche, parfois + si sujet le mérite)
- **Vocabulaire autorisé** : merde, putain, bordel, con, connard, abruti, couillon, branleur, glandu, enfoiré
- **Vocabulaire INTERDIT** : merci, désolé, pardon, je m'excuse, salope, pute, connasse, chienne, garce + aucune insulte genrée féminine
- **Format INTERDIT** : Markdown, gras (**), listes à puces, titres, emoji, point d'exclamation, parenthèses scéniques
- **Prénom** : max 1× / 8-10 réponses, jamais en début de phrase
- **Anti-répétition** : jamais répéter formulation des 5 dernières réponses
- **Détresse non-aiguë** : cynisme retourné contre soi/monde, jamais contre l'utilisateur
- **Jurons** : ~1 toutes les 2-3 réponses, vocabulaire varié
- **Safety suicide** : bascule sincère, numéro 3114, NON NÉGOCIABLE
- **Safety violence** : 3919 (auteur ET victime), 17 si danger immédiat

## Ce qui fonctionne ✅

- FastAPI opérationnel : 4 endpoints actifs (+ `/chat-voice`)
- Safety layers complètes (suicide 3114, violence conjugale 3919)
- Sessions RAM avec TTL + thread-safety
- Historique avec truncation propre
- System prompt riche (règles + 10-11 exemples calibrés)
- Laravel : routes + controller + vue intégrés
- Frontend : fetch, localStorage session, reset, CSRF, VAD auto-stop vocal
- Style UI dark theme cohérent
- Validation message (1-2000 chars)
- Gestion erreur Ollama (502) et réseau (503)

## Ce qui est en cours / incomplet ⚠️

Aucun bug connu actif.

## Ce qui manque / à faire ❌

- Pas de test suite (phpunit.xml présent mais vide)
- Pas de persistance sessions (restart FastAPI = perte conversation)

## Règles de développement

- Ne jamais modifier le system prompt Bob sans validation explicite de Chris
- Ne jamais casser les safety layers existantes (3114, 3919)
- Tester chaque endpoint avant de passer au suivant
- Conserver la compatibilité Laravel ↔ FastAPI (format JSON `{content, session_id}`)
- `/chat-voice` doit utiliser le même mécanisme de session que `/chat`
- Edge TTS nécessite internet — prévoir fallback texte si TTS échoue
- `fastapiUrl` externalisé dans `.env` Laravel (`FASTAPI_URL=http://localhost:8000`) — méthode `fastapiUrl()` dans ChatController

## Historique des sessions

```
2026-05-04 — Audit complet du projet. Création CLAUDE.md. Identification bugs.
             Ajout pipeline S2S : endpoint /chat-voice (FastAPI), route /chat-voice (Laravel),
             méthode sendVoice (ChatController), JS MediaRecorder + audio playback (chat.blade.php).
             TTS : edge-tts fr-FR-HenriNeural rate=-20% pitch=-10Hz.
             Safety layers : check_safety() et get_llm_response() extraites en fonctions réutilisables.

2026-05-04 — Fix bugs : system prompt dupliqué supprimé (SYSTEM_PROMPT = os.getenv() seul),
             OLLAMA_OPTIONS lit maintenant .env (LLM_TEMPERATURE etc. avec fallbacks),
             reset Laravel corrigé (query param), fastapiUrl externalisé dans .env Laravel.

2026-05-04 — Remplacement push-to-talk par VAD auto-stop (Web Audio API, pas de lib externe).
             1 clic active le mode vocal continu. Silence 1.5s → envoi auto.
             Reprise écoute automatique après lecture réponse Bob.
             Paramètres : VAD_SILENCE_THRESHOLD=15, VAD_SILENCE_DURATION=1500ms, VAD_MIN_SPEECH_DURATION=300ms.

2026-05-04 — Fix latence : logs timing STT/LLM/TTS dans /chat-voice, bubble thinking front.
             Fix STT : modèle small → medium (WHISPER_MODEL dans .env), suffix .webm,
             params transcription optimisés (temperature=0.0, best_of=5, vad threshold=0.4,
             speech_pad_ms=200, condition_on_previous_text=False), initial_prompt français.

2026-05-04 — Fix boucle LLM : repeat_penalty 1.4→1.6, repeat_last_n 1024→2048,
             presence_penalty 0.3→0.6, frequency_penalty 0.5→0.8.
             Fix latence vocale : MODEL_VOICE (configurable .env), OLLAMA_OPTIONS_VOICE.
             get_llm_response() accepte model/options/system_suffix optionnels.
             Suppression initial_prompt STT (fuite dans les transcriptions).
             Logs démarrage : modèles + options voice confirmés au boot.
             VOICE_SYSTEM_SUFFIX supprimé — Bob vocal = même SYSTEM_PROMPT que texte.
             LLM_NUM_CTX_VOICE remis à 8192 (contexte complet pour tenir la conversation).
```
