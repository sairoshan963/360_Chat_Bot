import { useState, useRef, useCallback } from 'react';

/**
 * useSpeechToText — wraps the Web Speech API for voice input.
 * Works in Chrome/Edge. Returns transcript, listening state, toggle, and stop.
 *
 * Options:
 *   continuous      — keep listening until manually stopped (default: false — stops after a pause)
 *   interimResults  — show partial results while speaking (default: true)
 *   lang            — language code (default: 'en-US')
 *   onFinalResult   — callback(finalTranscript) fired when recognition ends with content
 */
export function useSpeechToText({
  continuous = false,
  interimResults = true,
  lang = 'en-US',
  onFinalResult = null,
} = {}) {
  const recognitionRef  = useRef(null);
  const finalTextRef    = useRef('');
  const [listening,   setListening]   = useState(false);
  const [transcript,  setTranscript]  = useState('');

  const startListening = useCallback(() => {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      alert('Voice input is not supported in this browser. Please use Chrome or Edge.');
      return;
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    // Always create a fresh instance so settings are applied cleanly
    const rec = new SpeechRecognition();
    rec.continuous      = continuous;
    rec.interimResults  = interimResults;
    rec.lang            = lang;

    rec.onresult = (event) => {
      let interim = '';
      let final   = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const t = event.results[i][0].transcript;
        if (event.results[i].isFinal) final += t;
        else interim += t;
      }
      // Accumulate final portions; show interim live in transcript
      if (final) finalTextRef.current += (finalTextRef.current ? ' ' : '') + final.trim();
      setTranscript(finalTextRef.current + (interim ? (finalTextRef.current ? ' ' : '') + interim : ''));
    };

    rec.onend = () => {
      setListening(false);
      const result = finalTextRef.current.trim();
      if (result && onFinalResult) onFinalResult(result);
      recognitionRef.current = null;
    };

    rec.onerror = (e) => {
      if (e.error !== 'no-speech') console.warn('SpeechRecognition error:', e.error);
      setListening(false);
      recognitionRef.current = null;
    };

    finalTextRef.current  = '';
    recognitionRef.current = rec;
    setTranscript('');
    rec.start();
    setListening(true);
  }, [continuous, interimResults, lang, onFinalResult]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop(); // triggers onend → fires onFinalResult
    }
    setListening(false);
  }, []);

  const toggleListening = useCallback(() => {
    if (listening) stopListening();
    else startListening();
  }, [listening, startListening, stopListening]);

  return { listening, transcript, toggleListening, stopListening };
}
