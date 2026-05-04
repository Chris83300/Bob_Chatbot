# PROMPT CLAUDE CODE — BOB BRAIN : LATENCE + QUALITÉ STT

Projet : `C:\laragon\www\chat-ia-local`
Lis le `CLAUDE.md` en premier.

---

## PROBLÈME 1 — Latence `/chat-voice`

L'endpoint est actuellement séquentiel bloquant : STT complet → LLM complet → TTS complet → retour.
Il n'y a pas de streaming. Le LLM (Qwen3 14B) est le goulot principal.

### Fix A — Streaming LLM → TTS par phrases

Au lieu d'attendre la réponse LLM complète avant de lancer le TTS, on génère l'audio
phrase par phrase dès qu'elles arrivent du LLM, puis on les concatène.

Dans `main.py`, modifier la fonction qui appelle Ollama pour `/chat-voice` :

```python
async def get_llm_response_streaming(message: str, session_id: str) -> str:
    """
    Appelle Ollama en mode stream=True, reconstruit la réponse complète.
    Pour /chat-voice : collecter les tokens jusqu'à un point/virgule/fin
    puis lancer TTS sur ce segment pendant que le LLM continue.
    """
    # Pour l'instant : collecter streaming mais retourner complet
    # (base pour optimisation future phrase-par-phrase)
    with _sessions_lock:
        session = _get_or_create_session(session_id)
        history = session["history"].copy()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    messages.append({"role": "user", "content": message})

    response = ollama.chat(
        model=MODEL,
        messages=messages,
        stream=False,  # garder False pour l'instant, voir Fix B
        options=OLLAMA_OPTIONS
    )
    return response["message"]["content"]
```

### Fix B — Réduction du temps perçu côté front (plus impactant)

Le vrai gain est côté JavaScript : envoyer un **signal visuel immédiat** dès que l'audio
est envoyé, et jouer un son de "thinking" de Bob pendant le traitement.

Dans `chat.blade.php`, modifier `sendVoiceMessage()` :

```javascript
async function sendVoiceMessage(audioBlob) {
    isProcessing = true;
    updateMicButton('processing');

    // Feedback immédiat : afficher "Bob réfléchit..." dans le chat
    const thinkingId = showThinkingBubble();

    // Jouer le son de soupir/réflexion de Bob pendant qu'on attend
    // (optionnel — commenter si pas de fichier audio)
    // playThinkingSound();

    const formData = new FormData();
    formData.append('audio', audioBlob, 'voice.webm');
    formData.append('session_id', localStorage.getItem('bob_session_id') || '');

    try {
        const response = await fetch('/chat-voice', {
            method: 'POST',
            body: formData,
            headers: { 'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content }
        });

        const data = await response.json();
        removeThinkingBubble(thinkingId);

        if (data.transcription) appendMessage('user', data.transcription);
        appendMessage('bob', data.response);

        if (data.session_id) localStorage.setItem('bob_session_id', data.session_id);

        if (data.audio_base64) {
            const audio = new Audio('data:audio/mp3;base64,' + data.audio_base64);
            audio.onended = () => {
                isProcessing = false;
                if (voiceModeActive) startListening();
            };
            audio.play();
        } else {
            isProcessing = false;
            if (voiceModeActive) startListening();
        }

    } catch (err) {
        removeThinkingBubble(thinkingId);
        appendMessage('bob', 'Problème technique. Réessaie.');
        isProcessing = false;
        if (voiceModeActive) startListening();
    }
}

function showThinkingBubble() {
    const id = 'thinking-' + Date.now();
    const div = document.createElement('div');
    div.id = id;
    div.className = 'message bot thinking';
    div.textContent = '...';
    document.getElementById('chat-box').appendChild(div);
    div.scrollIntoView({ behavior: 'smooth' });
    return id;
}

function removeThinkingBubble(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}
```

### Fix C — Log des temps dans FastAPI (diagnostic)

Ajouter des timestamps dans `/chat-voice` pour identifier le vrai goulot :

