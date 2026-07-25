import { useState, useRef, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import ChatPanel from "./components/ChatPanel";
import Sidebar from "./components/Sidebar";
import Terminal from "./components/Terminal";

export interface Message {
  role: "user" | "assistant" | "system";
  content: string;
}

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"chat" | "terminal">("chat");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = { role: "user", content: input.trim() };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await invoke<string>("send_message", {
        message: userMessage.content,
      });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: response },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${error}` },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="app">
      <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="main">
        {activeTab === "chat" ? (
          <ChatPanel
            messages={messages}
            input={input}
            isLoading={isLoading}
            onInputChange={setInput}
            onSend={sendMessage}
            onKeyDown={handleKeyDown}
            messagesEndRef={messagesEndRef}
          />
        ) : (
          <Terminal />
        )}
      </main>
    </div>
  );
}

export default App;
