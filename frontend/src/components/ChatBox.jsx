import { Fragment, useEffect, useRef, useState } from "react";
import apiClient from "../api/client";
import { deleteConversation, listConversations } from "../api/activity";
import { useAuth } from "../context/AuthContext";
import { auth } from "../firebase/firebase";
import PostAssistant from "./PostAssistant";
import RichText from "./RichText";
import { parsePlan } from "../utils/parsePlan";
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

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

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

  const loadHistory = async () => {
    if (!conversationId) return;

    try {
      const token = await getFirebaseToken();

      const response = await apiClient.get(`/chat/history/${conversationId}`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      const loadedMessages = response.data.messages.map((msg) => ({
        role: msg.role,
        text: msg.content,
      }));

      setMessages(loadedMessages);
    } catch (error) {
      console.error("Load history error:", error);
      localStorage.removeItem("marketing_ai_conversation_id");
      setConversationId(null);
    }
  };

  useEffect(() => {
    loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userText = input;

    const userMessage = {
      role: "user",
      text: userText,
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

        <div className="flex gap-2">
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
                {msg.role === "user" ? msg.text : <RichText text={msg.text} />}
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

        <button onClick={handleSend} disabled={loading} className="dx-btn">
          {loading ? "Wait..." : "Send"}
        </button>
      </div>
    </div>
  );
}
