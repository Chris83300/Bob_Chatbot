# PROMPT CLAUDE CODE — BUGFIX BOB BRAIN

Projet : `C:\laragon\www\chat-ia-local`
Lis le `CLAUDE.md` en premier pour le contexte complet.

---

## BUG 1 — System prompt dupliqué (`main.py`)

**Problème :** `.env` FastAPI contient déjà le system prompt complet avec les exemples 1-11 +
`FIN DES EXEMPLES`. `main.py` concatène ensuite `STYLE_EXAMPLES` (exemples 1-10 + `FIN DES EXEMPLES`)
→ doublon dans le contexte envoyé à Ollama.

**Fix :** Supprimer la variable `STYLE_EXAMPLES` et toute concaténation avec le system prompt dans
`main.py`. Le system prompt final envoyé à Ollama doit être uniquement `os.getenv("SYSTEM_PROMPT")`,
sans rien ajouter après.

**Vérification :** Logger (ou print) les 50 premiers et 50 derniers caractères du system prompt
effectivement envoyé à Ollama pour confirmer qu'il n'y a plus de doublon.

---

## BUG 2 — Variables LLM `.env` non lues (`main.py`)

**Problème :** `LLM_TEMPERATURE`, `LLM_REPEAT_PENALTY`, `LLM_REPEAT_LAST_N`, `LLM_TOP_P`,
`LLM_TOP_K`, `LLM_NUM_CTX`, `LLM_PRESENCE_PENALTY`, `LLM_FREQUENCY_PENALTY` sont définies
dans `.env` FastAPI mais ignorées. `OLLAMA_OPTIONS` est hardcodé dans `main.py`.

**Fix :** Lire ces variables depuis `.env` avec fallback sur les valeurs actuelles hardcodées :

```python
OLLAMA_OPTIONS = {
    "temperature":        float(os.getenv("LLM_TEMPERATURE", "0.85")),
    "repeat_penalty":     float(os.getenv("LLM_REPEAT_PENALTY", "1.4")),
    "repeat_last_n":      int(os.getenv("LLM_REPEAT_LAST_N", "1024")),
    "top_p":              float(os.getenv("LLM_TOP_P", "0.9")),
    "top_k":              int(os.getenv("LLM_TOP_K", "40")),
    "num_ctx":            int(os.getenv("LLM_NUM_CTX", "8192")),
    "presence_penalty":   float(os.getenv("LLM_PRESENCE_PENALTY", "0.3")),
    "frequency_penalty":  float(os.getenv("LLM_FREQUENCY_PENALTY", "0.5")),
}
```

**Important :** Ce dict doit être construit APRÈS `load_dotenv()`, pas avant.

---

## BUG 3 — Reset Laravel ne transmet pas le session_id (`ChatController.php`)

**Problème :** La méthode `reset()` utilise un 3e argument inexistant de `Http::post()` pour
passer le session_id → FastAPI reçoit un reset sans savoir quelle session réinitialiser.

**Fix :** Passer le session_id en query string :

```php
public function reset(Request $request)
{
    $sessionId = $request->input('session_id', '');
    $url = env('FASTAPI_URL', 'http://localhost:8000') . '/chat/reset';

    $response = Http::timeout(10)->post($url . '?session_id=' . urlencode($sessionId));

    if ($response->failed()) {
        return response()->json(['error' => 'Reset failed'], 503);
    }

    return response()->json($response->json());
}
```

**Aussi :** Remplacer le `fastapiUrl` hardcodé dans tout `ChatController.php` par
`env('FASTAPI_URL', 'http://localhost:8000')` — dans `send()`, `reset()`, et `sendVoice()`.

**Et dans `.env` Laravel**, ajouter si absent :
```
FASTAPI_URL=http://localhost:8000
```

---

## APRÈS LES 3 FIXES

1. Relancer FastAPI : `uvicorn main:app --reload`
2. Tester `/health` → confirme que le serveur démarre sans erreur
3. Envoyer un message texte → vérifier que la réponse Bob est cohérente (pas de doublon visible)
4. Tester reset → envoyer un message, reset, renvoyer le même message → Bob ne doit plus
   se souvenir du contexte précédent

---

## MISE À JOUR CLAUDE.md

Après les fixes, mettre à jour :
- Déplacer les 3 bugs de la section `⚠️ En cours` vers `✅ Fonctionne`
- Ajouter une ligne dans `Historique des sessions` :
```
2026-05-04 — Fix bugs : system prompt dupliqué supprimé, OLLAMA_OPTIONS lit .env,
             reset Laravel corrigé (query param), fastapiUrl externalisé dans .env.
```
