/**
 * Unit tests: AdminLayout component.
 *
 * Verifies:
 * - Admin auth guard redirects non-admin users
 * - Navigation links render all admin surfaces
 * - Admin panel structure renders correctly
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock next-auth
const mockRequireAdmin = vi.fn();
vi.mock('@/middleware/admin', () => ({
  requireAdmin: () => mockRequireAdmin(),
}));

// Mock next/navigation
const mockRedirect = vi.fn();
vi.mock('next/navigation', () => ({
  redirect: (path: string) => {
    mockRedirect(path);
    throw new Error('REDIRECT'); // redirect throws in Next.js server components
  },
}));

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AdminLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Auth Guard', () => {
    it('redirects to home when requireAdmin throws', async () => {
      mockRequireAdmin.mockRejectedValue(new Error('Admin access required'));

      // Dynamically import to get fresh module
      const { default: AdminLayout } = await import(
        '../../app/admin/layout'
      );

      try {
        // AdminLayout is an async server component
        await AdminLayout({ children: null });
      } catch (e: any) {
        // redirect throws
      }

      expect(mockRedirect).toHaveBeenCalledWith('/');
    });

    it('renders children when user is admin', async () => {
      mockRequireAdmin.mockResolvedValue({
        email: 'admin@overplanned.app',
        systemRole: 'admin',
      });

      const { default: AdminLayout } = await import(
        '../../app/admin/layout'
      );

      // Server component returns JSX
      const result = await AdminLayout({
        children: 'test-content' as any,
      });

      // Result should be a React element (not a redirect)
      expect(result).toBeTruthy();
      expect(mockRedirect).not.toHaveBeenCalled();
    });
  });

  describe('Navigation Links', () => {
    it('includes all expected admin surfaces', async () => {
      mockRequireAdmin.mockResolvedValue({
        email: 'admin@overplanned.app',
        systemRole: 'admin',
      });

      const { default: AdminLayout } = await import(
        '../../app/admin/layout'
      );

      const result = await AdminLayout({ children: null });

      // Convert to string representation to check link hrefs
      const rendered = JSON.stringify(result);

      const expectedPaths = [
        '/admin/users',
        '/admin/trips',
        '/admin/activity-nodes',
        '/admin/audit-log',
        '/admin/sources',
        '/admin/seeding',
        '/admin/models',
        '/admin/pipeline',
        '/admin/safety',
      ];

      for (const path of expectedPaths) {
        expect(rendered).toContain(path);
      }
    });

    it('includes back to app link', async () => {
      mockRequireAdmin.mockResolvedValue({
        email: 'admin@overplanned.app',
        systemRole: 'admin',
      });

      const { default: AdminLayout } = await import(
        '../../app/admin/layout'
      );

      const result = await AdminLayout({ children: null });
      const rendered = JSON.stringify(result);
      expect(rendered).toContain('Back to App');
    });
  });
});
