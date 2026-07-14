import re

with open('templates/ia.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract styles
style_match = re.search(r'<style>(.*?)</style>', content, re.DOTALL)
styles = style_match.group(1) if style_match else ''

# Construct the new HTML
new_html = """<!DOCTYPE html>
<html lang="es">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chat de IA - STARCONTRACT</title>
    <link rel="shortcut icon" href="/static/favicon.ico">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/marked/4.3.0/marked.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10.6.1/dist/mermaid.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/localforage/1.10.0/localforage.min.js"></script>
    <script src="/static/js/tts-controller.js"></script>
    <!-- Alpine.js -->
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css">
    <script>
        tailwind.config = { theme: { extend: { fontFamily: { sans: ['Inter', 'sans-serif'] } } } };
        mermaid.initialize({ startOnLoad: false, theme: 'dark' });
    </script>
    <style>""" + styles + """</style>
</head>

<body class="bg-gray-50" x-data="chatApp()">

    <div class="chat-container bg-white rounded-2xl shadow-xl overflow-hidden h-screen">
        <div class="chat-header p-4 flex items-center justify-between rounded-t-2xl">
            <h1 class="text-xl font-bold flex items-center">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 4v-4z" />
                </svg>Asistente STARCONTRACT
            </h1>
            <div class="flex items-center space-x-4">
                <button @click="exportChat" title="Exportar conversación" class="text-gray-400 hover:text-white transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                </button>
                <button @click="clearChat" title="Limpiar conversación" class="text-gray-400 hover:text-white transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                </button>
                <button @click="toggleTTSGlobalPause" :class="{'hidden': !isTTSPlaying}" class="flex items-center justify-center text-gray-400 hover:text-indigo-400 focus:outline-none transition-colors" title="Pausar/Reanudar (Alt+P)">
                    <svg x-show="!ttsPaused" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <svg x-show="ttsPaused" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 hidden" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                        <path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                </button>
                <div @click="toggleTTSAuto" class="tts-auto-toggle" :class="{'active': ttsAutoRead}" title="Auto-lectura de respuestas">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M15.536 8.464a5 5 0 010 7.072M18.364 5.636a9 9 0 010 12.728M11 5L6 9H2v6h4l5 4V5z"/>
                    </svg>
                    <span>Voz</span>
                    <div class="toggle-dot"></div>
                </div>
            </div>
        </div>

        <div id="messages" x-ref="messagesContainer" class="messages-container flex-1 p-6 overflow-y-auto flex flex-col space-y-4">
            <template x-for="msg in chatHistory" :key="msg.id">
                <div class="chat-bubble p-4 rounded-2xl shadow-sm text-sm relative group animate-fade-in-up"
                     :class="msg.role === 'user' ? 'bg-indigo-600 text-white self-end ml-12 rounded-br-none' : 'bg-gray-100 border border-gray-200 text-gray-800 self-start mr-12 shadow-sm rounded-bl-none'">
                    
                    <!-- Streaming Status Indicator -->
                    <template x-if="msg.role === 'model' && msg.isStreaming && msg.statusText">
                        <div class="text-xs text-indigo-500 font-medium mb-1 flex items-center gap-2">
                            <div class="w-2 h-2 rounded-full thinking-pulse bg-indigo-500"></div>
                            <span x-text="msg.statusText"></span>
                        </div>
                    </template>

                    <!-- Message Content -->
                    <div class="message-content prose max-w-none prose-p:leading-relaxed"
                         :class="msg.role === 'user' ? 'prose-invert' : ''"
                         x-html="msg.html"
                         x-init="$watch('msg.isStreaming', val => { if(!val && msg.role === 'model') processPostRender($el, msg) })">
                    </div>

                    <!-- Timestamp -->
                    <template x-if="msg.timestamp">
                        <div class="text-[10px] text-gray-500 mt-2"
                             :class="msg.role === 'user' ? 'text-right' : 'text-left'"
                             x-text="msg.timestamp"></div>
                    </template>

                    <!-- Botones interactivos (solo bot finalizado) -->
                    <template x-if="msg.role === 'model' && !msg.isStreaming">
                        <div>
                            <!-- Copiar -->
                            <button @click="copyToClipboard(msg.text)" class="absolute top-2 right-2 p-1 rounded-full bg-white/10 hover:bg-black/5 opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-indigo-500" title="Copiar">
                                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                            </button>
                            <!-- Crear plantilla -->
                            <button @click="createTemplateFromMsg(msg.text)" class="absolute top-2 right-10 p-1 rounded-full bg-white/10 hover:bg-black/5 opacity-0 group-hover:opacity-100 transition-opacity text-indigo-400 hover:text-indigo-600" title="Crear plantilla">
                                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                            </button>
                            <!-- TTS -->
                            <button @click="speakMsg(msg.text)" class="absolute top-2 right-[4.5rem] p-1 rounded-full bg-white/10 hover:bg-black/5 opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-indigo-500" title="Leer en voz alta">
                                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.536 8.464a5 5 0 010 7.072M18.364 5.636a9 9 0 010 12.728M11 5L6 9H2v6h4l5 4V5z"/></svg>
                            </button>
                        </div>
                    </template>
                </div>
            </template>
        </div>

        <form @submit.prevent="submitForm" class="p-4 border-t border-gray-200 relative">
            
            <!-- Botones de Acción Rápida -->
            <div class="flex overflow-x-auto gap-2 px-2 pb-2 mb-1 scrollbar-hide">
                <template x-for="action in quickActions" :key="action.label">
                    <button type="button" @click="handleQuickAction(action.prompt)"
                        class="quick-action-btn whitespace-nowrap px-3 py-1 bg-gray-100 hover:bg-indigo-100 text-gray-700 hover:text-indigo-700 text-xs rounded-full border border-gray-200 transition-colors flex items-center gap-1">
                        <span x-html="action.icon"></span>
                        <span x-text="action.label"></span>
                    </button>
                </template>
            </div>

            <!-- Chips de Archivos y Skills -->
            <div class="flex flex-wrap gap-2 px-2 pb-2" x-show="currentAttachment || activeSkill">
                <!-- Archivo -->
                <template x-if="currentAttachment">
                    <div class="inline-flex items-center bg-indigo-100 text-indigo-800 text-xs px-2 py-1 rounded-full border border-indigo-200">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                        <span class="max-w-[150px] truncate" :title="currentAttachment.name" x-text="currentAttachment.name"></span>
                        <button type="button" @click="currentAttachment = null" class="ml-1 text-indigo-500 hover:text-indigo-700 focus:outline-none">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                    </div>
                </template>

                <!-- Skill -->
                <template x-if="activeSkill">
                    <div class="inline-flex items-center bg-gradient-to-r from-green-50 to-emerald-50 text-emerald-800 text-sm font-medium px-3 py-1.5 rounded-full border border-emerald-200 shadow-sm animate-fade-in-up">
                        <span class="mr-2 animate-pulse text-emerald-500">🟢</span>
                        <span class="font-bold mr-1" x-text="activeSkill.cmd"></span>
                        <span class="max-w-[250px] truncate opacity-75" :title="activeSkill.desc" x-text="'- ' + activeSkill.desc"></span>
                        <button type="button" @click="removeSkill" class="ml-2 bg-emerald-200 hover:bg-emerald-300 text-emerald-700 rounded-full p-0.5 focus:outline-none transition-colors">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                    </div>
                </template>
            </div>

            <!-- Slash Menu -->
            <div id="slash-menu" x-show="slashMenu.visible" @click.away="slashMenu.visible = false" style="display: none;" class="absolute bottom-full left-0 w-80 max-h-64 overflow-y-auto bg-white/70 backdrop-blur-md border border-white/40 rounded-2xl shadow-xl z-50 mb-2">
                <template x-if="filteredSlashCommands.length === 0">
                    <div class="p-4 text-center text-gray-500 text-sm">No hay comandos.</div>
                </template>
                <template x-for="(cmd, index) in filteredSlashCommands" :key="cmd.id">
                    <div class="slash-item p-3 cursor-pointer flex items-center gap-3 transition-all hover:bg-white/90 border-b border-black/5"
                         :class="{'bg-white/95 translate-x-1': index === slashMenu.activeIndex}"
                         @click="executeSlashCommand(cmd)">
                        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" x-html="cmd.icon"></svg>
                        <span class="font-semibold text-gray-800" x-text="cmd.cmd"></span>
                        <span class="text-xs text-gray-500 ml-auto" x-text="cmd.short_description || cmd.desc"></span>
                    </div>
                </template>
            </div>

            <!-- Sugerencias Inteligentes -->
            <div x-show="lastSuggestions.length > 0" class="flex flex-wrap gap-2 px-2 pb-4 pt-2 animate-fade-in-up">
                <div class="flex items-center gap-2 w-full mb-1">
                    <div class="h-px bg-gray-200 flex-1"></div>
                    <span class="text-[10px] uppercase tracking-wider text-gray-400 font-bold whitespace-nowrap">Sugerencias recomendadas</span>
                    <button type="button" @click="lastSuggestions = []" class="text-gray-400 hover:text-gray-600 transition-colors" title="Cerrar sugerencias">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                    <div class="h-px bg-gray-200 flex-1"></div>
                </div>
                <template x-for="suggestion in lastSuggestions" :key="suggestion">
                    <button type="button" @click="selectSuggestion(suggestion)"
                        class="suggestion-chip px-3 py-2 bg-gradient-to-r from-indigo-50 to-blue-50 hover:from-indigo-600 hover:to-blue-600 text-indigo-800 hover:text-white text-xs font-medium rounded-xl border border-indigo-100 shadow-sm hover:shadow-md transition-all duration-300 active:scale-95 flex items-center gap-2 group">
                        <div class="p-0.5 rounded-full bg-indigo-200 group-hover:bg-white/20 transition-colors">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3 text-indigo-600 group-hover:text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                        </div>
                        <span x-text="suggestion"></span>
                    </button>
                </template>
            </div>

            <div class="input-wrapper relative">
                <input type="file" x-ref="fileInput" @change="handleFileUpload" class="hidden" accept=".pdf,.txt,.md,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document">

                <button type="button" @click="$refs.fileInput.click()" title="Adjuntar documento" class="absolute left-3 bottom-3 text-gray-500 hover:text-indigo-600 z-10 transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>
                </button>

                <button type="button" @click="openTemplateModal" title="Cargar plantilla" class="absolute left-12 bottom-3 text-gray-500 hover:text-indigo-600 z-10">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                </button>

                <textarea x-model="userInput" x-ref="textarea" @input="handleInput" @keydown="handleKeydown"
                    :placeholder="activeSkill ? `Hablando con ${activeSkill.cmd}...` : 'Escribe tu pregunta legal...'"
                    class="chat-input-textarea flex-1 w-full pl-20 pr-28 rounded-xl border border-gray-300 focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition duration-200"
                    rows="1" required></textarea>

                <button type="button" @click="toggleMic" title="Dictar por voz" class="absolute right-16 bottom-3 z-10 transition-colors" :class="isRecording ? 'text-red-500' : 'text-gray-500 hover:text-indigo-600'">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                </button>
                <button type="submit" class="absolute right-3 bottom-2 bg-indigo-600 text-white p-2 rounded-lg hover:bg-indigo-700 transition duration-200 shadow-md active:scale-95 z-10">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
                </button>
            </div>

            <div x-show="status.message" x-text="status.message" class="text-xs mt-2 transition-all font-medium" :style="`color: ${status.color}`"></div>
        </form>
    </div>

    <!-- Template Modal -->
    <div x-show="isTemplateModalOpen" class="modal-backdrop" style="display: none;">
        <div class="modal-content bg-white p-6 rounded-xl shadow-2xl w-90 max-w-md" @click.away="isTemplateModalOpen = false">
            <h2 class="text-xl font-bold mb-4 text-gray-800">Cargar Plantilla</h2>
            <ul class="space-y-2 max-h-60 overflow-y-auto custom-scrollbar">
                <template x-for="tpl in templates" :key="tpl">
                    <li>
                        <button type="button" @click="loadTemplateContent(tpl)" class="w-full text-left p-3 rounded-lg hover:bg-indigo-50 transition-colors text-sm font-medium text-gray-700 border border-gray-100 hover:border-indigo-200" x-text="tpl"></button>
                    </li>
                </template>
            </ul>
            <button type="button" @click="isTemplateModalOpen = false" class="mt-4 w-full p-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 font-semibold transition-colors">Cerrar</button>
        </div>
    </div>

    <!-- MAIN ALPINE COMPONENT -->
    <script src="/static/js/app-ia.js"></script>
</body>
</html>
"""
with open('templates/ia.html', 'w', encoding='utf-8') as f:
    f.write(new_html)

print("[OK] templates/ia.html updated with Alpine.js layout")
