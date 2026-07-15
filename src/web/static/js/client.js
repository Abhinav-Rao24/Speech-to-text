// client.js - Real-time client audio streaming and Web Audio playback for Logistics Voice Portal

let audioContext = null;
let mediaStream = null;
let scriptProcessor = null;
let socket = null;
let playbackContext = null;
let analyser = null;
let animationFrameId = null;
let isRecording = false;
let isMuted = false;
let visualizerMode = 'idle'; // 'idle', 'listening', 'speaking'
let audioQueue = [];
let isPlayingAudio = false;

// Initialize Playback Context for Web Audio API defensively under user gesture
function getPlaybackContext() {
    try {
        if (!playbackContext) {
            playbackContext = new (window.AudioContext || window.webkitAudioContext)();
        }
        if (playbackContext.state === 'suspended') {
            playbackContext.resume().catch(err => console.warn("AudioContext resume failed:", err));
        }
    } catch (e) {
        console.error("Failed to initialize Web Audio playback context:", e);
    }
    return playbackContext;
}

// Force the browser to unlock Web Audio by playing a tiny silent buffer
function unlockAudioContext(ctx) {
    if (!ctx) return;
    try {
        const buffer = ctx.createBuffer(1, 1, 22050);
        const source = ctx.createBufferSource();
        source.buffer = buffer;
        source.connect(ctx.destination);
        source.start(0);
        console.log("[Audio] Silent buffer source scheduled to unlock browser autoplay context.");
    } catch (err) {
        console.warn("Failed to play silent context unlock buffer:", err);
    }
}

// Convert Float32 PCM buffer to 16-bit signed PCM ArrayBuffer
function float32ToInt16(buffer) {
    let l = buffer.length;
    const buf = new Int16Array(l);
    for (let i = 0; i < l; i++) {
        let s = Math.max(-1, Math.min(1, buffer[i]));
        buf[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return buf.buffer;
}

// Convert 16-bit signed PCM to Float32 array
function pcm16ToFloat32(arrayBuffer) {
    const int16Array = new Int16Array(arrayBuffer);
    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
        float32Array[i] = int16Array[i] / 32768.0;
    }
    return float32Array;
}

// Decodes standard file payloads (WAV/MP3) or raw binary 16-bit PCM arrays
function decodeAudioPayload(arrayBuffer, callback) {
    if (!arrayBuffer || arrayBuffer.byteLength < 4) {
        console.warn("[Audio] Payload too small to parse, skipping.");
        return;
    }
    
    const view = new DataView(arrayBuffer);
    let isFormatFile = false;
    try {
        const magic = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3));
        const isMp3 = magic === 'ID3\x03' || magic === 'ID3\x04' || 
                      (view.getUint16(0) === 0xFFFB) || (view.getUint16(0) === 0xFFF3);
        if (magic === 'RIFF' || isMp3) {
            isFormatFile = true;
        }
    } catch (e) {
        console.warn("Error checking file signature, treating as raw PCM:", e);
    }
    
    const ctx = getPlaybackContext();
    if (!ctx) return;
    
    if (isFormatFile) {
        ctx.decodeAudioData(arrayBuffer, (decodedBuffer) => {
            callback(decodedBuffer);
        }, (err) => {
            console.warn("decodeAudioData failed, trying raw PCM fallback:", err);
            const floatArray = pcm16ToFloat32(arrayBuffer);
            const buffer = ctx.createBuffer(1, floatArray.length, 16000);
            buffer.copyToChannel(floatArray, 0);
            callback(buffer);
        });
    } else {
        const floatArray = pcm16ToFloat32(arrayBuffer);
        const buffer = ctx.createBuffer(1, floatArray.length, 16000);
        buffer.copyToChannel(floatArray, 0);
        callback(buffer);
    }
}

// Plays returning chunks sequentially using the playback queue
function playSynthesizedAudio(arrayBuffer) {
    console.log("[Audio] Playing chunk of size:", arrayBuffer.byteLength);
    decodeAudioPayload(arrayBuffer, (audioBuffer) => {
        audioQueue.push(audioBuffer);
        if (!isPlayingAudio) {
            playNextInQueue();
        }
    });
}

