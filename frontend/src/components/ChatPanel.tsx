import type { RefObject } from "react";
import type { Message } from "../App";
import Markdown from "react-markdown";

interface ChatPanelProps {
  messages: Message[];
  input: string;
  isLoading: boolean;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  messagesEndRef: RefObject<HTMLDivElement | null>;
}

export default function ChatPanel({
  messages,
  input,
  isLoading,
  onInputChange,
  onSend,
  onKeyDown,
  messagesEndRef,
}: ChatPanelProps) {
  return (
    <div className="chat-panel">
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <h1>🐙 Octopus Agent</h1>
            <p>AI coding assistant with harness governance</p>
            <div className="chat-examples">
              <button onClick={() => onInputChange("Write a hello world in Python")}>
                Write a hello world in Python
              </button>
              <button onClick={() => onInputChange("Explain what harness governance means")}>
                Explain harness governance
              </button>
            </div>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`message message-${msg.role}`}>
            <div className="message-avatar">
              {msg.role === "user" ? "👤" : "🐙"}
            </div>
            <div className="message-content">
              <Markdown>{msg.content}</Markdown>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="message message-assistant">
            <div className="message-avatar">🐙</div>
            <div className="message-content loading">
              <span className="dot">.</span>
              <span className="dot">.</span>
              <span className="dot">.</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-area">
        <textarea
          className="chat-input"
          placeholder="Type a message... (Enter to send, Shift+Enter for newline)"
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
        />
        <button
          className="send-button"
          onClick={onSend}
          disabled={isLoading || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
