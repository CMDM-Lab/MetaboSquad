import Content from "@/src/modules/chatpage/Content";
import { Suspense } from "react";

export default function NewChatPage() {
  return (
      <Suspense fallback={<div>Loading...</div>}>
        <Content />
      </Suspense>
  );
}
