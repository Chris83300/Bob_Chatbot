<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;

class ChatController extends Controller
{
    private string $fastapiUrl = 'http://localhost:8000';

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
                ->post("{$this->fastapiUrl}/chat", $payload);
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
        $sessionId = $request->json('session_id');

        if ($sessionId) {
            try {
                Http::timeout(10)->post("{$this->fastapiUrl}/chat/reset", [], [
                    'query' => ['session_id' => $sessionId],
                ]);
            } catch (\Exception $e) {
                // On ignore l'erreur, on reset côté client de toute façon
            }
        }

        return response()->json([
    'response' => 'Conversation réinitialisée',
    'session_id' => null,
]);
    }
}
