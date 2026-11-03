import { afterEach, describe, expect, it, vi } from "vitest";
import { canSpeak, speak, speakableText, stopSpeaking } from "../speech";

describe("speakableText", () => {
  it("drops markdown, links and hashtags", () => {
    const text = "**Caption:** Fresh bread daily!\nHashtags: #Bakery #Lahore\nOrder at https://example.com/order";
    expect(speakableText(text)).toBe("Caption: Fresh bread daily!. Hashtags:. Order at");
  });

  it("reads list items without bullets", () => {
    expect(speakableText("- one\n- two")).toBe("one. two");
  });

  it("cuts long answers at a sentence and points to the screen", () => {
    const long = "This is a sentence. ".repeat(60);
    const spoken = speakableText(long, 200);

    expect(spoken.length).toBeLessThan(260);
    expect(spoken.endsWith("sentence. The full answer is on your screen.")).toBe(true);
  });

  it("keeps Urdu text", () => {
    expect(speakableText("عید کی خاص پیشکش #عید")).toBe("عید کی خاص پیشکش");
  });

  it("handles empty input", () => {
    expect(speakableText("")).toBe("");
    expect(speakableText(null)).toBe("");
  });
});

describe("speak", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function stubSynth(voices = []) {
    const synth = { speak: vi.fn(), cancel: vi.fn(), getVoices: () => voices };
    vi.stubGlobal("speechSynthesis", synth);
    vi.stubGlobal(
      "SpeechSynthesisUtterance",
      class {
        constructor(text) {
          this.text = text;
        }
      },
    );
    return synth;
  }

  it("says nothing when the browser cannot speak", () => {
    expect(canSpeak()).toBe(false);
    expect(speak("hello")).toBe(false);
    expect(() => stopSpeaking()).not.toThrow();
  });

  it("stops the previous reply and speaks English with an English voice", () => {
    const english = { name: "Google US English", lang: "en-US" };
    const synth = stubSynth([{ name: "Other", lang: "fr-FR" }, english]);

    expect(speak("Hello there")).toBe(true);

    const utterance = synth.speak.mock.calls[0][0];
    expect(synth.cancel).toHaveBeenCalled();
    expect(utterance.text).toBe("Hello there");
    expect(utterance.lang).toBe("en-US");
    expect(utterance.voice).toBe(english);
  });

  it("uses an Urdu voice for Urdu text", () => {
    const synth = stubSynth([{ name: "Urdu", lang: "ur-PK" }]);

    speak("عید مبارک");

    expect(synth.speak.mock.calls[0][0].lang).toBe("ur-PK");
  });

  it("does not speak an empty reply", () => {
    const synth = stubSynth();

    expect(speak("#onlyhashtags")).toBe(false);
    expect(synth.speak).not.toHaveBeenCalled();
  });
});
