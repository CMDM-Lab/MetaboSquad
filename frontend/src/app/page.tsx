import Content from "@/src/modules/home/Content";
import { Suspense } from "react";

export default function HomePage() {
  return (
      <Suspense fallback={<div>Loading...</div>}>
        <Content /> {/* With Suspense, Content doesn't need its own if (isLoading) check. */}
      </Suspense>
  );
}