interface SidebarProps {
  activeTab: "chat" | "terminal";
  onTabChange: (tab: "chat" | "terminal") => void;
}

export default function Sidebar({ activeTab, onTabChange }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">🐙</div>
      <nav className="sidebar-nav">
        <button
          className={`sidebar-btn ${activeTab === "chat" ? "active" : ""}`}
          onClick={() => onTabChange("chat")}
          title="Chat"
        >
          💬
        </button>
        <button
          className={`sidebar-btn ${activeTab === "terminal" ? "active" : ""}`}
          onClick={() => onTabChange("terminal")}
          title="Terminal"
        >
          ⌨️
        </button>
      </nav>
      <div className="sidebar-bottom">
        <button className="sidebar-btn" title="Settings">
          ⚙️
        </button>
      </div>
    </aside>
  );
}
