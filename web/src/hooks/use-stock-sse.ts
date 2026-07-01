import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

/**
 * 监听后端 SSE 推送，数据有更新时自动刷新前端查询。
 *
 * 用法：在股票列表页调用 useStockSSE()
 * 后端有 sync_progress / source_updated 事件时自动 invalidate 相关 query。
 */
export function useStockSSE() {
  const queryClient = useQueryClient();
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const es = new EventSource('/api/financial/api/events/*');
    eventSourceRef.current = es;

    es.addEventListener('sync_progress', () => {
      queryClient.invalidateQueries({ queryKey: ['financial-stocks'] });
    });

    es.addEventListener('source_updated', () => {
      queryClient.invalidateQueries({ queryKey: ['financial-stocks'] });
    });

    es.addEventListener('connected', () => {
      // 连接建立
    });

    es.onerror = () => {
      // SSE 断开后 5 秒自动重连（EventSource 默认行为）
    };

    return () => {
      es.close();
    };
  }, [queryClient]);
}
