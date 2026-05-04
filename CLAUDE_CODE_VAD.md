# PROMPT CLAUDE CODE — BOB BRAIN : VAD AUTO-STOP MICRO

Projet : `C:\laragon\www\chat-ia-local`
Lis le `CLAUDE.md` en premier.

## Objectif

Remplacer le mode push-to-talk (clic → parle → reclique) par un mode VAD automatique :
- **1 clic** pour activer le micro (Bob écoute en continu)
- **Silence détecté** → envoi automatique + lecture réponse
- **Bob répond** → retour automatique en mode écoute (conversation continue)
- **1 clic** sur le bouton rouge pour stopper manuellement si besoin

## Implémentation — Web Audio API (pas de lib externe)

Modifier uniquement `resources/views/chat.blade.php`.

### Logique VAD à implémenter

```javascript
// Paramètres VAD (ajustables)
const VAD_SILENCE_THRESHOLD = 15;     // niveau RMS en dessous duquel = silence
const VAD_SILENCE_DURATION  = 2000;   // ms de silence avant envoi automatique
const VAD_MIN_SPEECH_DURATION = 300;  // ms de parole min avant d'activer le silence detector
                                       // (évite envoi immédiat si micro s'active avant que tu parles)

let audioContext, analyser, micStream, mediaRecorder;
let audioChunks = [];
let silenceTimer = null;
let speechDetected = false;
let isListening = false;
let isProcessing = false;  // true pendant que Bob génère/parle → ne pas réenregistrer

async function startListening() {
    if (isProcessing) return;  // Bob parle encore, on attend

    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioContext = new AudioContext();
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 512;

    const source = audioContext.createMediaStreamSource(micStream);
    source.connect(analyser);

    mediaRecorder = new MediaRecorder(micStream, { mimeType: 'audio/webm;codecs=opus' });
    audioChunks = [];
    speechDetected = false;

    mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
        if (speechDetected && audioChunks.length > 0) {
            await sendVoiceMessage(new Blob(audioChunks, { type: 'audio/webm' }));
        }
        // Nettoyer
        micStream.getTracks().forEach(t => t.stop());
        audioContext.close();
    };

    mediaRecorder.start(100);  // chunk toutes les 100ms
    isListening = true;
    updateMicButton('listening');
    detectSilence();  // boucle VAD
}

function detectSilence() {
    if (!isListening) return;

    const buffer = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(buffer);

    // Calcul RMS
    const rms = Math.sqrt(buffer.reduce((sum, v) => sum + v * v, 0) / buffer.length);

    if (rms > VAD_SILENCE_THRESHOLD) {
        // Parole détectée
        speechDetected = true;
        clearTimeout(silenceTimer);
        silenceTimer = null;
        updateMicButton('speaking');  // feedback visuel "Bob t'entend"
    } else if (speechDetected) {
        // Silence après parole → déclencher le timer
        if (!silenceTimer) {
            silenceTimer = setTimeout(() => {
                stopListening();  // envoi automatique
            }, VAD_SILENCE_DURATION);
        }
        updateMicButton('silence');  // feedback visuel "Bob attend la fin"
    }

    requestAnimationFrame(detectSilence);
}

function stopListening() {
    isListening = false;
    clearTimeout(silenceTimer);
    silenceTimer = null;
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
}

async function sendVoiceMessage(audioBlob) {
    isProcessing = true;
    updateMicButton('processing');

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

        appendMessage('user', data.transcription);
        appendMessage('bob', data.response);

        if (data.session_id) {
            localStorage.setItem('bob_session_id', data.session_id);
        }

        if (data.audio_base64) {
            const audio = new Audio('data:audio/mp3;base64,' + data.audio_base64);
            audio.onended = () => {
                isProcessing = false;
                // Relancer l'écoute automatiquement si le mode vocal est actif
                if (voiceModeActive) {
                    startListening();
                }
            };
            audio.play();
        } else {
            isProcessing = false;
            if (voiceModeActive) startListening();
        }

    } catch (err) {
        console.error('Voice error:', err);
        appendMessage('bob', 'Problème technique. Réessaie.');
        isProcessing = false;
        if (voiceModeActive) startListening();
    }
}
```

### État global et bouton

```javascript
let voiceModeActive = false;

// Le bouton micro toggle le mode vocal complet
document.getElementById('btn-mic').addEventListener('click', () => {
    if (!voiceModeActive) {
        voiceModeActive = true;
        startListening();
    } else {
        voiceModeActive = false;
        stopListening();
        isProcessing = false;
        updateMicButton('off');
    }
});

function updateMicButton(state) {
    const btn = document.getElementById('btn-mic');
    const states = {
        off:        { text: '🎙', title: 'Activer le micro',        class: '' },
        listening:  { text: '👂', title: 'Bob écoute...',           class: 'listening' },
        speaking:   { text: '🔴', title: 'Je t\'entends...',        class: 'speaking' },
        silence:    { text: '⏳', title: 'Envoi dans 1.5s...',      class: 'silence' },
        processing: { text: '💭', title: 'Bob réfléchit...',        class: 'processing' },
    };
    const s = states[state] || states.off;
    btn.textContent = s.text;
    btn.title = s.title;
    btn.className = s.class;
}
```

### CSS états bouton micro

Ajouter dans le `<style>` de chat.blade.php :

```css
#btn-mic { transition: all 0.2s; cursor: pointer; font-size: 1.2rem; padding: 0.4rem 0.7rem; border-radius: 6px; }
#btn-mic.listening  { background: #1a3a1a; animation: pulse 2s infinite; }
#btn-mic.speaking   { background: #3a1a1a; animation: pulse 0.5s infinite; }
#btn-mic.silence    { background: #3a3a1a; }
#btn-mic.processing { background: #1a1a3a; animation: pulse 1s infinite; }

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.5; }
}
```

## Tests à effectuer après modification

1. Clic micro → icône 👂 (Bob écoute)
2. Parler → icône 🔴 (Bob t'entend, RMS > seuil)
3. S'arrêter → icône ⏳ pendant 1.5s → envoi auto
4. Bob répond en audio → icône 💭 pendant le traitement
5. Fin de l'audio Bob → retour automatique à 👂 (écoute relancée)
6. Clic micro pendant n'importe quel état → arrêt propre

## Ajustements possibles si VAD trop/pas assez sensible

Dans le JS, modifier :
- `VAD_SILENCE_THRESHOLD` : augmenter si trop de bruit de fond déclenche des envois (défaut 15)
- `VAD_SILENCE_DURATION` : augmenter si Bob coupe avant que tu finisses ta phrase (défaut 1500ms)

## MISE À JOUR CLAUDE.md

Après implémentation, ajouter dans Historique :
```
2026-05-04 — Remplacement push-to-talk par VAD auto-stop (Web Audio API, pas de lib externe).
             1 clic active le mode vocal continu. Silence 1.5s → envoi auto.
             Reprise écoute automatique après lecture réponse Bob.
             Paramètres ajustables : VAD_SILENCE_THRESHOLD, VAD_SILENCE_DURATION.
```
