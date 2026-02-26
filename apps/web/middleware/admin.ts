import { getServerSession } from 'next-auth/next';
import { authOptions } from '@/lib/auth/config';

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
