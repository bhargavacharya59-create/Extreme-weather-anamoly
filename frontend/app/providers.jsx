'use client';
import { AuthProvider } from '@/lib/auth';
import { Toaster } from '@/components/ui';

export default function Providers({ children }) {
  return (
    <AuthProvider>
      {children}
      <Toaster />
    </AuthProvider>
  );
}
