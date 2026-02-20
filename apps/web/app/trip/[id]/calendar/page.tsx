import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { redirect, notFound } from "next/navigation";
import { PrismaClient } from "@prisma/client";
import CalendarClient from "./CalendarClient";

const prisma = new PrismaClient();

interface PageProps {
  params: { id: string };
}

export async function generateMetadata({ params }: PageProps) {
  return {
    title: `Calendar — Overplanned`,
  };
}

export default async function CalendarPage({ params }: PageProps) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    redirect("/auth/signin");
  }

  const userId = (session.user as { id: string }).id;

  // Fetch trip with member check
  const trip = await prisma.trip.findFirst({
    where: {
      id: params.id,
      members: {
        some: { userId },
      },
    },
    include: {
      slots: {
        include: {
          activityNode: {
            select: {
              id: true,
              name: true,
              address: true,
              latitude: true,
              longitude: true,
              category: true,
            },
          },
        },
        orderBy: [{ dayNumber: "asc" }, { sortOrder: "asc" }],
      },
    },
  });

  if (!trip) {
    notFound();
  }

  return (
    <CalendarClient
      trip={{
        id: trip.id,
        destination: trip.destination,
        city: trip.city,
        timezone: trip.timezone,
        startDate: trip.startDate.toISOString(),
        endDate: trip.endDate.toISOString(),
        slots: trip.slots.map((s) => ({
          id: s.id,
          dayNumber: s.dayNumber,
          sortOrder: s.sortOrder,
          slotType: s.slotType,
          status: s.status,
          startTime: s.startTime?.toISOString() ?? null,
          endTime: s.endTime?.toISOString() ?? null,
          durationMinutes: s.durationMinutes,
          isLocked: s.isLocked,
          activityNode: s.activityNode
            ? {
                id: s.activityNode.id,
                name: s.activityNode.name,
                address: s.activityNode.address,
                latitude: s.activityNode.latitude,
                longitude: s.activityNode.longitude,
                category: s.activityNode.category,
              }
            : null,
        })),
      }}
    />
  );
}
