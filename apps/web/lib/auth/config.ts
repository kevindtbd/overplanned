import type { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import { PrismaAdapter } from "@auth/prisma-adapter";
import { PrismaClient } from "@prisma/client";
import { enforceConcurrentSessionLimit } from "./session";

const prisma = new PrismaClient();

export const authOptions: NextAuthOptions = {
  adapter: PrismaAdapter(prisma) as any,
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  ],
  session: {
    strategy: "database",
    maxAge: 30 * 24 * 60 * 60, // 30 days
    updateAge: 7 * 24 * 60 * 60, // 7 days (idle timeout)
  },
  callbacks: {
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
    async session({ session, user }) {
      if (session.user) {
        session.user.id = user.id;
        session.user.subscriptionTier = user.subscriptionTier;
        session.user.systemRole = user.systemRole;
      }

      // Update lastActiveAt on every session load
      await prisma.user.update({
        where: { id: user.id },
        data: { lastActiveAt: new Date() },
      });

      // Enforce concurrent session limit (max 5 sessions per user)
      await enforceConcurrentSessionLimit(user.id);

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
