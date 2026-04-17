import { redirect } from 'next/navigation';

// Root (/) always redirects to /dashboard.
// AuthGuard on /dashboard will handle the login redirect if not authenticated.
export default function RootPage() {
  redirect('/dashboard');
}
