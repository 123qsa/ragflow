import axios from 'axios';

const FINANCIAL_API_BASE = '/api/financial';

const financialApi = axios.create({
  baseURL: FINANCIAL_API_BASE,
  timeout: 120000,
});

export interface Stock {
  code: string;
  name: string;
  exchange: string;
  market: string;
  kb_id?: string;
  chat_id?: string;
  created_at?: string;
  updated_at?: string;
  announcement_count: number;
  sync_progress?: SyncProgress | null;
}

export interface SyncProgress {
  stage: string;
  current?: number;
  total?: number;
  total_anns: number;
  new_anns: number;
}

export interface Announcement {
  id?: number;
  stock_code: string;
  stock_name?: string;
  title: string;
  announcement_time: string;
  category?: string;
  url: string;
  status: string;
  created_at?: string;
}

export interface SyncLog {
  id?: number;
  stock_code: string;
  started_at: string;
  ended_at?: string;
  total_count: number;
  new_count: number;
  failed_count: number;
  message?: string;
}

export interface CreateStockRequest {
  code: string;
  name?: string;
  embedding_model?: string;
  llm_id?: string;
}

export interface SyncRequest {
  start_date?: string;
  end_date?: string;
  category?: string;
}

class FinancialService {
  async getHealth() {
    const { data } = await financialApi.get('/api/health');
    return data;
  }

  async listStocks(): Promise<Stock[]> {
    const { data } = await financialApi.get('/api/stocks');
    return data;
  }

  async createStock(payload: CreateStockRequest): Promise<Stock> {
    const { data } = await financialApi.post('/api/stocks', payload);
    return data;
  }

  async deleteStock(code: string): Promise<void> {
    await financialApi.delete(`/api/stocks/${code}`);
  }

  async syncStock(code: string, payload: SyncRequest = {}): Promise<any> {
    const { data } = await financialApi.post(
      `/api/stocks/${code}/sync`,
      payload,
    );
    return data;
  }

  async syncAll(payload: SyncRequest = {}): Promise<any[]> {
    const { data } = await financialApi.post('/api/stocks/sync-all', payload);
    return data;
  }

  async listAnnouncements(params?: {
    stock_code?: string;
    status?: string;
  }): Promise<Announcement[]> {
    const { data } = await financialApi.get('/api/announcements', { params });
    return data;
  }

  async listSyncLogs(params?: {
    stock_code?: string;
    limit?: number;
  }): Promise<SyncLog[]> {
    const { data } = await financialApi.get('/api/sync-logs', { params });
    return data;
  }

  async listCategories(): Promise<string[]> {
    const { data } = await financialApi.get('/api/categories');
    return data;
  }
}

export const financialService = new FinancialService();
