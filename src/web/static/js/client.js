// client.js - Real-time client audio streaming and Web Audio playback for Logistics Voice Portal

let audioContext = null;
let mediaStream = null;
let scriptProcessor = null;
let socket = null;
let playbackContext = null;
let animationFrameId = null;
let isRecording = false;

// Initialize Playback Context for Web Audio API
function getPlaybackContext() {
    if (!playbackContext) {
        playbackContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (playbackContext.state === 'suspended') {
        playbackContext.resume();
    }
    return playbackContext;
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

// Play returning binary audio chunks (WAV/MP3) via Web Audio API
function playSynthesizedAudio(arrayBuffer) {
    try {
        const ctx = getPlaybackContext();
        ctx.decodeAudioData(arrayBuffer, (decodedBuffer) => {
            const source = ctx.createBufferSource();
            source.buffer = decodedBuffer;
            source.connect(ctx.destination);
            
            const statusText = document.getElementById('portal-status-text');
            const helpText = document.getElementById('portal-help-text');
            if (statusText) statusText.textContent = 'Speaking...';
            if (helpText) helpText.textContent = 'Playing logistics assistant audio response...';
            
            source.onended = () => {
                if (statusText) statusText.textContent = 'Voice Agent Ready';
                if (helpText) helpText.textContent = 'Press and hold the button to record your speech. Release when finished.';
            };
            
            source.start(0);
        }, (decodeError) => {
            console.error("Web Audio decoding failed:", decodeError);
        });
    } catch (e) {
        console.error("Audio playback error:", e);
    }
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

// Draw real-time mock mic input waves on canvas when active
function drawWaveform(canvas, ctx) {
    if (!isRecording) return;
    
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = '#10b981'; // emerald theme green
    ctx.lineWidth = 2;
    ctx.beginPath();
    
    const midY = canvas.height / (2 * window.devicePixelRatio);
    const width = canvas.width / window.devicePixelRatio;
    ctx.moveTo(0, midY);
    
    const time = Date.now() * 0.015;
    for (let x = 0; x < width; x++) {
        // Generate random-looking sin/cos waves scaled to mimic sound activity
        const wave = Math.sin(x * 0.06 + time) * Math.cos(x * 0.02) * (8 + Math.random() * 4);
        ctx.lineTo(x, midY + wave);
    }
    
    ctx.stroke();
    animationFrameId = requestAnimationFrame(() => drawWaveform(canvas, ctx));
}

// Clear visual canvas waves and draw a flat baseline
function drawBaseline(canvas, ctx) {
    if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
    }
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--border').trim() || '#e5e7eb';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    const midY = canvas.height / (2 * window.devicePixelRatio);
    ctx.moveTo(0, midY);
    ctx.lineTo(canvas.width / window.devicePixelRatio, midY);
    ctx.stroke();
}

// Establish Web Socket and start 16kHz PCM capture
async function startPttRecording(sessionId) {
    if (isRecording) return;
    isRecording = true;

    const pttMicBtn = document.getElementById('ptt-mic-btn');
    const statusText = document.getElementById('portal-status-text');
    const helpText = document.getElementById('portal-help-text');
    const canvas = document.getElementById('voiceWaveCanvas');

    if (pttMicBtn) {
        pttMicBtn.classList.remove('bg-primary');
        pttMicBtn.classList.add('bg-red-500');
    }
    if (statusText) statusText.textContent = 'Connecting...';

    // Start WebSocket
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/stream?session_id=${sessionId}`;
    socket = new WebSocket(wsUrl);

    socket.binaryType = 'arraybuffer';

    socket.onopen = async () => {
        if (statusText) statusText.textContent = 'Listening...';
        if (helpText) helpText.textContent = 'Recording microphone input. Release button to submit speech.';

        // Canvas animation
        if (canvas) {
            const ctx = canvas.getContext('2d');
            drawWaveform(canvas, ctx);
        }

        try {
            // Request microphone access
            mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
            audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
            
            const source = audioContext.createMediaStreamSource(mediaStream);
            // ScriptProcessor with 2048 buffer size, 1 input channel, 1 output channel
            scriptProcessor = audioContext.createScriptProcessor(2048, 1, 1);

            scriptProcessor.onaudioprocess = (e) => {
                if (socket.readyState !== WebSocket.OPEN) return;
                const inputData = e.inputBuffer.getChannelData(0);
                const int16Buffer = float32ToInt16(inputData);
                socket.send(int16Buffer);
            };

            source.connect(scriptProcessor);
            scriptProcessor.connect(audioContext.destination);
        } catch (err) {
            console.error("Microphone capture failed:", err);
            if (statusText) statusText.textContent = 'Mic Error';
            if (helpText) helpText.textContent = 'Could not access microphone. Ensure permissions are granted.';
            stopPttRecording();
        }
    };

    socket.onmessage = (event) => {
        if (typeof event.data === 'string') {
            const msg = JSON.parse(event.data);
            if (msg.type === 'transcript') {
                appendMessageBubble(msg.sender, msg.text);
            }
        } else {
            // Binary audio bytes returned from TTS
            playSynthesizedAudio(event.data);
        }
    };

    socket.onerror = (err) => {
        console.error("WebSocket Pipeline Error:", err);
    };

    socket.onclose = () => {
        console.log("WebSocket Closed");
        cleanupMicrophone();
    };
}

// Stop recording and send stop signal
function stopPttRecording() {
    if (!isRecording) return;
    isRecording = false;

    const pttMicBtn = document.getElementById('ptt-mic-btn');
    const statusText = document.getElementById('portal-status-text');
    const helpText = document.getElementById('portal-help-text');
    const canvas = document.getElementById('voiceWaveCanvas');

    if (pttMicBtn) {
        pttMicBtn.classList.remove('bg-red-500');
        pttMicBtn.classList.add('bg-primary');
    }
    if (statusText) statusText.textContent = 'Processing...';
    if (helpText) helpText.textContent = 'Running pipeline elements...';

    // Clear wave visualization
    if (canvas) {
        const ctx = canvas.getContext('2d');
        drawBaseline(canvas, ctx);
    }

    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "stop_recording" }));
    }

    cleanupMicrophone();
}

// Release microphone capture handles
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
