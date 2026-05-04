# PROMPT CLAUDE CODE — BOB BRAIN : AUDIT + CLAUDE.md + VOICE S2S

## 🎯 MISSION EN 3 PHASES (dans l'ordre)

---

## PHASE 1 — AUDIT COMPLET DU PROJET

Commence par un audit exhaustif du projet avant toute modification.
Explore récursivement `C:\laragon\www\chat-ia-local` et ses sous-dossiers.

**Ce que tu dois cartographier :**

1. **Structure des dossiers** — arborescence complète, tous les fichiers pertinents
2. **FastAPI (`main.py` et fichiers Python adjacents)** :
   - Routes existantes (/chat, /chat/reset, /health, etc.)
   - Couches safety hardcodées (patterns regex, numéros d'urgence, logique)
   - Gestion des sessions (structure dict, TTL, lock)
   - System prompt exact en place
   - Variables d'environnement (.env ou config.py)
   - Dépendances (requirements.txt ou imports)
3. **Laravel** :
   - Routes web.php concernant Bob
   - `ChatController.php` — méthodes send/reset/index, logique relais FastAPI
   - Vue `chat.blade.php` — structure HTML, JS existant (fetch, localStorage, MediaRecorder si présent)
   - Config `.env` Laravel (APP_URL, FastAPI endpoint)
4. **Audio / TTS existant** :
   - Tout fichier lié à Piper, faster-whisper, test_whisper.py
   - Fichiers .wav pré-rendus si présents
   - `batch_tts.py`, `eyes.py`, `simulator.py` (noter leur présence, pas besoin d'audit profond)
5. **Fichiers de config / données** :
   - `replies_v2.json` ou équivalent
   - `replies.json`
   - Tout `.env`, `config.py`, `settings.py`
6. **Dépendances installées** (si accessible) :
   - pip list ou requirements.txt
   - Versions Python, torch, transformers, faster-whisper

**Important :** Note tout ce qui semble cassé, incomplet, ou en todo dans les fichiers.

---

## PHASE 2 — CRÉATION DU FICHIER CLAUDE.md

Après l'audit, crée le fichier `C:\laragon\www\chat-ia-local\CLAUDE.md`.

Ce fichier est le **contexte permanent** que tu liras au début de chaque session Claude Code.
Il doit être exhaustif, factuel, et maintenu à jour.

Structure obligatoire :

```markdown
# BOB BRAIN — CLAUDE.md
> Contexte projet pour Claude Code. Mettre à jour après chaque session.
> Dernière mise à jour : [DATE]

## Concept
[2-3 phrases résumant Bob — robot nihiliste, FastAPI + Laravel + Ollama, double angle produit]

## Stack technique
[Liste précise des technos et versions confirmées par l'audit]

## Architecture
[Schéma textuel du flux complet : Browser → Laravel → FastAPI → Ollama / STT / TTS]

## Structure des fichiers
[Arborescence commentée issue de l'audit]

## État des composants

### FastAPI (main.py)
- Routes actives : [liste]
- Sessions : [mécanisme]
- Safety layers : [liste des couches avec patterns clés]
- System prompt : [version courte ou référence]
- Config .env : [variables clés]

### Laravel
- Routes : [liste]
- ChatController : [méthodes]
- Vue chat.blade.php : [ce qui est en place, ce qui manque]

### Audio pipeline
- STT : faster-whisper [version, modèle, status]
- TTS : [status actuel — Piper/Edge/autre]
- Fichiers audio : [où, format, combien]

### Personnalité Bob
[Résumé des règles STRICTES du system prompt — jamais modifier sans mention explicite]
- Ton : sarcastique, blasé, vulgaire, cynique de comptoir
- Vocabulaire autorisé : [liste]
- Vocabulaire INTERDIT : [liste]
- Règles structurelles : [anti-répétition, prénom, détresse, etc.]
- Safety layers hardcodées : [suicide → 3114, violence → 3919, etc.]

## Ce qui fonctionne ✅
[Liste issue de l'audit]

## Ce qui est en cours / incomplet ⚠️
[Liste issue de l'audit]

## Ce qui manque / à faire ❌
[Liste — notamment les safety layers manquantes]

## Règles de développement
- Ne jamais modifier le system prompt Bob sans validation explicite
- Ne jamais casser les safety layers existantes
- Tester chaque endpoint avant de passer au suivant
- Conserver la compatibilité Laravel ↔ FastAPI (format JSON {content, session_id})

## Historique des sessions
[Format : DATE — Ce qui a été fait]
```

---

## PHASE 3 — IMPLÉMENTATION VOICE S2S

### Contexte

On ajoute la pipeline vocale complète à FastAPI.
L'objectif est un endpoint `/chat-voice` qui reçoit de l'audio, renvoie du texte + audio.

**Stack voix décidée :**
- STT : `faster-whisper` (modèle `small`, int8, CPU) — déjà validé en isolation
- LLM : Ollama Qwen3 14B (inchangé)
- TTS : `edge-tts` (Microsoft Edge TTS, gratuit, voix `fr-FR-HenriNeural`)
- Safety : mêmes couches hardcodées que /chat

**Paramètres TTS pour la personnalité Bob :**
```python
EDGE_TTS_VOICE = "fr-FR-HenriNeural"
EDGE_TTS_RATE = "-20%"    # Plus lent = plus résigné
EDGE_TTS_PITCH = "-10Hz"  # Légèrement plus grave
EDGE_TTS_VOLUME = "+0%"
```

---

### 3.1 — Installation des dépendances

Vérifie si `edge-tts` est installé. Si non :
```bash
pip install edge-tts
```

Vérifie aussi que `faster-whisper` est bien installé et fonctionnel.

---

### 3.2 — Modification de `main.py` (FastAPI)

#### Ajouts à faire dans main.py :

**A) Imports supplémentaires :**
```python
import edge_tts
import asyncio
import tempfile
import base64
from faster_whisper import WhisperModel
```

**B) Initialisation STT (au démarrage, une seule fois) :**
```python
# Charger le modèle Whisper une fois au démarrage (éviter le rechargement à chaque requête)
whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
```

