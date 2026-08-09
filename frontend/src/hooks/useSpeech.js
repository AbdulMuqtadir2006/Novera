import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Thin wrapper over the Web Speech API (window.speechSynthesis). Drives orb +
 * transcript state from real start/end/boundary events. Picks a voice matching
 * `lang` ("en" | "ar") when available.
 *
 * Seam for a premium TTS API (e.g. ElevenLabs): replace the body of `play`
 * with a fetch + <audio> element and keep the same state shape.
 */
export function useSpeech(text, lang = "en") {
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;
  const [speaking, setSpeaking] = useState(false);
  const [paused, setPaused] = useState(false);
  const [charIndex, setCharIndex] = useState(0);
  const [hasVoiceForLang, setHasVoiceForLang] = useState(true);
  // Increments on every real Web Speech `boundary` event (word/sentence,
  // engine-dependent) — a genuine timing signal a waveform can react to,
  // distinct from charIndex which drives the transcript highlight.
  const [boundaryPulse, setBoundaryPulse] = useState(0);
  const utterRef = useRef(null);

  const pickVoice = useCallback(() => {
    const voices = window.speechSynthesis.getVoices();
    if (lang === "ar") {
      return voices.find((v) => /^ar\b|-ar|arabic/i.test(v.lang) || /arabic/i.test(v.name));
    }
    return (
      voices.find((v) => /en-US/i.test(v.lang) && /female|samantha|zira|aria/i.test(v.name)) ||
      voices.find((v) => /en/i.test(v.lang))
    );
  }, [lang]);

  const stop = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    setSpeaking(false);
    setPaused(false);
    setCharIndex(0);
    setBoundaryPulse(0);
  }, [supported]);

  const play = useCallback(() => {
    if (!supported || !text) return;
    window.speechSynthesis.cancel();

    const u = new SpeechSynthesisUtterance(text);
    u.rate = 0.98;
    u.pitch = 1.0;
    u.lang = lang === "ar" ? "ar-SA" : "en-US";
    const voice = pickVoice();
    if (voice) u.voice = voice;
    setHasVoiceForLang(lang === "ar" ? !!voice : true);

    u.onstart = () => {
      setSpeaking(true);
      setPaused(false);
    };
    u.onend = () => {
      setSpeaking(false);
      setPaused(false);
      setCharIndex(text.length);
    };
    u.onerror = () => {
      setSpeaking(false);
      setPaused(false);
    };
    u.onboundary = (e) => {
      if (typeof e.charIndex === "number") setCharIndex(e.charIndex);
      setBoundaryPulse((p) => p + 1);
    };

    utterRef.current = u;
    setCharIndex(0);
    window.speechSynthesis.speak(u);
  }, [supported, text, lang, pickVoice]);

  const pause = useCallback(() => {
    if (!supported) return;
    if (window.speechSynthesis.speaking && !window.speechSynthesis.paused) {
      window.speechSynthesis.pause();
      setPaused(true);
    }
  }, [supported]);

  const resume = useCallback(() => {
    if (!supported) return;
    if (window.speechSynthesis.paused) {
      window.speechSynthesis.resume();
      setPaused(false);
    }
  }, [supported]);

  useEffect(() => {
    if (!supported) return;
    const warm = () => window.speechSynthesis.getVoices();
    warm();
    window.speechSynthesis.addEventListener?.("voiceschanged", warm);
    return () => {
      window.speechSynthesis.removeEventListener?.("voiceschanged", warm);
      window.speechSynthesis.cancel();
    };
  }, [supported]);

  return {
    supported,
    speaking,
    paused,
    charIndex,
    boundaryPulse,
    hasVoiceForLang,
    play,
    pause,
    resume,
    stop,
  };
}
