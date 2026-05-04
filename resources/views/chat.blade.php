<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chat IA</title>
    <style>
        body {
            background: #0a0a0a;
            color: #e8e4dc;
            font-family: 'Instrument Sans', ui-sans-serif, system-ui, sans-serif;
            height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            margin: 0;
        }
        h1 {
            letter-spacing: 0.5rem;
            margin: 0 0 1rem 0;
        }
        #chat-box {
            width: 600px;
            height: 500px;
            background: #111;
            border-radius: 10px;
            border: 1px solid #333;
            padding: 1rem;
            overflow-y: auto;
            margin-bottom: 1rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }
        .message {
            padding: 0.6rem 1rem;
            border-radius: 8px;
            max-width: 80%;
            font-size: 1rem;
            line-height: 1.4;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .user {
            background: #1a1a2e;
            border: 1px solid #333;
            align-self: flex-end;
        }
        .bot {
            background: #5e5e5e27;
            border: 1px solid #585858;
            align-self: flex-start;
            color: #fff;
        }
        .bot.thinking {
            opacity: 0.6;
            font-style: italic;
        }
        .bot.error {
            border-color: #7a2929;
            background: #2a0f0f;
        }
        #input-area {
            display: flex;
            width: 600px;
            gap: 0.5rem;
            margin-bottom: 0.5rem;
        }
        #message-input {
            flex: 1;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            border: 1px solid #333;
            background: #111;
            color: #e8e4dc;
            outline: none;
        }
        #message-input:focus {
            border-color: #6e6e6e;
        }
        #message-input:disabled {
            opacity: 0.5;
        }
        button {
            padding: 0.75rem 1rem;
            border-radius: 8px;
            border: 1px solid #333;
            background: #111;
            color: #e8e4dc;
            cursor: pointer;
        }
        button:hover:not(:disabled) {
            background: #666;
        }
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        #controls {
            width: 600px;
            display: flex;
            justify-content: space-between;
            font-size: 0.8rem;
            color: #666;
        }
        #reset-btn {
            background: none;
            border: none;
            color: #888;
            text-decoration: underline;
            cursor: pointer;
            padding: 0;
            font-size: 0.8rem;
        }
        #reset-btn:hover {
            color: #fff;
        }
        #btn-mic {
            transition: all 0.2s;
            cursor: pointer;
            font-size: 1.2rem;
            padding: 0.4rem 0.7rem;
            border-radius: 6px;
            border: 1px solid #333;
            background: #111;
            color: #e8e4dc;
        }
        #btn-mic:hover:not(:disabled) { background: #666; }
        #btn-mic.listening  { background: #1a3a1a; animation: pulse 2s infinite; }
        #btn-mic.speaking   { background: #3a1a1a; animation: pulse 0.5s infinite; }
        #btn-mic.silence    { background: #3a3a1a; }
        #btn-mic.processing { background: #1a1a3a; animation: pulse 1s infinite; }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50%       { opacity: 0.5; }
        }
    </style>
