import ChatWindow from "@/src/modules/chatpage/ChatWindow";
import { Suspense } from "react";


export default async function ChatPage() {

  return (
    <Suspense
      fallback={
        <div className="h-[calc(100vh-8rem)] flex items-center justify-center">
          Loading Chat...
        </div>
      }
    >
      <ChatWindow />
    </Suspense>
  );
}