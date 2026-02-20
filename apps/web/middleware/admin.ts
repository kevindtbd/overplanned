import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { authOptions } from '@/lib/auth';

/**
 * Admin middleware: Enforces systemRole = 'admin' for all /admin routes.
 * Returns 403 Forbidden if user is not authenticated or lacks admin role.
 */
export async function adminMiddleware(req: NextRequest) {
  const session = await getServerSession(authOptions);

  if (!session?.user) {
    return NextResponse.json(
      { error: 'Unauthorized', message: 'Authentication required' },
      { status: 401 }
    );
  }

  // Check systemRole (assumes User type has systemRole field)
  const systemRole = (session.user as any).systemRole;

  if (systemRole !== 'admin') {
    return NextResponse.json(
      { error: 'Forbidden', message: 'Admin access required' },
      { status: 403 }
    );
  }

  // User is admin, allow request to proceed
  return NextResponse.next();
}

/**
 * Utility to check admin role in server components/actions
 */
export async function requireAdmin() {
  const session = await getServerSession(authOptions);

  if (!session?.user) {
    throw new Error('Authentication required');
  }

  const systemRole = (session.user as any).systemRole;

  if (systemRole !== 'admin') {
    throw new Error('Admin access required');
  }

  return session.user;
}
