import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  MessageSquare,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  TrendingUp,
} from 'lucide-react';
import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useToast } from '@/components/hooks/use-toast';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useStockSSE } from '@/hooks/use-stock-sse';
import { Routes } from '@/routes';
import { financialService, type Stock } from '@/services/financial-service';
import { generateConversationId } from '@/utils/chat';
import request from '@/utils/next-request';
import { useNavigate } from 'react-router';

export default function StocksPage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newStockCode, setNewStockCode] = useState('');
  const [newStockName, setNewStockName] = useState('');
  const [newLlmId, setNewLlmId] = useState('deepseek-chat@DeepSeek');
  const [syncingCode, setSyncingCode] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const { data: stocks = [], isLoading } = useQuery({
    queryKey: ['financial-stocks'],
    queryFn: () => financialService.listStocks(),
  });

  // SSE 推送：数据有更新时自动刷新，无需定时轮询
  useStockSSE();

  const filteredStocks = useMemo(() => {
    const q = searchQuery.trim();
    if (!q) return stocks;
    return stocks.filter(
      (s) =>
        s.code.toLowerCase().includes(q.toLowerCase()) ||
        s.name.toLowerCase().includes(q.toLowerCase()),
    );
  }, [stocks, searchQuery]);

  const createMutation = useMutation({
    mutationFn: (payload: { code: string; name?: string; llm_id?: string }) =>
      financialService.createStock(payload),
    onSuccess: () => {
      setIsCreateOpen(false);
      setNewStockCode('');
      setNewStockName('');
      setNewLlmId('glm-4-flash@ZHIPU-AI');
      toast({ title: '添加成功', description: '已开始自动同步公告...' });
      queryClient.invalidateQueries({ queryKey: ['financial-stocks'] });
    },
    onError: (error: any) => {
      const message =
        error?.response?.data?.detail || error.message || '添加失败';
      toast({
        title: '添加失败',
        description: message,
        variant: 'destructive',
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (code: string) => financialService.deleteStock(code),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['financial-stocks'] });
    },
  });

  const syncMutation = useMutation({
    mutationFn: (code: string) => financialService.syncStock(code),
    onMutate: (code) => setSyncingCode(code),
    onSettled: () => setSyncingCode(null),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['financial-stocks'] });
      queryClient.invalidateQueries({ queryKey: ['financial-announcements'] });
      queryClient.invalidateQueries({ queryKey: ['financial-sync-logs'] });
      toast({ title: '同步完成', description: '公告同步已完成' });
    },
    onError: (error: any) => {
      const message =
        error?.response?.data?.detail || error.message || '同步失败';
      toast({
        title: '同步失败',
        description: message,
        variant: 'destructive',
      });
    },
  });

  const syncAllMutation = useMutation({
    mutationFn: () => financialService.syncAll(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['financial-stocks'] });
      queryClient.invalidateQueries({ queryKey: ['financial-announcements'] });
      queryClient.invalidateQueries({ queryKey: ['financial-sync-logs'] });
    },
  });

  const stageLabel: Record<string, string> = {
    fetching: '获取公告列表...',
    filtering: '比对已有公告...',
    downloading: '下载公告PDF',
    parsing: '解析入库',
    creating_chat: '创建问答助手...',
  };

  const handleCreate = () => {
    if (!newStockCode.trim()) return;
    createMutation.mutate({
      code: newStockCode.trim(),
      name: newStockName.trim() || undefined,
      llm_id: newLlmId.trim() || undefined,
    });
  };

  const openStockChat = async (stock: Stock) => {
    if (!stock.chat_id) {
      toast({
        title: '请先同步股票',
        description: '该股票尚未创建问答助手',
        variant: 'destructive',
      });
      return;
    }
    try {
      const res = await request.get(`/api/v1/chats/${stock.chat_id}/sessions`);
      const sessions = (res.data?.data || []) as Array<{
        id: string;
        create_time?: number;
      }>;
      // 一只股票有且仅有一个对话：始终使用唯一的 session
      if (sessions.length > 0) {
        navigate(
          `${Routes.Chat}/${stock.chat_id}?conversationId=${sessions[0].id}`,
        );
      } else {
        const conversationId = generateConversationId();
        navigate(
          `${Routes.Chat}/${stock.chat_id}?conversationId=${conversationId}&isNew=true`,
        );
      }
    } catch (error: any) {
      toast({
        title: '打开助手失败',
        description: error?.message || '无法加载历史会话',
        variant: 'destructive',
      });
    }
  };

  return (
    <div className="size-full flex flex-col p-8">
      <header className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <TrendingUp className="size-6" />
            {t('header.stocks')}
          </h1>
          <p className="text-text-secondary mt-1">
            管理已接入的股票，每只股自动同步公告并创建独立的问答助手。
          </p>
        </div>
        <div className="flex-1 max-w-md">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-text-secondary" />
            <Input
              placeholder="搜索股票代码或名称..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => syncAllMutation.mutate()}
            disabled={syncAllMutation.isPending || stocks.length === 0}
          >
            <RefreshCw
              className={`size-4 mr-1 ${syncAllMutation.isPending ? 'animate-spin' : ''}`}
            />
            同步全部
          </Button>
          <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="size-4 mr-1" />
                添加股票
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>添加股票</DialogTitle>
                <DialogDescription>
                  输入股票代码，系统将自动创建知识库和问答助手。
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="stockCode">股票代码或名称</Label>
                  <Input
                    id="stockCode"
                    placeholder="例如：000001 或 平安银行"
                    value={newStockCode}
                    onChange={(e) => setNewStockCode(e.target.value)}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="stockName">股票名称（可选）</Label>
                  <Input
                    id="stockName"
                    placeholder="例如：平安银行"
                    value={newStockName}
                    onChange={(e) => setNewStockName(e.target.value)}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="llmId">LLM 模型</Label>
                  <Input
                    id="llmId"
                    placeholder="例如：deepseek-chat@DeepSeek"
                    value={newLlmId}
                    onChange={(e) => setNewLlmId(e.target.value)}
                  />
                  <p className="text-xs text-text-secondary">
                    默认使用 DeepSeek；如需更换，请确保模型已在「设置 → Model
                    Providers」中配置
                  </p>
                </div>
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setIsCreateOpen(false)}
                >
                  取消
                </Button>
                <Button
                  onClick={handleCreate}
                  disabled={createMutation.isPending || !newStockCode.trim()}
                >
                  {createMutation.isPending ? '创建中...' : '确认'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </header>

      <div className="flex-1 flex gap-4 overflow-hidden">
        <Card className="flex-1 flex flex-col overflow-hidden">
          <CardHeader>
            <CardTitle>股票列表</CardTitle>
            <CardDescription>
              共 {filteredStocks.length} / {stocks.length} 只股票
            </CardDescription>
          </CardHeader>
          <CardContent className="flex-1 overflow-auto">
            {isLoading ? (
              <div className="py-20 text-center text-text-secondary">
                加载中...
              </div>
            ) : !stocks || stocks.length === 0 ? (
              <div className="py-20 text-center text-text-secondary">
                暂无股票，请点击右上角「添加股票」。
              </div>
            ) : filteredStocks.length === 0 ? (
              <div className="py-20 text-center text-text-secondary">
                没有匹配的股票。
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>股票代码</TableHead>
                    <TableHead>股票名称</TableHead>
                    <TableHead>交易所</TableHead>
                    <TableHead>公告数量</TableHead>
                    <TableHead>最后更新</TableHead>
                    <TableHead className="text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredStocks.map((stock: Stock) => (
                    <TableRow
                      key={stock.code}
                      className={`${stock.chat_id ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'}`}
                      onClick={() => {
                        if (stock.chat_id) openStockChat(stock);
                      }}
                    >
                      <TableCell className="font-medium">
                        {stock.code}
                      </TableCell>
                      <TableCell>{stock.name}</TableCell>
                      <TableCell>{stock.exchange?.toUpperCase()}</TableCell>
                      <TableCell>
                        {stock.sync_progress ? (
                          <div className="space-y-1">
                            <div className="flex items-center gap-1.5">
                              <RefreshCw className="size-3 animate-spin text-primary" />
                              <span className="text-xs text-primary">
                                {stageLabel[stock.sync_progress.stage] ||
                                  stock.sync_progress.stage}
                              </span>
                            </div>
                            {stock.sync_progress.current != null &&
                              stock.sync_progress.total > 0 && (
                                <div className="w-full h-1 bg-bg-secondary rounded-full overflow-hidden">
                                  <div
                                    className="h-full bg-primary rounded-full transition-all duration-500"
                                    style={{
                                      width: `${Math.round((stock.sync_progress.current / stock.sync_progress.total) * 100)}%`,
                                    }}
                                  />
                                </div>
                              )}
                            <span className="text-[10px] text-text-secondary">
                              {stock.sync_progress.new_anns > 0
                                ? `+${stock.sync_progress.new_anns} 份新公告`
                                : `${stock.sync_progress.total_anns} 份远程`}
                            </span>
                          </div>
                        ) : (
                          stock.announcement_count
                        )}
                      </TableCell>
                      <TableCell>
                        {stock.updated_at
                          ? new Date(stock.updated_at).toLocaleString('zh-CN')
                          : '-'}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(
                              e: React.MouseEvent<HTMLButtonElement>,
                            ) => {
                              e.stopPropagation();
                              openStockChat(stock);
                            }}
                            disabled={!stock.chat_id}
                            title={
                              stock.chat_id ? '打开问答助手' : '请先同步股票'
                            }
                          >
                            <MessageSquare
                              className={`size-4 ${stock.chat_id ? 'text-primary' : 'text-text-disabled'}`}
                            />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(
                              e: React.MouseEvent<HTMLButtonElement>,
                            ) => {
                              e.stopPropagation();
                              syncMutation.mutate(stock.code);
                            }}
                            disabled={syncingCode === stock.code}
                          >
                            <RefreshCw
                              className={`size-4 ${syncingCode === stock.code ? 'animate-spin' : ''}`}
                            />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(
                              e: React.MouseEvent<HTMLButtonElement>,
                            ) => {
                              e.stopPropagation();
                              deleteMutation.mutate(stock.code);
                            }}
                            disabled={deleteMutation.isPending}
                          >
                            <Trash2 className="size-4 text-text-danger" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