```python
import time

@app.post("/chat-voice")
async def chat_voice(...):
    t0 = time.time()

    # STT
    transcription = await transcribe(audio_bytes)
    t1 = time.time()
    logger.info(f"STT : {t1-t0:.2f}s — '{transcription[:50]}'")

    # LLM
    response_text = await get_llm_response(transcription, session_id)
    t2 = time.time()
    logger.info(f"LLM : {t2-t1:.2f}s")

    # TTS
    audio_out = await synthesize_speech(response_text)
    t3 = time.time()
    logger.info(f"TTS : {t3-t2:.2f}s — TOTAL : {t3-t0:.2f}s")
```

---

## PROBLÈME 2 — Qualité STT (mots manquants / déformés)

### Causes probables

1. **Modèle `small` trop léger pour le français** — small est entraîné majoritairement sur
   l'anglais, les phonèmes français sont approximatifs
2. **Format audio webm/opus** — MediaRecorder envoie du webm, faster-whisper préfère du wav PCM
3. **VAD filter trop agressif** — coupe le début/fin des phrases
4. **beam_size trop bas** — moins précis mais plus rapide

### Fix 1 — Passer au modèle `medium` (recommandé)

Dans `main.py`, modifier l'initialisation Whisper :

```python
# Remplacer :
whisper_model = WhisperModel("small", device="cpu", compute_type="int8")

# Par :
whisper_model = WhisperModel("medium", device="cpu", compute_type="int8")
```

Medium est ~1.5Go RAM supplémentaire mais la qualité en français est nettement meilleure.
Le modèle se télécharge automatiquement au premier démarrage (~1.5Go).

**Aussi externaliser dans .env FastAPI :**
```
WHISPER_MODEL=medium
```
```python
whisper_model = WhisperModel(
    os.getenv("WHISPER_MODEL", "medium"),
    device="cpu",
    compute_type="int8"
)
```

### Fix 2 — Améliorer les paramètres de transcription

```python
def transcribe_audio_sync(audio_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        segments, info = whisper_model.transcribe(
            tmp_path,
            language="fr",           # forcer le français (évite détection auto erronée)
            beam_size=5,             # garder 5 (bon compromis)
            best_of=5,               # essayer 5 décodages, garder le meilleur
            temperature=0.0,         # déterministe (0.0 = plus précis, pas de hallucination)
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=300,   # réduire (était 500) — moins de coupures
                speech_pad_ms=200,             # ajouter 200ms avant/après la parole
                threshold=0.4,                 # seuil VAD (0.4 = moins agressif que défaut 0.5)
            ),
            word_timestamps=False,
            condition_on_previous_text=False,  # évite les hallucinations en boucle
        )

        text = " ".join([seg.text.strip() for seg in segments]).strip()
        return text

    finally:
        os.unlink(tmp_path)
```

### Fix 3 — Prompt initial Whisper pour le contexte français

faster-whisper accepte un `initial_prompt` qui guide le modèle sur le vocabulaire attendu :

```python
segments, info = whisper_model.transcribe(
    tmp_path,
    language="fr",
    initial_prompt="Voici une conversation en français avec un assistant vocal.",
    # ... autres params
)
```

---

## ORDRE D'APPLICATION

1. Ajouter les logs de temps (Fix C) → relancer FastAPI → faire un test vocal → voir dans
   le terminal quelle étape prend le plus de temps (STT / LLM / TTS)
2. Appliquer les fixes STT (Fix 1 medium + Fix 2 params + Fix 3 prompt)
3. Appliquer Fix B (bubble thinking côté front)
4. Retester et comparer les logs

---

## MISE À JOUR CLAUDE.md

```
2026-05-04 — Fix latence : logs timing STT/LLM/TTS, bubble thinking front.
             Fix STT : modèle small → medium, params transcription optimisés
             (temperature=0.0, best_of=5, vad threshold=0.4, speech_pad_ms=200),
             initial_prompt français, WHISPER_MODEL externalisé dans .env.
```
