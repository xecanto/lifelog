import { redirect } from "next/navigation";

export default function RootPage() {
  // Landing on the capture box meant the first thing you saw was a blank
  // field. Today's agenda is what's actually waiting for you; capture is one
  // tap away from every page.
  redirect("/agenda");
}
