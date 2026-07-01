import { useQuery } from '@tanstack/react-query';
import { FileText, Newspaper } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  financialService,
  type Announcement,
} from '@/services/financial-service';

const statusMap: Record<
  string,
  {
    label: string;
    variant: 'default' | 'secondary' | 'destructive' | 'outline';
  }
> = {
  pending: { label: '待下载', variant: 'outline' },
  downloaded: { label: '已下载', variant: 'secondary' },
  uploaded: { label: '已上传', variant: 'secondary' },
  parsed: { label: '已解析', variant: 'default' },
  failed: { label: '失败', variant: 'destructive' },
};

export default function AnnouncementsPage() {
  const { t } = useTranslation();
  const [stockCode, setStockCode] = useState<string>('');
  const [status, setStatus] = useState<string>('');
  const [search, setSearch] = useState('');

  const { data: stocks = [] } = useQuery({
    queryKey: ['financial-stocks'],
    queryFn: () => financialService.listStocks(),
  });

  const { data: announcements = [], isLoading } = useQuery({
    queryKey: ['financial-announcements', stockCode, status],
    queryFn: () =>
      financialService.listAnnouncements({
        stock_code: stockCode || undefined,
        status: status || undefined,
      }),
  });

  const filteredAnnouncements = announcements.filter((ann: Announcement) =>
    ann.title.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="size-full flex flex-col p-8">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Newspaper className="size-6" />
            {t('header.announcements')}
          </h1>
          <p className="text-text-secondary mt-1">
            查看已同步的公告列表及其解析状态。
          </p>
        </div>
      </header>

      <Card className="flex-1 overflow-hidden flex flex-col">
        <CardHeader>
          <CardTitle>公告列表</CardTitle>
          <CardDescription>
            共 {filteredAnnouncements.length} 份公告
          </CardDescription>
        </CardHeader>
        <CardContent className="flex-1 overflow-auto">
          <div className="flex items-center gap-4 mb-4">
            <div className="grid gap-2 flex-1">
              <Label htmlFor="search">搜索公告</Label>
              <Input
                id="search"
                placeholder="输入公告标题关键词"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="grid gap-2 w-48">
              <Label>股票筛选</Label>
              <Select value={stockCode} onValueChange={setStockCode}>
                <SelectTrigger>
                  <SelectValue placeholder="全部股票" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">全部股票</SelectItem>
                  {stocks.map((stock) => (
                    <SelectItem key={stock.code} value={stock.code}>
                      {stock.code} {stock.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2 w-40">
              <Label>状态筛选</Label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger>
                  <SelectValue placeholder="全部状态" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">全部状态</SelectItem>
                  <SelectItem value="pending">待下载</SelectItem>
                  <SelectItem value="downloaded">已下载</SelectItem>
                  <SelectItem value="uploaded">已上传</SelectItem>
                  <SelectItem value="parsed">已解析</SelectItem>
                  <SelectItem value="failed">失败</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {isLoading ? (
            <div className="py-20 text-center text-text-secondary">
              加载中...
            </div>
          ) : filteredAnnouncements.length === 0 ? (
            <div className="py-20 text-center text-text-secondary">
              暂无公告，请先在「股票管理」中添加股票并同步。
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>股票</TableHead>
                  <TableHead>公告标题</TableHead>
                  <TableHead>发布时间</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredAnnouncements.map((ann: Announcement) => (
                  <TableRow key={ann.id}>
                    <TableCell className="font-medium">
                      {ann.stock_code}
                      {ann.stock_name && (
                        <span className="text-text-secondary ml-1">
                          ({ann.stock_name})
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <FileText className="size-4 text-text-secondary" />
                        <span className="max-w-md truncate" title={ann.title}>
                          {ann.title}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      {ann.announcement_time
                        ? new Date(ann.announcement_time).toLocaleDateString(
                            'zh-CN',
                          )
                        : '-'}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={statusMap[ann.status]?.variant || 'outline'}
                      >
                        {statusMap[ann.status]?.label || ann.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {ann.url && (
                        <Button variant="ghost" size="sm" asChild>
                          <a
                            href={ann.url}
                            target="_blank"
                            rel="noreferrer noopener"
                          >
                            查看原文
                          </a>
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
