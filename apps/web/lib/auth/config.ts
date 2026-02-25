import type { NextAuthOptions } from "next-auth";
import type { SubscriptionTier, SystemRole } from "@prisma/client";
import GoogleProvider from "next-auth/providers/google";
import { PrismaAdapter } from "@auth/prisma-adapter";
import { prisma } from "@/lib/prisma";

export const authOptions: NextAuthOptions = {
  adapter: PrismaAdapter(prisma) as any,
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  ],
  session: {
    strategy: "jwt",
    maxAge: 30 * 24 * 60 * 60, // 30 days
  },
  callbacks: {
    async redirect({ url, baseUrl }) {
      // Allow relative URLs
      if (url.startsWith("/")) return `${baseUrl}${url}`;
      // Allow same-origin URLs
      try {
        if (new URL(url).origin === baseUrl) return url;
      } catch {
        // Invalid URL, fall through to default
      }
      // Default to base
      return baseUrl;
    },
    async signIn({ user, account, profile }) {
      // First-time Google login - create User with beta tier
      if (account?.provider === "google" && profile?.email) {
        const existingUser = await prisma.user.findUnique({
          where: { email: profile.email },
        });

        if (!existingUser) {
          // User will be created by adapter with default subscriptionTier: beta
          // as defined in schema.prisma
          return true;
        }

        // Existing user - update googleId if not set
        if (!existingUser.googleId && profile.sub) {
          await prisma.user.update({
            where: { id: existingUser.id },
            data: { googleId: profile.sub },
          });
        }
      }

      return true;
    },
    async jwt({ token, user }) {
      if (user) {
        // First sign-in — encode user data into JWT
        token.id = user.id;
        token.subscriptionTier = user.subscriptionTier;
        token.systemRole = user.systemRole;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.id = token.id as string;
        session.user.subscriptionTier = token.subscriptionTier as SubscriptionTier;
        session.user.systemRole = token.systemRole as SystemRole;
      }
      return session;
    },
  },
  events: {
    async createUser({ user }) {
      // User created by adapter - ensure subscriptionTier is set to beta
      // (should already be default, but being explicit)
      if (!user.subscriptionTier) {
        await prisma.user.update({
          where: { id: user.id },
          data: { subscriptionTier: "beta" },
        });
      }
    },
  },
  pages: {
    signIn: "/auth/signin",
    error: "/auth/error",
  },
};