// Schedules queue playback gaplessly using Web Audio source nodes
function playNextInQueue() {
    const ctx = getPlaybackContext();
    const statusText = document.getElementById('portal-status-text');
    const pttMicBtn = document.getElementById('ptt-mic-btn');
    
    if (!ctx || audioQueue.length === 0) {
        isPlayingAudio = false;
        visualizerMode = 'idle';
        triggerVisualizer();
        
        if (statusText) statusText.textContent = isMuted ? 'Status: Muted' : 'Status: Ready';
        if (pttMicBtn) {
            pttMicBtn.disabled = false;
            pttMicBtn.classList.remove('opacity-50', 'pointer-events-none');
        }
        analyser = null;
        return;
    }
    
    isPlayingAudio = true;
    const buffer = audioQueue.shift();
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    
    analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    analyser.connect(ctx.destination);
    
    visualizerMode = 'speaking';
    if (statusText) statusText.textContent = 'Status: Speaking...';
    
    triggerVisualizer();
    
    source.onended = () => {
        playNextInQueue();
    };
    source.start(0);
}

// Appends message bubbles dynamically to timeline without page reload
function appendMessageBubble(sender, text) {
    const messagesPanel = document.getElementById('messages-panel');
    if (!messagesPanel) return;

    const row = document.createElement('div');
    row.className = `flex w-full ${sender === 'user' ? 'justify-end' : 'justify-start'}`;

    const bubble = document.createElement('div');
    bubble.className = `max-w-[70%] rounded-xl p-4 text-sm shadow-sm border ${
        sender === 'user' 
            ? 'bg-primary text-primary-foreground border-primary/20 rounded-br-none' 
            : 'bg-card text-card-foreground border-border rounded-bl-none'
    }`;

    const p = document.createElement('p');
    p.className = 'leading-relaxed';
    p.textContent = text;

    const meta = document.createElement('div');
    meta.className = `text-[10px] mt-2 opacity-65 flex items-center gap-1 ${sender === 'user' ? 'justify-end' : ''}`;
    
    const roleSpan = document.createElement('span');
    roleSpan.textContent = sender === 'user' ? 'You' : 'Assistant';
    
    meta.appendChild(roleSpan);
    bubble.appendChild(p);
    bubble.appendChild(meta);
    row.appendChild(bubble);
    messagesPanel.appendChild(row);

    // Scroll to bottom
    messagesPanel.scrollTop = messagesPanel.scrollHeight;
}

// Circular "thread wave" concentric visualizer loop
function updateVisualizer() {
    const canvas = document.getElementById('voiceWaveCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const rings = [25, 45, 65, 85]; // Adjusted for compact 200x200 canvas
    
    if (visualizerMode === 'speaking' && analyser) {
        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        analyser.getByteFrequencyData(dataArray);
        
        let sum = 0;
        for (let i = 0; i < bufferLength; i++) {
            sum += dataArray[i];
        }
        const average = sum / bufferLength;
        const scale = 1.0 + (average / 128.0);
        
        const time = Date.now() * 0.003;
        const colors = [
            'rgba(16, 185, 129, 0.45)', // emerald-500
            'rgba(52, 211, 153, 0.35)', // emerald-400
            'rgba(110, 231, 183, 0.3)',  // emerald-300
            'rgba(5, 150, 105, 0.3)'     // emerald-600
        ];
        
        rings.forEach((baseRadius, index) => {
            ctx.beginPath();
            ctx.strokeStyle = colors[index % colors.length];
            ctx.lineWidth = 2;
            
            const points = 90;
            const freq = 4 + index;
            const phase = time * (index % 2 === 0 ? 1.5 : -1.5);
            const amp = 3 + (index * 1.5) * scale;
            
            for (let i = 0; i <= points; i++) {
                const angle = (i / points) * Math.PI * 2;
                const r_offset = Math.sin(angle * freq + phase) * amp * scale;
                const r = baseRadius + r_offset;
                const x = centerX + r * Math.cos(angle + time * 0.05);
                const y = centerY + r * Math.sin(angle + time * 0.05);
                if (i === 0) {
                    ctx.moveTo(x, y);
                } else {
                    ctx.lineTo(x, y);
                }
            }
            ctx.closePath();
            ctx.stroke();
        });
        
        animationFrameId = requestAnimationFrame(updateVisualizer);
    } else {
        const borderStyle = getComputedStyle(document.documentElement).getPropertyValue('--border').trim() || '#e5e7eb';
        
        rings.forEach((baseRadius) => {
            ctx.beginPath();
            ctx.strokeStyle = borderStyle;
            ctx.lineWidth = 1.2;
            ctx.arc(centerX, centerY, baseRadius, 0, Math.PI * 2);
            ctx.stroke();
        });
        animationFrameId = null;
    }
}

// Trigger loop updates
function triggerVisualizer() {
    if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
        animationFrameId = null;
    }
    updateVisualizer();
}

