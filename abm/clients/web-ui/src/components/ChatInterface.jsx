import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Bot, User, Loader2, ChevronDown, ChevronRight, Mic, Square, Volume2, VolumeX, Radio } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import './ChatInterface.css';

// Encodes a Float32Array of PCM samples (captured directly from the Web
// Audio API — see startRecording below) into a standard 16-bit mono WAV
// Blob. Added 2026-11-02 to replace MediaRecorder's webm/opus output: the
// backend needs raw PCM to run Arabang's WebRTC noise suppressor on it,
// and decoding Opus server-side would need ffmpeg — his own Lesedi
// toolkit deliberately avoids that dependency, so this does too, by
// never producing compressed audio in the first place.
function encodeWav(samples, sampleRate) {
  const numSamples = samples.length;
  const buffer = new ArrayBuffer(44 + numSamples * 2);
  const view = new DataView(buffer);

  const writeString = (offset, str) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };

  writeString(0, 'RIFF');
  view.setUint32(4, 36 + numSamples * 2, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);              // PCM fmt chunk size
  view.setUint16(20, 1, true);                // audio format = PCM
  view.setUint16(22, 1, true);                // channels = 1 (mono)
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);   // byte rate = sampleRate * channels * bytesPerSample
  view.setUint16(32, 2, true);                // block align = channels * bytesPerSample
  view.setUint16(34, 16, true);               // bits per sample
  writeString(36, 'data');
  view.setUint32(40, numSamples * 2, true);

  let offset = 44;
  for (let i = 0; i < numSamples; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: 'audio/wav' });
}