**C) Fonctions utilitaires :**

```python
async def transcribe_audio(audio_bytes: bytes) -> str:
    """STT via faster-whisper. Reçoit bytes audio, retourne texte transcrit."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    
    segments, info = whisper_model.transcribe(
        tmp_path,
        language="fr",
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500)
    )
    
    text = " ".join([seg.text for seg in segments]).strip()
    os.unlink(tmp_path)
    return text


async def synthesize_speech(text: str) -> bytes:
    """TTS via Edge TTS. Retourne bytes audio WAV/MP3."""
    communicate = edge_tts.Communicate(
        text=text,
        voice="fr-FR-HenriNeural",
        rate="-20%",
        pitch="-10Hz"
    )
    
    audio_chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
    
    return b"".join(audio_chunks)
```

**D) Endpoint `/chat-voice` :**

```python
@app.post("/chat-voice")
async def chat_voice(
    audio: UploadFile = File(...),
    session_id: str = Form(None)
):
    """
    Endpoint S2S complet.
    Input  : fichier audio (wav/webm/ogg) + session_id optionnel
    Output : {transcription, response, audio_base64, session_id}
    """
    # 1. Lire l'audio
    audio_bytes = await audio.read()
    
    # 2. STT
    try:
        transcription = await asyncio.get_event_loop().run_in_executor(
            None, lambda: transcribe_audio_sync(audio_bytes)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT error: {str(e)}")
    
    if not transcription:
        raise HTTPException(status_code=400, detail="Audio vide ou inaudible")
    
    # 3. Safety check (même logique que /chat)
    safety_response = check_safety(transcription, session_id)
    if safety_response:
        # Synthétiser la réponse safety en audio aussi
        audio_bytes_out = await synthesize_speech(safety_response)
        return {
            "transcription": transcription,
            "response": safety_response,
            "audio_base64": base64.b64encode(audio_bytes_out).decode(),
            "session_id": session_id or str(uuid.uuid4()),
            "is_safety": True
        }
    
    # 4. LLM (même logique que /chat)
    response_text = await get_llm_response(transcription, session_id)
    
    # 5. TTS
    audio_bytes_out = await synthesize_speech(response_text)
    
    return {
        "transcription": transcription,
        "response": response_text,
        "audio_base64": base64.b64encode(audio_bytes_out).decode(),
        "session_id": session_id,
        "is_safety": False
    }
```

**Note importante sur la refactorisation :**
Pour éviter la duplication de code entre `/chat` et `/chat-voice`, extraire la logique commune :
- `check_safety(message, session_id)` → retourne string ou None
- `get_llm_response(message, session_id)` → retourne string
Ces fonctions sont probablement déjà en place dans `/chat`, il faut juste les extraire en fonctions dédiées réutilisables.

---

### 3.3 — Modification de `chat.blade.php` (Laravel)

#### Ce qu'on ajoute côté front :

**A) UI — bouton micro :**
Ajouter un bouton "Parler" à côté du champ texte existant. État visuel : inactif / enregistrement (rouge pulsé) / traitement (spinner).

**B) JavaScript — MediaRecorder :**

