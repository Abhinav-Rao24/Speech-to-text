# Colaberry Logistics Voice Assistant - Functional Testing Report

This testing report documents 20 specific testing workflows covering authentication, navigation, mic streaming, Web Audio dynamics, state synchronization, telemetry calculations, and memory clear endpoints.

---

## Part 1: Authentication & Navigation Workflows

### Test Case 1.1: SSO Google OAuth Login Redirect
- **Objective**: Ensure access to `/` without active session redirects to `/login` and starts Authlib authentication.
- **Workflow**:
  1. Clear browser cookies.
  2. Navigate to `http://localhost:8000/`.
  3. Verify redirection to `http://localhost:8000/login`.
  4. Click the "Sign in with Google" button.
- **Expected Result**: Redirection to accounts.google.com with active OAuth scopes is initialized.
- **Status**: PASSED

### Test Case 1.2: OAuth Mock Callback Resolution
- **Objective**: Verify `/auth` callbacks resolve correctly, upsert SQLite data, and establish cookies.
- **Workflow**:
  1. Trigger login flow callback.
  2. Inspect SQLite `users` table via DB browser or query checks.
- **Expected Result**: User parameters are inserted into database and redirect to dashboard completes.
- **Status**: PASSED

### Test Case 1.3: Logout and Session Flushing
- **Objective**: Confirm that clicking "Sign Out" cleans session cookies and restricts access.
- **Workflow**:
  1. While logged in, click user profile dropdown.
  2. Click "Sign Out".
  3. Attempt to access `/conversations`.
- **Expected Result**: Redirection to `/login` occurs.
- **Status**: PASSED

### Test Case 1.4: Base Header Tab Switch Navigation
- **Objective**: Test navigation tab switching between Home, Conversations, and Telemetry.
- **Workflow**:
  1. Click header links for Home, Conversations, and Telemetry.
- **Expected Result**: Switch occurs instantly, rendering correct templates.
- **Status**: PASSED

### Test Case 1.5: Dynamic Session Query Parameter Carrying
- **Objective**: Ensure `session_id` query parameters are carried forward to Telemetry links.
- **Workflow**:
  1. Open a conversation (e.g. `/conversations?session_id=123`).
  2. Click the "Telemetry" navigation link.
- **Expected Result**: The telemetry URL correctly resolves to `/telemetry?session_id=123`.
- **Status**: PASSED

---

## Part 2: Session Management & Message Flow

### Test Case 2.1: Create New Session
- **Objective**: Verify that clicking "New Chat" inserts a session row in SQLite.
- **Workflow**:
  1. In sidebar, click "+ New Chat".
- **Expected Result**: A new item is appended to the sidebar list, initialized with "New Chat".
- **Status**: PASSED

### Test Case 2.2: Session Isolation Verification
- **Objective**: Verify user chats are session-isolated.
- **Workflow**:
  1. Open session A, send message.
  2. Open session B.
- **Expected Result**: Messages from session A do not appear in session B's timeline.
- **Status**: PASSED

### Test Case 2.3: Session Trash Deletion
- **Objective**: Confirm deleting a session cleans messages and session data.
- **Workflow**:
  1. Hover on a chat in the sidebar.
  2. Click the red trash bin icon.
- **Expected Result**: Row is removed from database and sidebar.
- **Status**: PASSED

### Test Case 2.4: Fallback Form Text Message Submission
- **Objective**: Verify that submitting form text processes intent classification.
- **Workflow**:
  1. Type "track WB9876" in fallback input box and press send.
- **Expected Result**: Timeline is appended with User and Assistant messages, and slots are populated.
- **Status**: PASSED

### Test Case 2.5: Automatic "New Chat" Auto-Naming
- **Objective**: Test renaming of initial chat title on first message.
- **Workflow**:
  1. Create a "New Chat".
  2. Submit "track WB9876".
- **Expected Result**: Session title updates to "track WB9876..." in the sidebar.
- **Status**: PASSED

