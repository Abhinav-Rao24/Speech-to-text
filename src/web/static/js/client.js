// client.js - Real-time client audio streaming and Web Audio playback for Logistics Voice Portal

let audioContext = null;
let mediaStream = null;
let scriptProcessor = null;
let socket = null;
let playbackContext = null;
let analyser = null;
let animationFrameId = null;
let isRecording = false;
let visualizerMode = 'idle'; // 'idle', 'listening', 'speaking'

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

// Play returning binary audio chunks (WAV/MP3) via Web Audio API with AnalyserNode
function playSynthesizedAudio(arrayBuffer) {
    try {
        const ctx = getPlaybackContext();
        ctx.decodeAudioData(arrayBuffer, (decodedBuffer) => {
            const source = ctx.createBufferSource();
            source.buffer = decodedBuffer;
            
            // Set up AnalyserNode for real-time visualization frequency extraction
            analyser = ctx.createAnalyser();
            analyser.fftSize = 256;
            
            source.connect(analyser);
            analyser.connect(ctx.destination);
            
            visualizerMode = 'speaking';
            
            const statusText = document.getElementById('portal-status-text');
            const helpText = document.getElementById('portal-help-text');
            const pttMicBtn = document.getElementById('ptt-mic-btn');
            
            if (statusText) statusText.textContent = 'Speaking...';
            if (helpText) helpText.textContent = 'Playing logistics assistant audio response...';
            
            // Lock user mic controls during assistant playback
            if (pttMicBtn) {
                pttMicBtn.disabled = true;
                pttMicBtn.classList.add('opacity-50', 'pointer-events-none');
            }
            
            // Start the visualizer rendering loop
            triggerVisualizer();
            
            source.onended = () => {
                visualizerMode = 'idle';
                triggerVisualizer(); // Re-draw static rings and freeze
                
                if (statusText) statusText.textContent = 'Voice Agent Ready';
                if (helpText) helpText.textContent = 'Press and hold the button to record your speech. Release when finished.';
                
                // Unlock user mic controls
                if (pttMicBtn) {
                    pttMicBtn.disabled = false;
                    pttMicBtn.classList.remove('opacity-50', 'pointer-events-none');
                }
                analyser = null;
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

// Circular "thread wave" concentric visualizer loop
function updateVisualizer() {
    const canvas = document.getElementById('voiceWaveCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    // Explicit clean
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const rings = [45, 80, 115, 150];
    
    if (visualizerMode === 'speaking' && analyser) {
        // Mode 1: SPEAKING - concentric ripples scaling reactively to Web Audio frequency
        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        analyser.getByteFrequencyData(dataArray);
        
        let sum = 0;
        for (let i = 0; i < bufferLength; i++) {
            sum += dataArray[i];
        }
        const average = sum / bufferLength;
        const scale = 1.0 + (average / 128.0); // calculate dynamic scale factor
        
        const time = Date.now() * 0.003;
        
        // Define overlapping emerald colors
        const colors = [
            'rgba(16, 185, 129, 0.45)', // emerald-500
            'rgba(52, 211, 153, 0.35)', // emerald-400
            'rgba(110, 231, 183, 0.3)',  // emerald-300
            'rgba(5, 150, 105, 0.3)'     // emerald-600
        ];
        
        rings.forEach((baseRadius, index) => {
            ctx.beginPath();
            ctx.strokeStyle = colors[index % colors.length];
            ctx.lineWidth = 2.5;
            
            const points = 120;
            const freq = 4 + index;
            const phase = time * (index % 2 === 0 ? 1.5 : -1.5);
            const amp = 5 + (index * 2.5) * scale;
            
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
        // Mode 2: LISTENING or IDLE - concentric lines frozen as perfect rings
        const borderStyle = getComputedStyle(document.documentElement).getPropertyValue('--border').trim() || '#e5e7eb';
        
        rings.forEach((baseRadius) => {
            ctx.beginPath();
            ctx.strokeStyle = borderStyle;
            ctx.lineWidth = 1.5;
            ctx.arc(centerX, centerY, baseRadius, 0, Math.PI * 2);
            ctx.stroke();
        });
        animationFrameId = null; // Freeze loop
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

// Establish Web Socket and start 16kHz PCM capture
async function startPttRecording(sessionId) {
    if (visualizerMode === 'speaking') {
        console.log("PTT locked: assistant speaking");
        return; // Prevent interruptions when speaking
    }
    
    if (isRecording) return;
    isRecording = true;
    visualizerMode = 'listening';

    const pttMicBtn = document.getElementById('ptt-mic-btn');
    const statusText = document.getElementById('portal-status-text');
    const helpText = document.getElementById('portal-help-text');

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

        // Render frozen rings
        triggerVisualizer();

        try {
            // Request microphone access
            mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
            audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
            
            const source = audioContext.createMediaStreamSource(mediaStream);
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
    visualizerMode = 'idle';

    const pttMicBtn = document.getElementById('ptt-mic-btn');
    const statusText = document.getElementById('portal-status-text');
    const helpText = document.getElementById('portal-help-text');

    if (pttMicBtn) {
        pttMicBtn.classList.remove('bg-red-500');
        pttMicBtn.classList.add('bg-primary');
    }
    if (statusText) statusText.textContent = 'Processing...';
    if (helpText) helpText.textContent = 'Running pipeline elements...';

    // Clear wave visualization back to flat rings
    triggerVisualizer();

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

// Draw static concentric rings on load
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
                // Clear all chat bubbles in timeline instantly
                if (messagesPanel) {
                    messagesPanel.innerHTML = '';
                }
                // Append fresh greeting
                if (data.greeting) {
                    appendMessageBubble('assistant', data.greeting);
                }
                // Update live slots widgets in conversations side panel if present
                if (workflowBadge) {
                    workflowBadge.textContent = 'IDLE';
                }
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
