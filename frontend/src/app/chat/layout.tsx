import Sidebar from "@/src/modules/chatpage/Sidebar";

// The chat shell: the conversation sidebar beside the routed
// page (`/chat` welcome screen or `/chat/[id]` thread).
export default function ChatLayout({ children }: { children: React.ReactNode }) {
    return (
        <div className="flex h-[calc(100vh-8rem)] overflow-hidden bg-bg">
        <Sidebar />

        <main className="flex-1 relative overflow-hidden">
          {children}
        </main>
      </div>
    );
  }