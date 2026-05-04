"""
Test isolé de faster-whisper avec le modèle 'small' en français.
Utilisation : python test_whisper.py chemin/vers/audio.wav
"""

import sys
import time
from pathlib import Path
from faster_whisper import WhisperModel


def main():
    if len(sys.argv) < 2:
        print("Usage : python test_whisper.py <fichier_audio>")
        print("Formats supportés : wav, mp3, m4a, ogg, flac, webm")
        sys.exit(1)

    audio_path = Path(sys.argv[1])
    if not audio_path.exists():
        print(f"Fichier introuvable : {audio_path}")
        sys.exit(1)

    print(f"📂 Fichier : {audio_path.name} ({audio_path.stat().st_size / 1024:.1f} KB)")

    # Chargement du modèle (téléchargé automatiquement au 1er lancement)
    print("⏳ Chargement du modèle Whisper small...")
    t0 = time.time()
    model = WhisperModel(
        "small",
        device="cpu",
        compute_type="int8",  # int8 = ~2x plus rapide qu'float32 sur CPU, qualité quasi identique
    )
    print(f"✅ Modèle chargé en {time.time() - t0:.1f}s")

    # Transcription
    print("\n⏳ Transcription en cours...")
    t0 = time.time()
    segments, info = model.transcribe(
        str(audio_path),
        language="fr",
        beam_size=5,
        vad_filter=True,  # supprime les silences automatiquement (gain de vitesse)
        vad_parameters={"min_silence_duration_ms": 500},
    )

    # segments est un générateur — il faut l'itérer pour déclencher la transcription
    full_text = ""
    for segment in segments:
        full_text += segment.text
        print(f"  [{segment.start:.1f}s → {segment.end:.1f}s] {segment.text.strip()}")

    elapsed = time.time() - t0

    print(f"\n📝 Transcription complète :")
    print(f"   {full_text.strip()}")
    print(f"\n⏱️  Temps : {elapsed:.2f}s")
    print(f"🎙️  Langue détectée : {info.language} (proba {info.language_probability:.2f})")
    print(f"⏰ Durée audio : {info.duration:.2f}s")
    print(f"⚡ Vitesse : {info.duration / elapsed:.2f}x temps réel")


if __name__ == "__main__":
    main()