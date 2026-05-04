<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;

class ChatController extends Controller
{
    private function fastapiUrl(): string
    {
        return env('FASTAPI_URL', 'http://localhost:8000');
    }

    public function index()
    {
        return view('chat');
    }

    public function send(Request $request)
    {
        $validated = $request->validate([
            'message' => 'required|string|min:1|max:2000',
            'session_id' => 'nullable|string|uuid',
        ]);

        $payload = ['content' => $validated['message']];
        if (!empty($validated['session_id'])) {
            $payload['session_id'] = $validated['session_id'];
        }

        try {
            $response = Http::timeout(120)
                ->post($this->fastapiUrl() . '/chat', $payload);
        } catch (\Exception $e) {
            return response()->json([
                'error' => 'Service IA injoignable',
                'detail' => $e->getMessage(),
            ], 503);
        }

        if (!$response->successful()) {
            return response()->json([
                'error' => 'Erreur du service IA',
                'detail' => $response->body(),
            ], $response->status());
        }

        $data = $response->json();

        return response()->json([
            'response' => $data['response'] ?? '(réponse vide)',
            'session_id' => $data['session_id'] ?? null,
        ]);
    }

    public function reset(Request $request)
    {
        $sessionId = $request->input('session_id', '');
        $url = $this->fastapiUrl() . '/chat/reset';

        try {
            $response = Http::timeout(10)->post($url . '?session_id=' . urlencode($sessionId));
        } catch (\Exception $e) {
            return response()->json(['error' => 'Reset failed', 'detail' => $e->getMessage()], 503);
        }

        if ($response->failed()) {
            return response()->json(['error' => 'Reset failed'], 503);
        }

        return response()->json($response->json());
    }

    public function sendVoice(Request $request)
    {
        $request->validate([
            'audio' => 'required|file',
            'session_id' => 'nullable|string',
        ]);

        try {
            $response = Http::timeout(120)
                ->attach('audio', file_get_contents($request->file('audio')->path()), 'voice.webm')
                ->post($this->fastapiUrl() . '/chat-voice', [
                    'session_id' => $request->input('session_id', ''),
                ]);
        } catch (\Exception $e) {
            return response()->json(['error' => 'Bob est indisponible', 'detail' => $e->getMessage()], 503);
        }

        if ($response->failed()) {
            return response()->json(['error' => 'Erreur du service IA', 'detail' => $response->body()], $response->status());
        }

        return response()->json($response->json());
    }
}
