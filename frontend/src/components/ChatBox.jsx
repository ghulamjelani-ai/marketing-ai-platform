import { Fragment, useEffect, useRef, useState } from "react";
import apiClient from "../api/client";
import { deleteConversation, listConversations } from "../api/activity";
import { useAuth } from "../context/useAuth";
import { auth } from "../firebase/firebase";
import PostAssistant from "./PostAssistant";
import RichText from "./RichText";
import VoiceButton from "./VoiceButton";
import { parsePlan } from "../utils/parsePlan";
import { canSpeak, speak, stopSpeaking } from "../utils/speech";
import "../dashboard.css";
import "../automation.css";

export default function ChatBox({ assistant }) {
  const { user } = useAuth();

  const [conversationId, setConversationId] = useState(
    localStorage.getItem("marketing_ai_conversation_id") || null
  );

  const [messages, setMessages] = useState([
    {
      role: "ai",
      text: "Hello! Tell me about your business, services, target audience, and location. I will create a marketing plan and social media post ideas for you.",
    },
  ]);

  const scrollRef = useRef(null);
  // A conversation this chat just created is already on screen; it is not reloaded.
  const createdHereRef = useRef(null);

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  // Replies to spoken messages are read aloud unless the user turns it off.
  const [voiceReplies, setVoiceReplies] = useState(() => {
    try {
      return localStorage.getItem("marketing_ai_voice_replies") !== "off";
    } catch {
      return true;
    }
  });
  const [speaking, setSpeaking] = useState(null); // the message being read aloud

  const [showHistory, setShowHistory] = useState(false);
  const [conversations, setConversations] = useState([]);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [historyError, setHistoryError] = useState("");

  const getFirebaseToken = async () => {
    const currentUser = auth.currentUser;

    if (!currentUser) {
      throw new Error("Firebase user not found. Please login again.");
    }

    return await currentUser.getIdToken();
  };

  useEffect(() => {
    if (!conversationId || conversationId === createdHereRef.current) return undefined;

    let cancelled = false;

    (async () => {
      try {
        const token = await getFirebaseToken();

        const response = await apiClient.get(`/chat/history/${conversationId}`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (cancelled) return;

        setMessages(
          response.data.messages.map((msg) => ({
            role: msg.role,
            text: msg.content,
          })),
        );
      } catch (error) {
        if (cancelled) return;

        console.error("Load history error:", error);
        localStorage.removeItem("marketing_ai_conversation_id");
        setConversationId(null);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  useEffect(() => stopSpeaking, []);

  function readAloud(message) {
    if (speak(message.text, () => setSpeaking((current) => (current === message ? null : current)))) {
      setSpeaking(message);
    }
  }

  function listen(message) {
    if (speaking === message) {
      stopSpeaking();
      setSpeaking(null);
    } else {
      readAloud(message);
    }
  }

  function toggleVoiceReplies() {
    const next = !voiceReplies;
    setVoiceReplies(next);

    if (!next) {
      stopSpeaking();
      setSpeaking(null);
    }

    try {
      localStorage.setItem("marketing_ai_voice_replies", next ? "on" : "off");
    } catch {
      // storage can be blocked; the choice still applies for this visit
    }
  }

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  // spokenText is set when the message came from the mic.
  const handleSend = async (spokenText) => {
    const spoken = typeof spokenText === "string";
    const userText = spoken ? spokenText : input;

    if (!userText.trim() || loading) return;

    stopSpeaking();
    setSpeaking(null);

    const userMessage = {
      role: "user",
      text: userText,
      voice: spoken,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const token = await getFirebaseToken();

      const response = await apiClient.post(
        "/chat/plan",
        {
          message: userText,
          business_name: user?.businessName || user?.name || "My Business",
          industry: "",
          conversation_id: conversationId,
        },
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (response.data.conversation_id) {
        createdHereRef.current = response.data.conversation_id;
        setConversationId(response.data.conversation_id);
        localStorage.setItem(
          "marketing_ai_conversation_id",
          response.data.conversation_id
        );
      }

      const aiMessage = {
        role: "ai",
        text: response.data.reply,
      };

      setMessages((prev) => [...prev, aiMessage]);

      if (spoken && voiceReplies) {
        readAloud(aiMessage);
      }
    } catch (error) {
      console.error("Chat API Error:", error);

      const detail = error.response?.data?.detail;

      let errorText = "Sorry, something went wrong.";

      if (typeof detail === "string") {
        errorText = detail;
      } else if (detail?.error) {
        errorText = detail.error;
      } else if (detail?.message) {
        errorText = detail.message;
      } else if (error.message) {
        errorText = error.message;
      }

      const errorMessage = {
        role: "ai",
        text: `Backend Error:\n${errorText}`,
      };

      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const openHistory = async () => {
    if (showHistory) {
      setShowHistory(false);
      return;
    }

    setShowHistory(true);
    setHistoryBusy(true);
    setHistoryError("");

    try {
      const data = await listConversations();
      setConversations(data.conversations || []);
    } catch (error) {
      setHistoryError(error.message || "Could not load your chats.");
    } finally {
      setHistoryBusy(false);
    }
  };

  const openConversation = (id) => {
    createdHereRef.current = null;
    localStorage.setItem("marketing_ai_conversation_id", id);
    setConversationId(id);
    setShowHistory(false);
  };

  const removeConversation = async (id) => {
    if (!window.confirm("Delete this conversation?")) return;

    try {
      await deleteConversation(id);
      setConversations((list) => list.filter((item) => item.id !== id));

      if (id === conversationId) {
        startNewChat();
      }
    } catch (error) {
      setHistoryError(error.message || "Could not delete the chat.");
    }
  };

  const startNewChat = () => {
    stopSpeaking();
    setSpeaking(null);
    localStorage.removeItem("marketing_ai_conversation_id");
    setConversationId(null);

    setMessages([
      {
        role: "ai",
        text: "New chat started. Tell me about your business and I will create a fresh marketing plan.",
      },
    ]);
  };

  // The latest AI reply that contains ready-to-use posts gets the guided steps.
  let assistIndex = -1;
  let assistPlan = null;

  if (assistant) {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === "user") continue;

      const plan = parsePlan(messages[i].text);

      if (plan.posts.length > 0) {
        assistIndex = i;
        assistPlan = plan;
        break;
      }
    }
  }

  return (
    <div className="dx-card dx-rise dx-d1 rounded-3xl p-5 h-full flex flex-col">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h3 className="dx-title text-2xl flex items-center gap-3">
            AI Marketing Assistant
            <span className="dx-online" title="Online" />
          </h3>

          <p className="text-sm dx-faint mt-1">
            Chat with AI to generate your business plan, captions, post ideas
            and campaign strategy.
          </p>
        </div>

        <div className="flex flex-wrap justify-end gap-2">
          {canSpeak() && (
            <button
              onClick={toggleVoiceReplies}
              className="dx-btn-ghost dx-btn-sm"
              aria-pressed={voiceReplies}
              aria-label={voiceReplies ? "Voice replies on" : "Voice replies off"}
              title="Read replies aloud when you speak to the assistant"
            >
              {voiceReplies ? "🔊 Voice on" : "🔇 Voice off"}
            </button>
          )}

          <button onClick={openHistory} className="dx-btn-ghost dx-btn-sm">
            History
          </button>

          <button onClick={startNewChat} className="dx-btn-ghost dx-btn-sm">
            New Chat
          </button>
        </div>
      </div>

      {showHistory && (
        <div className="dx-history">
          <p className="dx-history-title">Your earlier chats</p>

          {historyBusy && <p className="dx-history-empty">Loading...</p>}

          {historyError && <p className="dx-history-empty">{historyError}</p>}

          {!historyBusy && !historyError && conversations.length === 0 && (
            <p className="dx-history-empty">
              No saved chats yet. Your conversations are saved automatically.
            </p>
          )}

          {conversations.map((item) => (
            <div
              key={item.id}
              className={`dx-history-item ${
                item.id === conversationId ? "on" : ""
              }`}
            >
              <button
                type="button"
                className="dx-history-open"
                onClick={() => openConversation(item.id)}
              >
                <span className="dx-history-name">{item.title}</span>
                <span className="dx-history-date">
                  {new Date(item.updated_at + "Z").toLocaleString([], {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </button>

              <button
                type="button"
                className="dx-history-delete"
                onClick={() => removeConversation(item.id)}
                aria-label="Delete conversation"
                title="Delete conversation"
              >
                &times;
              </button>
            </div>
          ))}
        </div>
      )}

      <div
        ref={scrollRef}
        className="dx-chat-scroll flex-1 min-h-[420px] max-h-[520px] overflow-y-auto space-y-4 pr-2"
      >
        {messages.map((msg, index) => (
          <Fragment key={index}>
            <div
              className={`dx-msg flex ${
                msg.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              {msg.role !== "user" && <div className="dx-ai-avatar">✦</div>}

              <div
                className={`max-w-[85%] px-4 py-3 text-sm leading-relaxed ${
                  msg.role === "user" ? "dx-bubble-user" : "dx-bubble-ai"
                }`}
              >
                {msg.role === "user" ? (
                  <>
                    {msg.voice && <span className="dx-said" aria-label="Spoken">🎙️ </span>}
                    {msg.text}
                  </>
                ) : (
                  <RichText text={msg.text} />
                )}

                {msg.role !== "user" && index > 0 && canSpeak() && (
                  <button
                    type="button"
                    className={`dx-listen ${speaking === msg ? "on" : ""}`}
                    onClick={() => listen(msg)}
                    aria-label={speaking === msg ? "Stop reading aloud" : "Read this reply aloud"}
                  >
                    {speaking === msg ? "■ Stop" : "🔊 Listen"}
                  </button>
                )}
              </div>
            </div>

            {index === assistIndex && (
              <div className="dx-msg pl-9">
                <PostAssistant
                  key={`${assistIndex}-${assistant.publishedCount}`}
                  plan={assistPlan}
                  assistant={assistant}
                />
              </div>
            )}
          </Fragment>
        ))}

        {loading && (
          <div className="dx-msg flex justify-start">
            <div className="dx-ai-avatar">✦</div>
            <div className="dx-bubble-ai max-w-[85%] px-4 py-3 text-sm flex items-center gap-3">
              <div className="dx-steps">
                {[
                  "Understanding your business…",
                  "Building marketing strategy…",
                  "Writing post ideas…",
                ].map((step, i) => (
                  <div
                    key={step}
                    className="dx-step"
                    style={{ "--sd": `${i * 1.4}s` }}
                  >
                    <span className="dx-step-spin" />
                    {step}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="mt-5 flex gap-3">
        <input
          placeholder="Example: I run a bakery in Lahore and want more customers..."
          className="dx-input flex-1"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSend();
          }}
        />

        <VoiceButton onText={(text) => handleSend(text)} disabled={loading} label="Speak to the assistant" />

        <button onClick={() => handleSend()} disabled={loading} className="dx-btn">
          {loading ? "Wait..." : "Send"}
        </button>
      </div>
    </div>
  );
}