</head>
<body>
    <h1>B O B</h1>
    <div id="chat-box"></div>
    <div id="input-area">
        <input type="text" id="message-input" placeholder="Tapez votre message..." autocomplete="off">
        <button id="send-btn" onclick="sendMessage()">Envoyer</button>
        <button id="btn-mic" title="Parler à Bob">🎙</button>
    </div>
    <div id="controls">
        <span id="session-info">Pas de session active</span>
        <button id="reset-btn" onclick="resetConversation()">Réinitialiser la conversation</button>
    </div>

    <script>
        const csrf = '{{ csrf_token() }}';
        const STORAGE_KEY = 'bob_session_id';

        // Récupère la session existante du localStorage si présente
        let sessionId = localStorage.getItem(STORAGE_KEY) || null;
        updateSessionInfo();

        const input = document.getElementById('message-input');
        const sendBtn = document.getElementById('send-btn');
        const chatBox = document.getElementById('chat-box');

        function updateSessionInfo() {
            const info = document.getElementById('session-info');
            info.textContent = sessionId
                ? `Session : ${sessionId.slice(0, 8)}…`
                : 'Pas de session active';
        }

        function appendMessage(text, cls) {
            const div = document.createElement('div');
            div.className = `message ${cls}`;
            div.textContent = text;
            chatBox.appendChild(div);
            chatBox.scrollTop = chatBox.scrollHeight;
            return div;
        }

        async function sendMessage() {
            const message = input.value.trim();
            if (!message) return;

            appendMessage(message, 'user');
            input.value = '';
            input.disabled = true;
            sendBtn.disabled = true;

            const thinkingMsg = appendMessage('Bob réfléchit…', 'bot thinking');

            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': csrf,
                        'Accept': 'application/json',
                    },
                    body: JSON.stringify({
                        message: message,
                        session_id: sessionId,
                    }),
                });

                const data = await response.json();
                thinkingMsg.remove();

                if (!response.ok) {
                    appendMessage(`Erreur : ${data.error || 'inconnue'}`, 'bot error');
                    return;
                }

                // Sauvegarde le session_id pour les requêtes suivantes
                if (data.session_id) {
                    sessionId = data.session_id;
                    localStorage.setItem(STORAGE_KEY, sessionId);
                    updateSessionInfo();
                }

                appendMessage(data.response, 'bot');
            } catch (err) {
                thinkingMsg.remove();
                appendMessage(`Erreur réseau : ${err.message}`, 'bot error');
            } finally {
                input.disabled = false;
                sendBtn.disabled = false;
                input.focus();
            }
        }

        async function resetConversation() {
            if (!confirm('Effacer la conversation ?')) return;

            if (sessionId) {
                try {
                    await fetch('/chat/reset', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRF-TOKEN': csrf,
                        },
                        body: JSON.stringify({ session_id: sessionId }),
                    });
                } catch (err) {
                    // On ignore, on reset côté client de toute façon
                }
            }

            sessionId = null;
            localStorage.removeItem(STORAGE_KEY);
            chatBox.innerHTML = '';
            updateSessionInfo();
            input.focus();
        }

        input.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !input.disabled) {
                sendMessage();
            }
        });

        // --- Voice / VAD auto-stop ---
        const VAD_SILENCE_THRESHOLD  = 15;    // RMS en dessous = silence
        const VAD_SILENCE_DURATION   = 1500;  // ms de silence avant envoi auto
        const VAD_MIN_SPEECH_DURATION = 300;  // ms de parole min avant activation du silence-timer

        let audioContext, analyser, micStream, mediaRecorder;
        let audioChunks = [];
        let silenceTimer = null;
        let speechDetected = false;
        let speechStartTime = null;
        let isListening = false;
        let isProcessing = false;
        let voiceModeActive = false;

        const micBtn = document.getElementById('btn-mic');

        function updateMicButton(state) {
            const states = {
                off:        { text: '🎙', title: 'Activer le micro',   cls: '' },
                listening:  { text: '👂', title: 'Bob écoute...',      cls: 'listening' },
                speaking:   { text: '🔴', title: "Je t'entends...",    cls: 'speaking' },
                silence:    { text: '⏳', title: 'Envoi dans 1.5s...', cls: 'silence' },
                processing: { text: '💭', title: 'Bob réfléchit...',   cls: 'processing' },
            };
            const s = states[state] || states.off;
            micBtn.textContent = s.text;
            micBtn.title = s.title;
            micBtn.className = s.cls;
        }

        async function startListening() {
            if (isProcessing) return;

            try {
                micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            } catch (err) {
                appendMessage("Impossible d'accéder au micro : " + err.message, 'bot error');
                voiceModeActive = false;
                updateMicButton('off');
                return;
            }

            audioContext = new AudioContext();
            analyser = audioContext.createAnalyser();
            analyser.fftSize = 512;
            audioContext.createMediaStreamSource(micStream).connect(analyser);

            const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                ? 'audio/webm;codecs=opus' : 'audio/webm';
            mediaRecorder = new MediaRecorder(micStream, { mimeType });
            audioChunks = [];
            speechDetected = false;
            speechStartTime = null;

            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) audioChunks.push(e.data);
            };

            mediaRecorder.onstop = async () => {
                micStream.getTracks().forEach(t => t.stop());
                audioContext.close();
                if (speechDetected && audioChunks.length > 0) {
                    await sendVoiceMessage(new Blob(audioChunks, { type: 'audio/webm' }));
                } else if (voiceModeActive) {
                    startListening();
                }
            };

            mediaRecorder.start(100);
            isListening = true;
            updateMicButton('listening');
            detectSilence();
        }

        function detectSilence() {
            if (!isListening) return;

            const buffer = new Uint8Array(analyser.frequencyBinCount);
            analyser.getByteFrequencyData(buffer);
            const rms = Math.sqrt(buffer.reduce((sum, v) => sum + v * v, 0) / buffer.length);

            if (rms > VAD_SILENCE_THRESHOLD) {
                if (!speechDetected) {
                    speechDetected = true;
                    speechStartTime = Date.now();
                }
                clearTimeout(silenceTimer);
                silenceTimer = null;
                updateMicButton('speaking');
            } else if (speechDetected) {
                const speechDuration = Date.now() - (speechStartTime || 0);
                if (speechDuration >= VAD_MIN_SPEECH_DURATION && !silenceTimer) {
                    silenceTimer = setTimeout(stopListening, VAD_SILENCE_DURATION);
                    updateMicButton('silence');
                }
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

        function showThinkingBubble() {
            const id = 'thinking-' + Date.now();
            const div = document.createElement('div');
            div.id = id;
            div.className = 'message bot thinking';
            div.textContent = '...';
            chatBox.appendChild(div);
            chatBox.scrollTop = chatBox.scrollHeight;
            return id;
        }

        function removeThinkingBubble(id) {
            const el = document.getElementById(id);
            if (el) el.remove();
        }

        async function sendVoiceMessage(audioBlob) {
            isProcessing = true;
            updateMicButton('processing');
            input.disabled = true;
            sendBtn.disabled = true;

            const thinkingId = showThinkingBubble();

            const formData = new FormData();
            formData.append('audio', audioBlob, 'voice.webm');
            formData.append('session_id', sessionId || '');

            try {
                const response = await fetch('/chat-voice', {
                    method: 'POST',
                    headers: { 'X-CSRF-TOKEN': csrf },
                    body: formData,
                });

                removeThinkingBubble(thinkingId);
                const data = await response.json();

                if (!response.ok) {
                    appendMessage('Erreur : ' + (data.error || 'inconnue'), 'bot error');
                    return;
                }

                if (data.transcription) appendMessage(data.transcription, 'user');
                appendMessage(data.response, 'bot');

                if (data.session_id) {
                    sessionId = data.session_id;
                    localStorage.setItem(STORAGE_KEY, sessionId);
                    updateSessionInfo();
                }

                if (data.audio_base64) {
                    const audio = new Audio('data:audio/mp3;base64,' + data.audio_base64);
                    audio.onended = () => {
                        isProcessing = false;
                        if (voiceModeActive) startListening();
                    };
                    audio.onerror = () => {
                        isProcessing = false;
                        if (voiceModeActive) startListening();
                    };
                    audio.play().catch(() => {
                        isProcessing = false;
                        if (voiceModeActive) startListening();
                    });
                } else {
                    isProcessing = false;
                    if (voiceModeActive) startListening();
                }
            } catch (err) {
                removeThinkingBubble(thinkingId);
                appendMessage('Erreur réseau : ' + err.message, 'bot error');
                isProcessing = false;
                if (voiceModeActive) startListening();
            } finally {
                input.disabled = false;
                sendBtn.disabled = false;
                input.focus();
            }
        }

        micBtn.addEventListener('click', () => {
            if (!voiceModeActive) {
                voiceModeActive = true;
                startListening();
            } else {
                voiceModeActive = false;
                isProcessing = false;
                stopListening();
                updateMicButton('off');
            }
        });

        input.focus();
    </script>
</body>
</html>