function MessageBubble({ msg }) {
  const [sourcesExpanded, setSourcesExpanded] = useState(false);
  return (
    <div className={`message-bubble ${msg.role}`}>
      <div className="message-text">
        {msg.role === 'agent' ? (
          <ReactMarkdown>{msg.text}</ReactMarkdown>
        ) : (
          msg.text
        )}
      </div>
      {msg.role === 'agent' && msg.sources && msg.sources.length > 0 && (
        <div className="message-sources">
          <div 
            className="sources-toggle" 
            onClick={() => setSourcesExpanded(!sourcesExpanded)}
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', userSelect: 'none' }}
          >
            {sourcesExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            <span style={{ fontWeight: 500, fontSize: '0.85rem' }}>{msg.sources.length} Sources</span>
          </div>
          {sourcesExpanded && (
            <ul style={{ marginTop: '0.75rem' }}>
              {msg.sources.map((src, i) => (
                <li key={i}>
                  <span className="source-collection">[{src.collection}]</span>
                  {src.text}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default function ChatInterface({ currentSessionId, onSessionUpdated }) {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [voiceReplyEnabled, setVoiceReplyEnabled] = useState(false);
  const [alwaysListening, setAlwaysListening] = useState(false);
  const messagesEndRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioContextRef = useRef(null);
  const vadFrameRef = useRef(null);
  // Refs mirror the state above so the recording loop (callbacks firing
  // after setTimeout/async gaps) always sees the LATEST value, not a
  // stale one captured when that closure was created.
  const alwaysListeningRef = useRef(false);
  const consecutiveFailuresRef = useRef(0);
  const MAX_CONSECUTIVE_FAILURES = 5; // circuit breaker so a stuck mic/API never loops forever
  // Root-cause fix (2026-11-02): currentSessionId is a PROP, and the
  // always-listening loop's handleSend/transcribeAndSend/startRecording
  // chain gets re-invoked from setTimeout/speech callbacks several
  // closures removed from any render — those closures kept reading
  // whatever currentSessionId WAS when that chain was first created
  // (often null, on the very first voice turn), so every voice turn after
  // that sent no session_id at all and the backend minted a brand new
  // session each time — exactly Arabang's "a new chat every single
  // command" report. Mirroring the prop into a ref, kept current by the
  // effect below, means handleSend always reads the latest value no
  // matter how stale the closure calling it is.
  const currentSessionIdRef = useRef(currentSessionId);
  useEffect(() => {
    currentSessionIdRef.current = currentSessionId;
  }, [currentSessionId]);
  // Root-cause fix (2026-11-02): tracks "the wake word was just
  // acknowledged, the NEXT thing heard is the command itself" — without
  // this, every recording cycle re-checked for the wake word, so a
  // command said *after* the ack (rather than in the same breath as
  // "ABM 2.0") never matched anything and was silently dropped. That's
  // Arabang's "doesn't respond unless I say it all at once" report.
  const awaitingCommandRef = useRef(false);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (currentSessionId) {
      fetch(`http://localhost:8080/api/session?id=${currentSessionId}`)
        .then(res => {
          if (!res.ok) throw new Error('Session not found');
          return res.json();
        })
        .then(data => {
          setMessages(data.messages || []);
        })
        .catch(err => {
          console.error(err);
          setMessages([]);
        });
    } else {
      setMessages([]);
    }
  }, [currentSessionId]);

  const handleSend = async (overrideText) => {
    const textToSend = (overrideText !== undefined ? overrideText : inputValue).trim();
    if (!textToSend || isLoading) return;
    
    const userMessage = { id: Date.now(), role: 'user', text: textToSend };
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      const payload = { question: userMessage.text };
      if (currentSessionIdRef.current) {
        payload.session_id = currentSessionIdRef.current;
      }
      const response = await fetch('http://localhost:8080/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) throw new Error('API Error');
      
      const data = await response.json();
      
      const agentMessage = {
        id: Date.now() + 1,
        role: 'agent',
        text: data.synthesis || "I couldn't generate an answer.",
        sources: data.hits || [],
        metadata: { department: data.department, confidence: data.confidence }
      };
      
      setMessages(prev => [...prev, agentMessage]);
      currentSessionIdRef.current = data.session_id;
      onSessionUpdated(data.session_id);
      speakText(agentMessage.text);
    } catch (error) {
      console.error(error);
      const errorMessage = {
        id: Date.now() + 1,
        role: 'agent',
        text: 'Sorry, I encountered an error communicating with the backend.'
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
      // If this question came in through the always-listening loop, go
      // back to listening for the next "ABM 2.0 ..." once this reply is
      // in, the same way a push-to-talk cycle ends ready for the next one.
      if (alwaysListeningRef.current) {
        setTimeout(() => startRecording(), 400);
      }
    }
  };

  const speakText = (text, { force = false } = {}) => {
    if ((!voiceReplyEnabled && !force) || !text) return;
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      window.speechSynthesis.speak(utterance);
    } catch (err) {
      console.error('Speech synthesis failed:', err);
    }
  };

  // Speaks `text` and calls `callback` once it's actually finished playing
  // (not just "started"), so the always-listening loop waits for ABM to
  // stop talking before it starts recording again — otherwise the mic
  // could pick up ABM's own acknowledgment as background noise. Always
  // speaks regardless of the voiceReplyEnabled toggle: this is the
  // listening/not-listening cue itself, not one of ABM's answers. Falls
  // back to a timer if the browser never fires onend/onerror, so the loop
  // can't get stuck waiting forever.
  const speakAndThen = (text, callback) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      callback();
    };
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.onend = finish;
      utterance.onerror = finish;
      window.speechSynthesis.speak(utterance);
      setTimeout(finish, 6000);
    } catch (err) {
      console.error('Speech synthesis failed:', err);
      finish();
    }
  };

  // Matches "ABM", "ABM 2.0", "hey ABM 2.0 launch" etc. at the start of
  // what you said, so in always-listening mode a single breath like
  // "ABM 2.0, what's the weather" splits into wake phrase + real question.
  const WAKE_WORD_RE = /\b(hey\s+)?abm\b[\s.,!]*\b(2\.?0|two\s*point\s*zero)?[\s.,!]*\b(launch)?[\s.,!]*/i;

  const transcribeAndSend = async (audioBlob) => {
    const listening = alwaysListeningRef.current;
    if (!listening) setIsLoading(true);
    // Captured up front, before anything in this call can mutate
    // awaitingCommandRef: while we're still just listening for the wake
    // word (not yet taking down the real command), accuracy matters less
    // than speed, so we ask the backend for the fast Whisper model. Once
    // we're capturing the actual command we want the accurate one.
    const fastMode = listening && !awaitingCommandRef.current;
    const transcribeUrl = `http://localhost:8080/api/voice/transcribe${fastMode ? '?fast=1' : ''}`;
    try {
      const response = await fetch(transcribeUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'audio/wav' },
        body: audioBlob
      });
      // Root-cause fix (2026-11-02): this used to discard the backend's real
      // error message and show a generic guess instead — made it impossible
      // to tell a real Groq-key problem apart from silence/a mic issue.
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.message || 'Transcription failed');
      }

      if (listening) {
        // Always-listening mode: nothing gets sent unless the wake word
        // was actually heard (or we're already past that, see below). A
        // cycle that heard silence or unrelated background noise is
        // normal here, not an error — it just loops again quietly
        // instead of surfacing a bubble.
        consecutiveFailuresRef.current = 0;
        const text = data.text || '';

        if (awaitingCommandRef.current) {
          // The wake word was already acknowledged last cycle — this
          // recording IS the command, whatever it is. Don't require
          // "ABM 2.0" again; requiring it here was exactly why a command
          // said after the acknowledgment (rather than in the same
          // breath as the wake word) used to get silently dropped.
          awaitingCommandRef.current = false;
          if (text.trim()) {
            handleSend(text.trim()); // handleSend's own `finally` resumes listening afterward
            return;
          }
          // Heard nothing usable — fall back to waiting for the wake
          // word again rather than staying stuck in "awaiting command".
          setTimeout(() => startRecording(), 300);
          return;
        }

        const wakeMatch = text.match(WAKE_WORD_RE);
        if (wakeMatch) {
          const remainder = text.slice(wakeMatch.index + wakeMatch[0].length).trim();
          if (remainder) {
            handleSend(remainder); // handleSend's own `finally` resumes listening afterward
            return;
          }
          // Wake word alone, nothing after it yet — acknowledge out loud
          // so there's no guessing whether ABM actually heard "ABM 2.0",
          // then wait for the acknowledgment to finish before listening
          // specifically for the command (also avoids the mic catching
          // ABM's own voice right as the next recording cycle starts).
          awaitingCommandRef.current = true;
          const ackMessage = { id: Date.now(), role: 'agent', text: "Yes, I'm listening — go ahead." };
          setMessages(prev => [...prev, ackMessage]);
          speakAndThen(ackMessage.text, () => startRecording());
          return;
        }
        // No wake word heard at all (silence or unrelated background
        // noise) — stay quiet, just go around again.
        setTimeout(() => startRecording(), 300);
        return;
      }

      if (data.text) {
        handleSend(data.text);
      } else {
        setIsLoading(false);
      }
    } catch (error) {
      console.error(error);
      if (listening) {
        consecutiveFailuresRef.current += 1;
        if (consecutiveFailuresRef.current >= MAX_CONSECUTIVE_FAILURES) {
          alwaysListeningRef.current = false;
          setAlwaysListening(false);
          consecutiveFailuresRef.current = 0;
          const errorMessage = {
            id: Date.now(),
            role: 'agent',
            text: `I turned off always-listening after several transcription failures in a row (${error.message || 'unknown error'}). Tap the listening button to try again.`
          };
          setMessages(prev => [...prev, errorMessage]);
        } else {
          setTimeout(() => startRecording(), 300);
        }
        return;
      }
      const errorMessage = {
        id: Date.now(),
        role: 'agent',
        text: `Sorry, I couldn't transcribe that: ${error.message || 'unknown error'}`
      };
      setMessages(prev => [...prev, errorMessage]);
      setIsLoading(false);
    }
  };

  // Voice-activity detection: auto-stop once you've spoken and then gone
  // quiet, instead of requiring a second click. Tune SPEAKING_RMS_THRESHOLD
  // if it cuts you off too early/late on your specific mic.
  const SPEAKING_RMS_THRESHOLD = 0.02;
  // Trimmed from 1400ms (2026-11-02): every turn waits this long after you
  // stop talking before ABM reacts, so it's the single biggest lever on
  // felt latency. 1000ms is still enough pause-room for most speech; if it
  // starts cutting you off mid-sentence, nudge this back up.
  const SILENCE_DURATION_MS = 1000;   // quiet time after speech before auto-stop
  const MAX_RECORDING_MS = 20000;     // hard cap so it can never hang forever

  const stopVad = () => {
    if (vadFrameRef.current) {
      cancelAnimationFrame(vadFrameRef.current);
      vadFrameRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
  };

  // Starts one VAD-gated recording cycle: records until you go quiet (or
  // MAX_RECORDING_MS), then transcribes and hands off to transcribeAndSend.
  // Used both by the manual mic button (one cycle) and by the
  // always-listening loop, which calls this again after every cycle.
  const startRecording = async () => {
    // mediaRecorderRef (not the isRecording state) is the reliable guard here:
    // this function gets re-invoked from setTimeout callbacks chained several
    // closures deep inside the always-listening loop, where a captured
    // `isRecording` state value can be stale — the ref is always live.
    if (mediaRecorderRef.current) return; // already mid-cycle — don't overlap
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          // Ask the browser's own WebRTC audio pipeline to clean the mic
          // input too, as a free first pass before Arabang's suppressor
          // runs server-side on the actual PCM — the two stack fine.
          noiseSuppression: true,
          echoCancellation: true,
          autoGainControl: true,
        },
      });
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      const audioContext = new AudioContextClass();
      if (audioContext.state === 'suspended') {
        // Cycles after the first are kicked off from a setTimeout/speech
        // callback, not a direct click, so some browsers may hand back a
        // suspended context here — resume() is a no-op if it's already
        // running, so this is safe to call unconditionally.
        await audioContext.resume().catch(() => {});
      }
      const source = audioContext.createMediaStreamSource(stream);

      // Captures raw PCM samples directly — instead of MediaRecorder's
      // compressed webm/opus — via a ScriptProcessorNode on the same
      // stream used for amplitude/VAD monitoring below. ScriptProcessorNode
      // is deprecated but still fully supported everywhere; it only runs
      // when connected through to a destination, hence the muted gain node.
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      const silentGain = audioContext.createGain();
      silentGain.gain.value = 0;
      source.connect(processor);
      processor.connect(silentGain);
      silentGain.connect(audioContext.destination);
      audioContextRef.current = audioContext;

      const capturedChunks = [];
      let hasSpoken = false;
      let silenceStartedAt = null;
      const startedAt = Date.now();
      let finished = false;

      const finishRecording = () => {
        if (finished) return;
        finished = true;
        processor.onaudioprocess = null;
        try { processor.disconnect(); } catch { /* already disconnected */ }
        try { silentGain.disconnect(); } catch { /* already disconnected */ }
        try { source.disconnect(); } catch { /* already disconnected */ }
        stopVad();
        stream.getTracks().forEach(track => track.stop());
        setIsRecording(false);
        mediaRecorderRef.current = null;

        let totalLength = 0;
        for (const chunk of capturedChunks) totalLength += chunk.length;
        const merged = new Float32Array(totalLength);
        let writeOffset = 0;
        for (const chunk of capturedChunks) {
          merged.set(chunk, writeOffset);
          writeOffset += chunk.length;
        }
        const wavBlob = encodeWav(merged, audioContext.sampleRate);
        transcribeAndSend(wavBlob);
      };

      processor.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0);
        capturedChunks.push(new Float32Array(input)); // copy — browser reuses this buffer

        let sumSquares = 0;
        for (let i = 0; i < input.length; i++) sumSquares += input[i] * input[i];
        const rms = Math.sqrt(sumSquares / input.length);

        if (rms > SPEAKING_RMS_THRESHOLD) {
          hasSpoken = true;
          silenceStartedAt = null;
        } else if (hasSpoken) {
          if (silenceStartedAt === null) silenceStartedAt = Date.now();
          if (Date.now() - silenceStartedAt > SILENCE_DURATION_MS) {
            finishRecording();
            return;
          }
        }

        if (Date.now() - startedAt > MAX_RECORDING_MS) {
          finishRecording();
        }
      };

      // Shim so the existing `mediaRecorderRef.current?.stop()` calls
      // (manual mic button, always-listening toggle-off) keep working
      // unchanged even though there's no real MediaRecorder any more.
      mediaRecorderRef.current = { stop: finishRecording };
      setIsRecording(true);
    } catch (err) {
      console.error('Mic access failed:', err);
      mediaRecorderRef.current = null;
      // In always-listening mode a one-off mic glitch shouldn't spam the
      // chat — it counts toward the same circuit breaker as a transcription
      // failure and just retries, same as any other failed cycle.
      if (alwaysListeningRef.current) {
        consecutiveFailuresRef.current += 1;
        if (consecutiveFailuresRef.current >= MAX_CONSECUTIVE_FAILURES) {
          alwaysListeningRef.current = false;
          setAlwaysListening(false);
          consecutiveFailuresRef.current = 0;
          const errorMessage = {
            id: Date.now(),
            role: 'agent',
            text: "I turned off always-listening — I couldn't access the microphone. Check this page's mic permission and try again."
          };
          setMessages(prev => [...prev, errorMessage]);
        } else {
          setTimeout(() => startRecording(), 300);
        }
        return;
      }
      const errorMessage = {
        id: Date.now(),
        role: 'agent',
        text: "I couldn't access your microphone — check this page's mic permission in your browser."
      };
      setMessages(prev => [...prev, errorMessage]);
    }
  };

  const handleMicClick = async () => {
    if (isRecording) {
      mediaRecorderRef.current?.stop();
      return;
    }
    await startRecording();
  };

  const handleAlwaysListeningToggle = () => {
    if (alwaysListening) {
      alwaysListeningRef.current = false;
      awaitingCommandRef.current = false;
      setAlwaysListening(false);
      if (isRecording) {
        mediaRecorderRef.current?.stop();
      }
    } else {
      alwaysListeningRef.current = true;
      awaitingCommandRef.current = false;
      consecutiveFailuresRef.current = 0;
      setAlwaysListening(true);
      if (!isRecording) {
        startRecording();
      }
    }
  };

  return (
    <div className="chat-interface">
      <div className="messages-container">
        {messages.length === 0 && (
          <motion.div 
            className="empty-state"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <Bot size={48} className="empty-icon" />
            <p>Ask ABM a question to get started.</p>
          </motion.div>
        )}
        
        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <motion.div 
              key={msg.id} 
              className={`message-wrapper ${msg.role}`}
              initial={{ opacity: 0, y: 20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ type: "spring", stiffness: 300, damping: 25 }}
            >
              <div className={`message-avatar ${msg.role}`}>
                {msg.role === 'agent' ? <Bot size={20} /> : <User size={20} />}
              </div>
              <MessageBubble msg={msg} />
            </motion.div>
          ))}
          
          {isLoading && (
            <motion.div 
              key="loading"
              className="message-wrapper agent"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.2 } }}
            >
              <div className="message-avatar agent">
                <Bot size={20} />
              </div>
              <div className="message-bubble agent loading">
                <Loader2 className="spinner" size={20} />
                <span>Thinking...</span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        <div ref={messagesEndRef} />
      </div>
      
      <div className="input-area glass-panel">
        <button
          className={`always-listening-btn ${alwaysListening ? 'active' : ''}`}
          onClick={handleAlwaysListeningToggle}
          title={alwaysListening ? 'Always listening: on — say "ABM 2.0" then your question' : 'Turn on hands-free listening'}
        >
          <Radio size={18} />
        </button>
        <button
          className={`mic-btn ${isRecording ? 'recording' : ''}`}
          onClick={handleMicClick}
          disabled={isLoading || alwaysListening}
          title={isRecording ? 'Stop recording' : 'Talk to ABM'}
        >
          {isRecording ? <Square size={18} /> : <Mic size={18} />}
        </button>
        <input 
          type="text" 
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder={alwaysListening ? 'Always listening — say "ABM 2.0" then your question...' : (isRecording ? 'Listening...' : 'Ask ABM...')}
          disabled={isLoading || isRecording}
        />
        <button
          className={`voice-toggle-btn ${voiceReplyEnabled ? 'active' : ''}`}
          onClick={() => setVoiceReplyEnabled(v => !v)}
          title={voiceReplyEnabled ? 'Voice replies: on' : 'Voice replies: off'}
        >
          {voiceReplyEnabled ? <Volume2 size={18} /> : <VolumeX size={18} />}
        </button>
        <button className="send-btn" onClick={() => handleSend()} disabled={!inputValue.trim() || isLoading}>
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}
