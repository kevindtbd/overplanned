import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { redirect } from "next/navigation";
import DiscoverClient from "./DiscoverClient";

export const metadata = {
  title: "Discover — Overplanned",
  description: "Find places worth going to.",
};

export default async function DiscoverPage({
  searchParams,
}: {
  searchParams: { city?: string; tripId?: string; day?: string };
}) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    redirect("/auth/signin?callbackUrl=/discover");
  }

  const city = searchParams.city ?? "Bend";
  const tripId = searchParams.tripId ?? undefined;
  const day = searchParams.day ? Number(searchParams.day) : undefined;

  return (
    <DiscoverClient
      userId={(session.user as { id: string }).id}
      city={city}
      tripId={tripId}
      day={day}
    />
  );
}
