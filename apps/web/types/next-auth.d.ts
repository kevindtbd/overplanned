import type { SubscriptionTier, SystemRole } from "@prisma/client";
import "next-auth";

declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      email: string;
      name?: string | null;
      image?: string | null;
      subscriptionTier: SubscriptionTier;
      systemRole: SystemRole;
    };
  }

  interface User {
    id: string;
    email: string;
    name?: string | null;
    image?: string | null;
    subscriptionTier: SubscriptionTier;
    systemRole: SystemRole;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    id: string;
    subscriptionTier: SubscriptionTier;
    systemRole: SystemRole;
  }
}
