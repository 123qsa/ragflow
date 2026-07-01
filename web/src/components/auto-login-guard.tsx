import { useAutoLogin } from '@/hooks/use-auto-login';
import { Loader2 } from 'lucide-react';

interface AutoLoginGuardProps {
  children: React.ReactNode;
}

export function AutoLoginGuard({ children }: AutoLoginGuardProps) {
  const { isReady } = useAutoLogin();

  if (!isReady) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <span className="text-sm text-text-secondary">加载中...</span>
      </div>
    );
  }

  return <>{children}</>;
}
