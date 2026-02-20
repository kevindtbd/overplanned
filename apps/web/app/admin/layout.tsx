import { ReactNode } from 'react';
import { requireAdmin } from '@/middleware/admin';
import { redirect } from 'next/navigation';

interface AdminLayoutProps {
  children: ReactNode;
}

/**
 * Admin layout: Separate from user app shell.
 * Enforces admin access before rendering any admin pages.
 */
export default async function AdminLayout({ children }: AdminLayoutProps) {
  try {
    await requireAdmin();
  } catch (error) {
    // Redirect non-admin users to home
    redirect('/');
  }

  return (
    <div className="min-h-screen bg-warm-background">
      {/* Admin navigation */}
      <nav className="border-b border-warm-border bg-warm-surface">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between">
            <div className="flex items-center gap-8">
              <h1 className="font-display text-xl text-gray-900">
                Admin Panel
              </h1>
              <div className="flex gap-4 font-mono text-sm">
                <a
                  href="/admin/users"
                  className="text-gray-600 hover:text-terracotta transition-colors"
                >
                  Users
                </a>
                <a
                  href="/admin/trips"
                  className="text-gray-600 hover:text-terracotta transition-colors"
                >
                  Trips
                </a>
                <a
                  href="/admin/activity-nodes"
                  className="text-gray-600 hover:text-terracotta transition-colors"
                >
                  Activity Nodes
                </a>
                <a
                  href="/admin/audit-log"
                  className="text-gray-600 hover:text-terracotta transition-colors"
                >
                  Audit Log
                </a>
                <a
                  href="/admin/sources"
                  className="text-gray-600 hover:text-terracotta transition-colors"
                >
                  Sources
                </a>
                <a
                  href="/admin/seeding"
                  className="text-gray-600 hover:text-terracotta transition-colors"
                >
                  Seeding
                </a>
                <a
                  href="/admin/models"
                  className="text-gray-600 hover:text-terracotta transition-colors"
                >
                  Model Registry
                </a>
                <a
                  href="/admin/pipeline"
                  className="text-gray-600 hover:text-terracotta transition-colors"
                >
                  Pipeline Health
                </a>
                <a
                  href="/admin/safety"
                  className="text-gray-600 hover:text-terracotta transition-colors"
                >
                  Safety
                </a>
              </div>
            </div>
            <a
              href="/"
              className="font-mono text-sm text-gray-600 hover:text-terracotta transition-colors"
            >
              ← Back to App
            </a>
          </div>
        </div>
      </nav>

      {/* Main admin content */}
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {children}
      </main>
    </div>
  );
}