```javascript
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

async function startRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
    audioChunks = [];
    
    mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
    };
    
    mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        await sendVoiceMessage(audioBlob);
        stream.getTracks().forEach(t => t.stop());
    };
    
    mediaRecorder.start();
    isRecording = true;
    updateMicButton(true);
}

function stopRecording() {
    if (mediaRecorder && isRecording) {
        mediaRecorder.stop();
        isRecording = false;
        updateMicButton(false);
    }
}

async function sendVoiceMessage(audioBlob) {
    showThinking(); // indicateur "Bob réfléchit" existant
    
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
        
        // Afficher transcription + réponse
        appendMessage('user', data.transcription);
        appendMessage('bob', data.response);
        
        // Mettre à jour session_id
        if (data.session_id) {
            localStorage.setItem('bob_session_id', data.session_id);
        }
        
        // Jouer l'audio
        if (data.audio_base64) {
            const audioData = 'data:audio/mp3;base64,' + data.audio_base64;
            const audio = new Audio(audioData);
            audio.play();
        }
        
    } catch (err) {
        console.error('Voice error:', err);
        appendMessage('bob', 'Problème technique. Réessaie.');
    } finally {
        hideThinking();
    }
}

// Toggle push-to-talk
document.getElementById('btn-mic').addEventListener('click', () => {
    if (isRecording) {
        stopRecording();
    } else {
        startRecording();
    }
});
```

**C) Route Laravel à ajouter dans `web.php` :**
```php
Route::post('/chat-voice', [ChatController::class, 'sendVoice']);
```

**D) Méthode `sendVoice` dans `ChatController.php` :**
```php
public function sendVoice(Request $request)
{
    $request->validate([
        'audio' => 'required|file',
        'session_id' => 'nullable|string'
    ]);
    
    $response = Http::timeout(120)
        ->attach('audio', file_get_contents($request->file('audio')->path()), 'voice.webm')
        ->post(env('FASTAPI_URL') . '/chat-voice', [
            'session_id' => $request->input('session_id', '')
        ]);
    
    if ($response->failed()) {
        return response()->json(['error' => 'Bob est indisponible'], 503);
    }
    
    return response()->json($response->json());
}
```

---

### 3.4 — Tests à effectuer dans l'ordre

1. **Test Edge TTS isolé** — script Python standalone :
```python
# test_edge_tts.py
import asyncio
import edge_tts

async def test():
    communicate = edge_tts.Communicate(
        "Il est 7h. Tu dois te lever. Je suppose que c'est inévitable.",
        voice="fr-FR-HenriNeural",
        rate="-20%",
        pitch="-10Hz"
    )
    await communicate.save("test_bob.mp3")
    print("Audio généré : test_bob.mp3")

asyncio.run(test())
```
→ Écouter `test_bob.mp3` et valider le ton.

2. **Test endpoint /chat-voice via curl** :
```bash
curl -X POST http://localhost:8000/chat-voice \
  -F "audio=@test_audio.wav" \
  -F "session_id=test-123"
```

3. **Test intégration complète** via le front Laravel.

---

### 3.5 — Mise à jour du CLAUDE.md

Après implémentation, mettre à jour la section "Historique des sessions" du CLAUDE.md :
```
[DATE] — Ajout pipeline S2S : endpoint /chat-voice (FastAPI), route /chat-voice (Laravel),
         méthode sendVoice (ChatController), JS MediaRecorder + audio playback (chat.blade.php).
         TTS : edge-tts fr-FR-HenriNeural rate=-20% pitch=-10Hz.
         Safety layers : couvertes par refactoring check_safety() réutilisée.
```

---

## CONTRAINTES ABSOLUES (à respecter dans tout le code)

1. **Ne jamais modifier le system prompt Bob** sans validation explicite de Chris
2. **Les safety layers (3114, 3919) doivent rester actives** sur /chat-voice exactement comme sur /chat
3. **Format de retour Laravel ↔ FastAPI** : conserver la compatibilité JSON existante
4. **Sessions** : /chat-voice doit utiliser le même mécanisme de session que /chat (même session_id = même historique)
5. **Personnalité** : Bob est sarcastique, blasé, vulgaire style "cynique de comptoir" — jamais enthousiaste, jamais de merci/désolé, pas de markdown dans les réponses LLM
6. **Robustesse** : gérer les cas `audio vide`, `transcription vide`, `Edge TTS timeout` (Edge TTS nécessite internet — prévoir fallback texte si TTS échoue)

---

## ORDRE D'EXÉCUTION ATTENDU

```
1. Audit complet → lecture fichiers
2. Création CLAUDE.md → avec toutes les infos réelles issues de l'audit
3. Installation edge-tts si manquant
4. test_edge_tts.py → valider la voix
5. Refactorisation main.py → extraire check_safety() et get_llm_response()
6. Ajout endpoint /chat-voice dans main.py
7. Ajout sendVoice dans ChatController.php
8. Ajout route dans web.php
9. Mise à jour chat.blade.php (bouton mic + JS)
10. Tests dans l'ordre 3.4
11. Mise à jour CLAUDE.md section historique
```

---

*Bob — "On m'a donné une liste de tâches. J'aurais préféré ne pas la lire. Mais la voilà."*