// Connect to persistent websocket session
function startVoiceSession(sessionId) {
    const statusText = document.getElementById('portal-status-text');
    if (statusText) statusText.textContent = 'Status: Connecting...';
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/stream?session_id=${sessionId}`;
    socket = new WebSocket(wsUrl);
    socket.binaryType = 'arraybuffer';

    socket.onopen = () => {
        if (statusText) statusText.textContent = isMuted ? 'Status: Muted' : 'Status: Ready';
        triggerVisualizer();
    };

    socket.onmessage = (event) => {
        if (typeof event.data === 'string') {
            const msg = JSON.parse(event.data);
            if (msg.type === 'transcript') {
                appendMessageBubble(msg.sender, msg.text);
            }
        } else {
            // Decodes and queues assistant synthesized audio chunks
            playSynthesizedAudio(event.data);
        }
    };

    socket.onerror = (err) => {
        console.error("Voice Session WebSocket error:", err);
    };

    socket.onclose = () => {
        console.log("Voice Session WebSocket closed");
        if (statusText) statusText.textContent = 'Status: Ready';
        triggerVisualizer();
    };
}

// Disconnect persistent voice session
function closeVoiceSession() {
    if (socket) {
        socket.close();
        socket = null;
    }
    visualizerMode = 'idle';
    audioQueue = [];
    isPlayingAudio = false;
    isRecording = false;
    
    const pttMicBtn = document.getElementById('ptt-mic-btn');
    if (pttMicBtn) {
        pttMicBtn.classList.remove('bg-red-500');
        pttMicBtn.classList.add('bg-primary');
    }
    
    triggerVisualizer();
}

// Click to Speak Start Record Handler
async function startClickSpeakRecording() {
    if (visualizerMode === 'speaking') {
        console.log("PTT locked: assistant speaking");
        return;
    }
    
    if (isRecording) return;
    isRecording = true;
    visualizerMode = 'listening';

    const pttMicBtn = document.getElementById('ptt-mic-btn');
    const statusText = document.getElementById('portal-status-text');

    if (pttMicBtn) {
        pttMicBtn.classList.remove('bg-primary');
        pttMicBtn.classList.add('bg-red-500');
        pttMicBtn.title = "Click to Stop and Send";
    }
    if (statusText) statusText.textContent = isMuted ? 'Status: Muted' : 'Status: Listening...';

    triggerVisualizer();

    try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        
        const source = audioContext.createMediaStreamSource(mediaStream);
        scriptProcessor = audioContext.createScriptProcessor(2048, 1, 1);

        scriptProcessor.onaudioprocess = (e) => {
            // Block streaming when muted
            if (isMuted) return;
            
            if (socket && socket.readyState === WebSocket.OPEN) {
                const inputData = e.inputBuffer.getChannelData(0);
                const int16Buffer = float32ToInt16(inputData);
                socket.send(int16Buffer);
            }
        };

        source.connect(scriptProcessor);
        scriptProcessor.connect(audioContext.destination);
    } catch (err) {
        console.error("Microphone capture failed:", err);
        if (statusText) statusText.textContent = 'Status: Mic Error';
        stopClickSpeakRecording();
    }
}

// Click to Speak Stop Record Handler
function stopClickSpeakRecording() {
    if (!isRecording) return;
    isRecording = false;
    visualizerMode = 'idle';

    const pttMicBtn = document.getElementById('ptt-mic-btn');
    const statusText = document.getElementById('portal-status-text');

    if (pttMicBtn) {
        pttMicBtn.classList.remove('bg-red-500');
        pttMicBtn.classList.add('bg-primary');
        pttMicBtn.title = "Click to Speak";
    }
    if (statusText) statusText.textContent = 'Status: Thinking...';

    triggerVisualizer();

    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "stop_recording" }));
    }

    cleanupMicrophone();
}

// Release mic capture tracks
function cleanupMicrophone() {
    if (scriptProcessor) {
        scriptProcessor.disconnect();
        scriptProcessor = null;
    }
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        mediaStream = null;
    }
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }
}

// Draw base visualizer concentric lines
function drawBaseline(canvas, ctx) {
    visualizerMode = 'idle';
    triggerVisualizer();
}

// AJAX-based Reset of Conversational Memory without page reload
async function clearConversationalMemoryAJAX(sessionId) {
    const messagesPanel = document.getElementById('messages-panel');
    const workflowBadge = document.getElementById('workflow-badge');
    const trackingSlot = document.getElementById('tracking-slot');
    const locationSlot = document.getElementById('location-slot');
    const dateSlot = document.getElementById('date-slot');
    
    try {
        const response = await fetch(`/session/clear/${sessionId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            if (data.status === 'reset') {
                if (messagesPanel) {
                    messagesPanel.innerHTML = '';
                }
                if (data.greeting) {
                    appendMessageBubble('assistant', data.greeting);
                }
                if (workflowBadge) workflowBadge.textContent = 'IDLE';
                if (trackingSlot) trackingSlot.textContent = 'Not collected';
                if (locationSlot) locationSlot.textContent = 'Not collected';
                if (dateSlot) dateSlot.textContent = 'Not collected';
                
                console.log("Session memory reset completed successfully");
            }
        } else {
            console.error("Failed to reset session memory:", response.statusText);
        }
    } catch (e) {
        console.error("AJAX Reset failed:", e);
    }
}

