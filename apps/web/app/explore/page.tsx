import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { redirect } from "next/navigation";
import ExploreClient from "./ExploreClient";

export const metadata = {
  title: "Explore — Overplanned",
  description: "Find your next destination by vibe, not by search bar.",
};

export default async function ExplorePage() {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    redirect("/auth/signin?callbackUrl=/explore");
  }

  return <ExploreClient userId={(session.user as { id: string }).id} />;
}
