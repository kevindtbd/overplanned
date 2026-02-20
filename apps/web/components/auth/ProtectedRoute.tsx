"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import type { ReactNode } from "react";
import { hasAccess } from "@/lib/auth/gates";

interface ProtectedRouteProps {
  children: ReactNode;
  requireAdmin?: boolean;
  fallback?: ReactNode;
}

/**
 * Client-side protected route wrapper
 * Redirects to signin if not authenticated or lacks access
 */
export function ProtectedRoute({
  children,
  requireAdmin = false,
  fallback = <div>Loading...</div>,
}: ProtectedRouteProps) {
  const { data: session, status } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (status === "loading") return;

    if (!session) {
      router.push("/auth/signin");
      return;
    }

    // Check access tier
    if (!hasAccess(session.user.subscriptionTier)) {
      router.push("/auth/signin");
      return;
    }

    // Check admin requirement
    if (requireAdmin && session.user.systemRole !== "admin") {
      router.push("/");
      return;
    }
  }, [session, status, requireAdmin, router]);

  if (status === "loading") {
    return <>{fallback}</>;
  }

  if (!session) {
    return null;
  }

  if (!hasAccess(session.user.subscriptionTier)) {
    return null;
  }

  if (requireAdmin && session.user.systemRole !== "admin") {
    return null;
  }

  return <>{children}</>;
}

/**
 * Higher-order component version for convenience
 */
export function withProtectedRoute<P extends object>(
  Component: React.ComponentType<P>,
  options?: {
    requireAdmin?: boolean;
    fallback?: ReactNode;
  }
) {
  return function ProtectedComponent(props: P) {
    return (
      <ProtectedRoute
        requireAdmin={options?.requireAdmin}
        fallback={options?.fallback}
      >
        <Component {...props} />
      </ProtectedRoute>
    );
  };
}
