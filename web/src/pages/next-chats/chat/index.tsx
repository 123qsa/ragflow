import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { MessageType } from '@/constants/chat';
import {
  useFetchChat,
  useFetchSessionList,
  useFetchSessionManually,
  useGetChatSearchParams,
} from '@/hooks/use-chat-request';
import {
  IClientConversation,
  IMessage,
  IReference,
} from '@/interfaces/database/chat';
import { cn } from '@/lib/utils';
import { Routes } from '@/routes';
import { generateConversationId } from '@/utils/chat';
import { useNavigate } from 'react-router';
import { useChatUrlParams } from '../hooks/use-chat-url';

import { isEmpty } from 'lodash';
import {
  LucideArrowBigLeft,
  LucideArrowLeft,
  LucideArrowUpRight,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useHandleClickConversationCard } from '../hooks/use-click-card';
import { ChatSettings } from './app-settings/chat-settings';
import { MultipleChatBox } from './chat-box/next-multiple-chat-box';
import { SingleChatBox } from './chat-box/single-chat-box';
import { ReferencePanel } from './reference-panel';
import { Sessions } from './sessions';
import { useAddChatBox } from './use-add-box';
import { useSwitchDebugMode } from './use-switch-debug-mode';

export default function Chat() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [currentConversation, setCurrentConversation] =
    useState<IClientConversation>({} as IClientConversation);
  const [liveMessages, setLiveMessages] = useState<IMessage[]>([]);

  const { fetchSessionManually } = useFetchSessionManually();

  const { handleConversationCardClick, controller, stopOutputMessage } =
    useHandleClickConversationCard();

  const { isDebugMode, switchDebugMode } = useSwitchDebugMode();
  const { removeChatBox, addChatBox, chatBoxIds, hasSingleChatBox } =
    useAddChatBox(isDebugMode);

  const { conversationId, isNew } = useGetChatSearchParams();
  const { setConversationBoth } = useChatUrlParams();

  const { data: dialogList } = useFetchSessionList();
  const { data: currentDialog } = useFetchChat();
  const hasAutoNavigated = useRef(false);

  const currentConversationName = useMemo(() => {
    return (
      dialogList.find((x) => x.id === conversationId)?.name ||
      t('chat.newConversation')
    );
  }, [conversationId, dialogList, t]);

  const stockInfo = useMemo(() => {
    // Chat 名称格式: {code}_{name}_问答助手
    const name = currentDialog?.name || currentConversationName;
    if (!name) return null;
    const match = name.match(/^([0-9]{6})_(.+?)_问答助手$/);
    if (match) {
      return { code: match[1], name: match[2] };
    }
    return null;
  }, [currentDialog, currentConversationName]);

  const isStockChat = stockInfo !== null;

  // 从当前对话中找到最新一条 AI 消息的引用信息源
  // 优先使用 liveMessages（实时），回退到 currentConversation.messages（持久化）
  const latestReference = useMemo<IReference | null>(() => {
    const messages =
      liveMessages.length > 0 ? liveMessages : currentConversation?.messages;
    if (!messages?.length) return null;
    const assistantMessages = messages.filter(
      (m) =>
        m.role === MessageType.Assistant &&
        !m.content?.startsWith('**ERROR**:'),
    );
    if (!assistantMessages.length) return null;
    const lastMsg = assistantMessages[assistantMessages.length - 1];
    return lastMsg.reference ?? null;
  }, [liveMessages, currentConversation?.messages]);

  const fetchConversation: typeof handleConversationCardClick = useCallback(
    async (conversationId, isNew) => {
      if (conversationId && !isNew) {
        const conversation = await fetchSessionManually(conversationId);
        if (!isEmpty(conversation)) {
          setCurrentConversation(conversation);
        }
      }
    },
    [fetchSessionManually],
  );

  const handleSessionClick: typeof handleConversationCardClick = useCallback(
    (conversationId, isNew) => {
      handleConversationCardClick(conversationId, isNew);
      fetchConversation(conversationId, isNew);
    },
    [fetchConversation, handleConversationCardClick],
  );

  useEffect(() => {
    fetchConversation(conversationId, isNew === 'true');
  }, [conversationId, isNew, fetchConversation]);

  useEffect(() => {
    if (hasAutoNavigated.current) return;
    if (conversationId || isNew === 'true' || !dialogList) return;
    hasAutoNavigated.current = true;
    if (dialogList.length > 0) {
      // 一只股票有且仅有一个对话：股票聊天始终使用第一个 session
      const target = isStockChat
        ? dialogList[0]
        : [...dialogList].sort(
            (a, b) => (b.create_time || 0) - (a.create_time || 0),
          )[0];
      setConversationBoth(target.id, '');
    } else {
      setConversationBoth(generateConversationId(), 'true');
    }
  }, [conversationId, isNew, dialogList, setConversationBoth, isStockChat]);

  if (isDebugMode) {
    return (
      <section
        className="pt-5 pb-14 h-[100vh] flex flex-col"
        data-testid="chat-detail-multimodel-root"
      >
        <header className="px-10 pb-5">
          <div className="mb-5">
            <Button
              variant="outline"
              onClick={switchDebugMode}
              data-testid="chat-detail-multimodel-back"
            >
              <LucideArrowBigLeft />
              <span>{t('common.back')}</span>
            </Button>
          </div>

          <span className="text-2xl">
            {t('chat.multipleModels')} ({chatBoxIds.length}/3)
          </span>
        </header>

        <MultipleChatBox
          chatBoxIds={chatBoxIds}
          controller={controller}
          removeChatBox={removeChatBox}
          addChatBox={addChatBox}
          stopOutputMessage={stopOutputMessage}
          conversation={currentConversation}
        ></MultipleChatBox>
      </section>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-bg-base">
      <header className="h-14 px-5 flex items-center justify-between border-b border-border-button shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(Routes.Root)}
            data-testid="chat-back-to-stocks"
          >
            <LucideArrowLeft className="size-4" />
            返回股票列表
          </Button>
          <div className="h-6 w-px bg-border-button" />
          <div className="flex flex-col min-w-0">
            <span className="text-sm font-medium truncate">
              {stockInfo
                ? `${stockInfo.code} ${stockInfo.name} - 问答助手`
                : currentConversationName}
            </span>
            <span className="text-xs text-text-secondary truncate">
              基于该股票已同步的公告进行问答
            </span>
          </div>
        </div>
      </header>

      <section
        className="flex-1 min-h-0 flex flex-col"
        data-testid="chat-detail"
      >
        <article className="flex flex-1 min-h-0">
          {!isStockChat && (
            <Sessions
              handleConversationCardClick={handleSessionClick}
            ></Sessions>
          )}

          <Card className="flex-1 min-w-0 bg-transparent border-none shadow-none h-full">
            <CardContent className="flex p-0 h-full">
              <Card className="flex flex-col flex-1 bg-transparent min-w-0">
                {!isStockChat && (
                  <CardHeader
                    className={cn('p-5', {
                      'border-b-0.5 border-border-button': hasSingleChatBox,
                    })}
                  >
                    <CardTitle className="flex justify-between items-center text-base gap-2">
                      <div className="flex items-center gap-2 truncate">
                        <span className="truncate">
                          {currentConversationName}
                        </span>
                      </div>

                      <Button
                        variant="ghost"
                        onClick={switchDebugMode}
                        data-testid="chat-detail-multimodel-toggle"
                      >
                        <LucideArrowUpRight />
                        {t('chat.multipleModels')}
                      </Button>
                    </CardTitle>
                  </CardHeader>
                )}
                <CardContent className="flex-1 p-0 min-h-0">
                  <SingleChatBox
                    controller={controller}
                    stopOutputMessage={stopOutputMessage}
                    conversation={currentConversation}
                    onMessagesChange={setLiveMessages}
                  />
                </CardContent>
              </Card>

              {isStockChat ? (
                <ReferencePanel reference={latestReference} />
              ) : (
                <ChatSettings
                  hasSingleChatBox={hasSingleChatBox}
                ></ChatSettings>
              )}
            </CardContent>
          </Card>
        </article>
      </section>
    </div>
  );
}
