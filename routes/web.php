<?php

use Illuminate\Support\Facades\Route;
use App\Http\Controllers\ChatController;

Route::get('/', [ChatController::class, 'index']);
Route::post('/chat', [ChatController::class, 'send']);
Route::post('/chat/reset', [ChatController::class, 'reset']);
Route::post('/chat-voice', [ChatController::class, 'sendVoice']);