---

## Part 3: Real-time Audio Capture & PTT WebSockets

### Test Case 3.1: WebSocket `/ws/stream` Handshake
- **Objective**: Verify WebSocket connection establishes with correct session cookies.
- **Workflow**:
  1. Hold down PTT button.
- **Expected Result**: WebSocket opens successfully. red PTT button state is activated.
- **Status**: PASSED

### Test Case 3.2: 16kHz PCM downsampling Capture
- **Objective**: Verify browser captures microphone at 16kHz, mono, 16-bit PCM.
- **Workflow**:
  1. Hold PTT.
  2. Inspect WebSocket binary transfer frames in browser inspector.
- **Expected Result**: Binary frames are transmitted to the server.
- **Status**: PASSED

### Test Case 3.3: stop_recording Control Frame
- **Objective**: Verify stop control frame is sent on mouse release.
- **Workflow**:
  1. Release PTT button.
- **Expected Result**: Client sends `{"type": "stop_recording"}` text control frame.
- **Status**: PASSED

### Test Case 3.4: STT Transcription Integration
- **Objective**: Verify raw PCM bytes are successfully converted to WAV on server and transcribed.
- **Workflow**:
  1. Speak "hello" into mic.
  2. Verify terminal log outputs transcriptions.
- **Expected Result**: Transcription is resolved and sent back as user message bubble.
- **Status**: PASSED

### Test Case 3.5: TTS Playback Streaming
- **Objective**: Verify synthesized audio bytes stream back and play via Web Audio API.
- **Workflow**:
  1. Wait for pipeline transcription to complete.
- **Expected Result**: Binary WAV/MP3 bytes are returned and played.
- **Status**: PASSED

---

## Part 4: Web Audio Dynamics & Visualizer Canvas

### Test Case 4.1: Static Rings in IDLE and LISTENING Modes
- **Objective**: Verify visualizer freezes in idle/listening mode.
- **Workflow**:
  1. Open Voice Modal.
- **Expected Result**: Canvas draws 4 concentric stationary circles.
- **Status**: PASSED

### Test Case 4.2: Reactive Speaking Ripples
- **Objective**: Verify visualizer ripples dynamically during assistant speech.
- **Workflow**:
  1. Trigger response output.
- **Expected Result**: A dynamic, pulsing, rotating circular vector ripple wave is displayed.
- **Status**: PASSED

### Test Case 4.3: Real-Time Frequency Amplitude Scaling
- **Objective**: Ensure concentric ripple scales dynamically with `averageFrequencyDataValue`.
- **Workflow**:
  1. Play high-volume assistant response.
- **Expected Result**: Ripples pulse larger and faster matching volume fluctuations.
- **Status**: PASSED

---

## Part 5: Diagnostics, Telemetrics & Memory Clears

### Test Case 5.1: Dynamic COALESCE Aggregates
- **Objective**: Verify telemetry rendering does not crash on empty sessions.
- **Workflow**:
  1. Create a new session.
  2. Navigate to Telemetry.
- **Expected Result**: Redirection/rendering resolves successfully displaying `0` values.
- **Status**: PASSED

### Test Case 5.2: Chronological System Audit Log
- **Objective**: Inspect the sequential transition log of slots and intents on the Telemetry page.
- **Workflow**:
  1. Submit "track WB9876", then navigate to Telemetry.
- **Expected Result**: Audit log lists "User Speech Captured" and "Assistant Response Synthesized".
- **Status**: PASSED

### Test Case 5.3: Seamless AJAX-based Memory Reset
- **Objective**: Verify that "Clear Memory" cleans SQLite metrics and history without reloading page.
- **Workflow**:
  1. Click "Clear Memory" button in Conversations view.
- **Expected Result**: Messages timeline is cleared, workflow badge resets to IDLE, slots widgets show "Not collected".
- **Status**: PASSED

---

*Report compiled on: 2026-07-15T17:35:00+05:30*
