import { ScrollArea } from '@/components/ui/scroll-area';
import { IReference, IReferenceChunk } from '@/interfaces/database/chat';
import { cn } from '@/lib/utils';
import { BookOpen, ChevronRight, FileText } from 'lucide-react';
import { useMemo, useState } from 'react';

interface ReferencePanelProps {
  reference: IReference | null;
}

export function ReferencePanel({ reference }: ReferencePanelProps) {
  const [expandedChunkId, setExpandedChunkId] = useState<string | null>(null);

  // Group chunks by document
  const grouped = useMemo(() => {
    if (!reference || !reference.chunks?.length) return [];

    const docMap = new Map<
      string,
      { docName: string; chunks: IReferenceChunk[] }
    >();
    reference.chunks.forEach((chunk) => {
      const key = chunk.document_id;
      if (!docMap.has(key)) {
        docMap.set(key, { docName: chunk.document_name, chunks: [] });
      }
      docMap.get(key)!.chunks.push(chunk);
    });

    return Array.from(docMap.entries()).map(([docId, { docName, chunks }]) => ({
      docId,
      docName,
      chunks,
    }));
  }, [reference]);

  const totalChunks = reference?.chunks?.length ?? 0;

  return (
    <section className="w-80 shrink-0 border-l border-border-button flex flex-col bg-bg-base">
      <header className="h-14 px-4 flex items-center gap-2 border-b border-border-button shrink-0">
        <BookOpen className="size-4 text-text-secondary" />
        <span className="text-sm font-medium">信息源</span>
        {totalChunks > 0 && (
          <span className="text-xs text-text-secondary">
            ({totalChunks} 条引用)
          </span>
        )}
      </header>

      <ScrollArea className="flex-1 min-h-0">
        {!reference || totalChunks === 0 ? (
          <div className="p-4 text-center text-text-secondary text-sm">
            请在左侧发送消息，对话完成后这里将展示引用的信息源。
          </div>
        ) : (
          <div className="p-2 space-y-3">
            {grouped.map(({ docId, docName, chunks }) => (
              <div key={docId}>
                <div className="flex items-center gap-1.5 px-3 py-1.5">
                  <FileText className="size-3.5 text-text-secondary shrink-0" />
                  <span className="text-xs font-medium text-text-secondary truncate">
                    {docName}
                  </span>
                  <span className="text-[10px] text-text-secondary/60 shrink-0">
                    {chunks.length} 条
                  </span>
                </div>

                {chunks.map((chunk) => {
                  const isExpanded = expandedChunkId === chunk.id;
                  return (
                    <div
                      key={chunk.id}
                      className={cn(
                        'mx-2 rounded-md transition-colors',
                        isExpanded && 'bg-bg-secondary',
                      )}
                    >
                      <button
                        className="w-full px-3 py-2 text-left hover:bg-bg-secondary/50 rounded-md group"
                        onClick={() =>
                          setExpandedChunkId(isExpanded ? null : chunk.id)
                        }
                      >
                        <div className="flex items-start gap-2">
                          <ChevronRight
                            className={cn(
                              'size-3.5 text-text-secondary shrink-0 mt-0.5 transition-transform',
                              isExpanded && 'rotate-90',
                            )}
                          />
                          <div className="min-w-0 flex-1">
                            <p className="text-xs leading-relaxed line-clamp-2 text-text-primary">
                              {chunk.content || '(无文本内容)'}
                            </p>
                            <div className="flex items-center gap-2 mt-1">
                              <span className="text-[10px] text-text-secondary">
                                相似度: {(chunk.similarity * 100).toFixed(1)}%
                              </span>
                              {chunk.doc_type && (
                                <span className="text-[10px] text-text-secondary/60 uppercase">
                                  {chunk.doc_type}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </button>

                      {isExpanded && (
                        <div className="px-3 pb-3">
                          <div className="text-xs text-text-secondary bg-bg-base rounded p-2 max-h-48 overflow-auto whitespace-pre-wrap break-all">
                            {chunk.content || '(无文本内容)'}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        )}
      </ScrollArea>
    </section>
  );
}