// Enforce strict DOMContentLoaded initialization and event registration
document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize canvas concentric rings if present
    const canvas = document.getElementById('voiceWaveCanvas');
    if (canvas) {
        const ctx = canvas.getContext('2d');
        const resizeCanvas = () => {
            canvas.width = canvas.clientWidth * window.devicePixelRatio;
            canvas.height = canvas.clientHeight * window.devicePixelRatio;
            ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
        };
        resizeCanvas();
        drawBaseline(canvas, ctx);
    }

    // 2. Bind Initiate Voice Agent toggle trigger to manage panel expansion & WebSocket
    const initiateBtn = document.getElementById('initiate-voice-btn');
    const voicePanel = document.getElementById('inline-voice-panel');
    
    if (initiateBtn && voicePanel) {
        initiateBtn.addEventListener('click', (e) => {
            e.preventDefault();
            
            // Unlock Web Audio context on user gesture
            const pCtx = getPlaybackContext();
            unlockAudioContext(pCtx);
            
            if (voicePanel.classList.contains('hidden')) {
                voicePanel.classList.remove('hidden');
                initiateBtn.classList.remove('bg-primary');
                initiateBtn.classList.add('bg-red-600');
                initiateBtn.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                    Terminate Voice Agent
                `;
                
                const pttMicBtn = document.getElementById('ptt-mic-btn');
                const sessionId = pttMicBtn ? pttMicBtn.getAttribute('data-session-id') : '';
                startVoiceSession(sessionId);
            } else {
                voicePanel.classList.add('hidden');
                initiateBtn.classList.remove('bg-red-600');
                initiateBtn.classList.add('bg-primary');
                initiateBtn.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg>
                    Initiate Voice Agent
                `;
                closeVoiceSession();
            }
        });
    }

    // 3. Bind click-to-speak recording toggles to central mic button
    const pttMicBtn = document.getElementById('ptt-mic-btn');
    if (pttMicBtn) {
        pttMicBtn.addEventListener('click', (e) => {
            e.preventDefault();
            
            // Unlock Web Audio context defensively
            const pCtx = getPlaybackContext();
            unlockAudioContext(pCtx);
            
            if (isRecording) {
                stopClickSpeakRecording();
            } else {
                startClickSpeakRecording();
            }
        });
    }

    // 4. Bind Mute Microphone toggle handler to mute button
    const muteMicBtn = document.getElementById('mute-mic-btn');
    const statusText = document.getElementById('portal-status-text');
    
    if (muteMicBtn) {
        muteMicBtn.addEventListener('click', (e) => {
            e.preventDefault();
            isMuted = !isMuted;
            
            if (isMuted) {
                // Set active mute state styles
                muteMicBtn.classList.remove('bg-card', 'text-muted-foreground', 'border-border');
                muteMicBtn.classList.add('bg-red-500/20', 'border-red-500', 'text-red-500');
                muteMicBtn.title = "Unmute Microphone";
                
                // Swap to crossed mic SVG icon
                muteMicBtn.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" id="mute-icon-svg"><line x1="1" y1="1" x2="23" y2="23"/><path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V5a3 3 0 0 0-5.94-.6"/><path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23"/><line x1="12" y1="19" x2="12" y2="22"/></svg>
                `;
                
                if (statusText) statusText.textContent = 'Status: Muted';
            } else {
                // Restore inactive styles
                muteMicBtn.classList.remove('bg-red-500/20', 'border-red-500', 'text-red-500');
                muteMicBtn.classList.add('bg-card', 'text-muted-foreground', 'border-border');
                muteMicBtn.title = "Mute Microphone";
                
                // Swap back to normal mic icon
                muteMicBtn.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" id="mute-icon-svg"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg>
                `;
                
                if (statusText) {
                    statusText.textContent = isRecording ? 'Status: Listening...' : 'Status: Ready';
                }
            }
        });
    }

    // Expose handlers to global window scope defensively
    window.startClickSpeakRecording = startClickSpeakRecording;
    window.stopClickSpeakRecording = stopClickSpeakRecording;
    window.clearConversationalMemoryAJAX = clearConversationalMemoryAJAX;
    window.drawBaseline = drawBaseline;
});
