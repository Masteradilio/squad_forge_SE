import { useState, useRef, type ChangeEvent } from 'react';
import { apiClient, type Project } from '../api/client';
import { Card } from './Card';
import { Button } from './Button';

interface Message {
  id: string;
  sender: 'PO' | 'Scrum Master';
  text: string;
  timestamp: string;
  attachments?: string[];
}

interface POChatViewProps {
  activeProject: Project | null;
  onNavigateToTab: (tab: string) => void;
  onProjectCreated?: (project: Project) => void;
}

export function POChatView({ activeProject, onNavigateToTab, onProjectCreated }: POChatViewProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      sender: 'Scrum Master',
      text: 'Olá Product Owner! Sou o **Scrum Master** do LocalForge OS. Envie o seu `PRD.md` e arquivos visuais/schemas de interface (`.png`, `.jpg`, `.svg`) abaixo para iniciarmos a Etapa 2 de criação do Backlog da Squad.',
      timestamp: new Date().toLocaleTimeString(),
    },
  ]);
  const [inputText, setInputText] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setSelectedFiles(Array.from(e.target.files));
    }
  };

  const handleSendMessage = async () => {
    if (!inputText.trim() && selectedFiles.length === 0) return;

    const fileNames = selectedFiles.map((f) => f.name);
    const poMsg: Message = {
      id: Date.now().toString(),
      sender: 'PO',
      text: inputText,
      timestamp: new Date().toLocaleTimeString(),
      attachments: fileNames.length > 0 ? fileNames : undefined,
    };

    setMessages((prev) => [...prev, poMsg]);
    setInputText('');
    setSelectedFiles([]);
    setIsProcessing(true);

    try {
      const chatRes = await apiClient.poChat(
        inputText,
        fileNames,
        activeProject?.id
      );

      if (chatRes.project && onProjectCreated) {
        onProjectCreated(chatRes.project);
      }

      const smResponse: Message = {
        id: (Date.now() + 1).toString(),
        sender: 'Scrum Master',
        text: chatRes.reply,
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages((prev) => [...prev, smResponse]);
    } catch (err: any) {
      const errorResponse: Message = {
        id: (Date.now() + 1).toString(),
        sender: 'Scrum Master',
        text: `Erro ao comunicar com a Squad/OmniRoute: ${err.message || err}`,
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages((prev) => [...prev, errorResponse]);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', height: 'calc(100vh - 120px)' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 800, margin: 0 }}>💬 Mission Control & PO Chat</h1>
          <p style={{ color: 'var(--text-secondary)', margin: '4px 0 0 0', fontSize: '14px' }}>
            Ponto de contato direto entre o Product Owner humano e o Scrum Master (Etapa 1 e Etapa 2).
          </p>
        </div>
        <Button variant="primary" onClick={() => onNavigateToTab('kanban')}>
          📋 Ir para Kanban Board →
        </Button>
      </div>

      {/* Main Chat Box */}
      <Card style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '20px', overflow: 'hidden' }}>
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px', paddingRight: '8px' }}>
          {messages.map((msg) => (
            <div
              key={msg.id}
              style={{
                alignSelf: msg.sender === 'PO' ? 'flex-end' : 'flex-start',
                maxWidth: '75%',
                backgroundColor: msg.sender === 'PO' ? '#2563eb' : '#1f2937',
                color: '#fff',
                padding: '14px 18px',
                borderRadius: msg.sender === 'PO' ? '16px 16px 2px 16px' : '16px 16px 16px 2px',
                boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
              }}
            >
              <div style={{ fontSize: '11px', opacity: 0.7, marginBottom: '4px', fontWeight: 700 }}>
                {msg.sender} • {msg.timestamp}
              </div>
              <div style={{ fontSize: '14px', lineHeight: '1.5', whiteSpace: 'pre-wrap' }}>
                {msg.text}
              </div>
              {msg.attachments && (
                <div style={{ marginTop: '10px', paddingTop: '8px', borderTop: '1px solid rgba(255,255,255,0.2)', fontSize: '12px' }}>
                  📎 Arquivos Anexados:
                  <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                    {msg.attachments.map((file, idx) => (
                      <li key={idx}>{file}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}
          {isProcessing && (
            <div style={{ alignSelf: 'flex-start', color: 'var(--text-muted)', fontSize: '13px', fontStyle: 'italic' }}>
              Scrum Master está analisando o PRD e gerando o backlog...
            </div>
          )}
        </div>

        {/* Selected Files Preview */}
        {selectedFiles.length > 0 && (
          <div style={{ padding: '8px 12px', backgroundColor: 'var(--bg-secondary)', borderRadius: '8px', marginBottom: '12px', fontSize: '12px' }}>
            📁 Arquivos selecionados para upload ({selectedFiles.length}):
            <div style={{ display: 'flex', gap: '8px', marginTop: '4px', flexWrap: 'wrap' }}>
              {selectedFiles.map((f, i) => (
                <span key={i} style={{ backgroundColor: 'var(--bg-input)', padding: '2px 8px', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                  {f.name} ({(f.size / 1024).toFixed(1)} KB)
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Input Bar */}
        <div style={{ display: 'flex', gap: '12px', marginTop: '12px' }}>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            multiple
            accept=".md,.txt,.png,.jpg,.jpeg,.svg"
            style={{ display: 'none' }}
          />
          <Button variant="secondary" onClick={() => fileInputRef.current?.click()} title="Anexar PRD.md ou imagens de UI">
            📎 Anexar Arquivos
          </Button>
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
            placeholder="Digite suas instruções ou solicitações para o Scrum Master..."
            style={{
              flex: 1,
              padding: '12px 16px',
              borderRadius: '8px',
              backgroundColor: 'var(--bg-input)',
              border: '1px solid var(--border-color)',
              color: 'var(--text-primary)',
              fontSize: '14px',
            }}
          />
          <Button variant="primary" onClick={handleSendMessage} disabled={isProcessing}>
            Enviar 🚀
          </Button>
        </div>
      </Card>
    </div>
  );
}
