import { useCallback, useState, useEffect, useRef, type ChangeEvent } from 'react';
import {
  apiClient,
  type Project,
  type ChatFolder,
  type ChatSession,
  type ChatMessageItem,
} from '../api/client';
import { Card } from './Card';
import { Button } from './Button';
import { ResourceState } from './ResourceState';

export interface ChatMessage {
  id: string;
  sender: 'PO' | 'Scrum Master' | 'System';
  text: string;
  timestamp: string;
  attachments?: string[];
}

interface POChatViewProps {
  activeProject: Project | null;
  onNavigateToTab: (tab: string) => void;
  onSelectProject?: (projectId: number) => void;
}

export function POChatView({
  activeProject,
  onNavigateToTab,
  onSelectProject,
}: POChatViewProps) {
  // Sidebar State
  const [folders, setFolders] = useState<ChatFolder[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  
  // UI States
  const [expandedFolders, setExpandedFolders] = useState<Record<number, boolean>>({});
  const [editingFolderId, setEditingFolderId] = useState<number | null>(null);
  const [folderNameInput, setFolderNameInput] = useState('');
  const [editingSessionId, setEditingSessionId] = useState<number | null>(null);
  const [sessionTitleInput, setSessionTitleInput] = useState('');
  
  // Move Session Modal
  const [movingSession, setMovingSession] = useState<ChatSession | null>(null);
  const [targetFolderId, setTargetFolderId] = useState<number | 'none'>('none');

  // Input & Processing State
  const [inputText, setInputText] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [structureStatus, setStructureStatus] = useState<'loading' | 'ready' | 'empty' | 'error'>('loading');
  const [structureError, setStructureError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load Folders & Sessions from PostgreSQL API
  const loadChatStructure = async () => {
    setStructureStatus('loading');
    setStructureError(null);
    try {
      const [fData, sData] = await Promise.all([
        apiClient.fetchChatFolders(),
        apiClient.fetchChatSessions(),
      ]);
      setFolders(fData);
      
      // Sort sessions by ID or updated_at descending
      const sortedSessions = [...sData].sort((a, b) => {
        const timeA = a.updated_at ? new Date(a.updated_at).getTime() : a.id;
        const timeB = b.updated_at ? new Date(b.updated_at).getTime() : b.id;
        return timeB - timeA;
      });
      setSessions(sortedSessions);

      // Auto-expand all folders by default
      const initialExpanded: Record<number, boolean> = {};
      fData.forEach((f) => {
        initialExpanded[f.id] = true;
      });
      setExpandedFolders((prev) => ({ ...initialExpanded, ...prev }));

      // Select saved session or most recently updated session
      const savedIdStr = localStorage.getItem('localforge_active_session_id');
      const savedId = savedIdStr ? Number(savedIdStr) : null;

      if (savedId && sortedSessions.some((s) => s.id === savedId)) {
        setActiveSessionId(savedId);
      } else if (sortedSessions.length > 0) {
        setActiveSessionId(sortedSessions[0].id);
      } else if (sortedSessions.length === 0) {
        // Create initial session if none exists
        const newSess = await apiClient.createChatSession('Nova Conversa');
        setSessions([newSess]);
        setActiveSessionId(newSess.id);
        localStorage.setItem('localforge_active_session_id', String(newSess.id));
      }
      setStructureStatus('ready');
    } catch (err) {
      console.error('Failed to load chat structure:', err);
      setStructureStatus('error');
      setStructureError(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    // This effect subscribes to the remote chat structure; its async callback
    // updates local state after the request resolves.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadChatStructure();
  }, []);

  // Load Active Session Details (Full Message History)
  const loadSessionDetails = useCallback(async (sessionId: number) => {
    setLoadingHistory(true);
    setHistoryError(null);
    try {
      const details = await apiClient.fetchChatSessionDetails(sessionId);
      if (details.messages) {
        const formatted: ChatMessage[] = details.messages.map((m: ChatMessageItem) => ({
          id: m.id.toString(),
          sender: m.sender,
          text: m.text,
          timestamp: m.created_at
            ? new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            : new Date().toLocaleTimeString(),
          attachments: m.attachments,
        }));
        setMessages(formatted);
      }
      if (details.project_id && onSelectProject) {
        onSelectProject(details.project_id);
      }
    } catch (err) {
      console.error('Error loading session details:', err);
      setHistoryError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingHistory(false);
    }
  }, [onSelectProject]);

  useEffect(() => {
    if (activeSessionId) {
      localStorage.setItem('localforge_active_session_id', String(activeSessionId));
      // Session history is an external resource synchronized by this effect.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      void loadSessionDetails(activeSessionId);
    }
  }, [activeSessionId, loadSessionDetails]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isProcessing]);

  // Handler: Create New Folder
  const handleCreateFolder = async () => {
    const name = prompt('Digite o nome da nova pasta de projetos:', 'Novo Projeto');
    if (!name || !name.trim()) return;
    try {
      const newFolder = await apiClient.createChatFolder(name.trim(), 'folder');
      setFolders((prev) => [...prev, newFolder]);
      setExpandedFolders((prev) => ({ ...prev, [newFolder.id]: true }));
    } catch (err) {
      alert(`Falha ao criar pasta: ${err}`);
    }
  };

  // Handler: Create New Chat Session
  const handleCreateSession = async (folderId?: number | null) => {
    try {
      const newSession = await apiClient.createChatSession('Nova Conversa', folderId);
      setSessions((prev) => [newSession, ...prev]);
      setActiveSessionId(newSession.id);
    } catch (err) {
      alert(`Falha ao criar conversa: ${err}`);
    }
  };

  // Handler: Rename Folder
  const handleStartRenameFolder = (folder: ChatFolder) => {
    setEditingFolderId(folder.id);
    setFolderNameInput(folder.name);
  };

  const handleSaveFolderRename = async (folderId: number) => {
    if (!folderNameInput.trim()) return setEditingFolderId(null);
    try {
      const updated = await apiClient.updateChatFolder(folderId, { name: folderNameInput.trim() });
      setFolders((prev) => prev.map((f) => (f.id === folderId ? updated : f)));
    } catch (err) {
      alert(`Falha ao renomear pasta: ${err}`);
    } finally {
      setEditingFolderId(null);
    }
  };

  // Handler: Delete Folder
  const handleDeleteFolder = async (folderId: number) => {
    if (!confirm('Deseja excluir esta pasta? As conversas contidas nela serão movidas para Conversas Soltas.')) return;
    try {
      await apiClient.deleteChatFolder(folderId);
      setFolders((prev) => prev.filter((f) => f.id !== folderId));
      setSessions((prev) =>
        prev.map((s) => (s.folder_id === folderId ? { ...s, folder_id: null } : s))
      );
    } catch (err) {
      alert(`Falha ao excluir pasta: ${err}`);
    }
  };

  // Handler: Rename Session
  const handleStartRenameSession = (session: ChatSession) => {
    setEditingSessionId(session.id);
    setSessionTitleInput(session.title);
  };

  const handleSaveSessionRename = async (sessionId: number) => {
    if (!sessionTitleInput.trim()) return setEditingSessionId(null);
    try {
      const updated = await apiClient.updateChatSession(sessionId, { title: sessionTitleInput.trim() });
      setSessions((prev) => prev.map((s) => (s.id === sessionId ? { ...s, title: updated.title } : s)));
    } catch (err) {
      alert(`Falha ao renomear conversa: ${err}`);
    } finally {
      setEditingSessionId(null);
    }
  };

  // Handler: Move Session
  const handleOpenMoveModal = (session: ChatSession) => {
    setMovingSession(session);
    setTargetFolderId(session.folder_id ?? 'none');
  };

  const handleConfirmMoveSession = async () => {
    if (!movingSession) return;
    const newFolderId = targetFolderId === 'none' ? null : Number(targetFolderId);
    try {
      const updated = await apiClient.updateChatSession(movingSession.id, { folder_id: newFolderId });
      setSessions((prev) => prev.map((s) => (s.id === movingSession.id ? { ...s, folder_id: updated.folder_id } : s)));
      setMovingSession(null);
    } catch (err) {
      alert(`Falha ao mover conversa: ${err}`);
    }
  };

  // Handler: Delete Session
  const handleDeleteSession = async (sessionId: number) => {
    if (!confirm('Deseja realmente excluir esta conversa e todo o seu histórico?')) return;
    try {
      await apiClient.deleteChatSession(sessionId);
      const remaining = sessions.filter((s) => s.id !== sessionId);
      setSessions(remaining);
      if (activeSessionId === sessionId) {
        if (remaining.length > 0) {
          setActiveSessionId(remaining[0].id);
        } else {
          handleCreateSession();
        }
      }
    } catch (err) {
      alert(`Falha ao excluir conversa: ${err}`);
    }
  };

  // Handler: Send Message
  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setSelectedFiles(Array.from(e.target.files));
    }
  };

  const handleSend = async () => {
    if (!inputText.trim() && selectedFiles.length === 0) return;
    if (!activeSessionId) return;

    const userText = inputText;
    const filesList = selectedFiles.map((f) => f.name);
    setInputText('');
    setSelectedFiles([]);
    setIsProcessing(true);

    // Optimistic user message render
    const optimisticUserMsg: ChatMessage = {
      id: Date.now().toString(),
      sender: 'PO',
      text: userText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      attachments: filesList.length > 0 ? filesList : undefined,
    };
    setMessages((prev) => [...prev, optimisticUserMsg]);

    try {
      let prdPath: string | undefined;
      const prdFile = selectedFiles.find((file) => file.name.toLowerCase().endsWith('.md'));
      if (prdFile && activeProject) {
        const imageFile = selectedFiles.find((file) => /\.(png|jpe?g|webp|svg)$/i.test(file.name));
        const imageBase64 = imageFile
          ? await new Promise<string>((resolve, reject) => {
              const reader = new FileReader();
              reader.onload = () => resolve(String(reader.result));
              reader.onerror = () => reject(reader.error || new Error('Unable to read design image'));
              reader.readAsDataURL(imageFile);
            })
          : undefined;
        const intake = await apiClient.intakeProjectInputs({
          name: activeProject.name,
          root_path: activeProject.root_path,
          project_id: activeProject.id,
          prd_content: await prdFile.text(),
          design_image_name: imageFile?.name,
          design_image_base64: imageBase64,
        });
        prdPath = intake.prd_path;
      }
      const res = await apiClient.poScrumMasterChat(
        userText,
        filesList,
        activeProject?.id,
        activeSessionId,
        prdPath,
      );
      
      const smResponse: ChatMessage = {
        id: (Date.now() + 1).toString(),
        sender: 'Scrum Master',
        text: res.reply,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, smResponse]);

      // Update session title & list
      setSessions((prev) =>
        prev.map((s) =>
          s.id === activeSessionId
            ? {
                ...s,
                title: s.title === 'Nova Conversa' ? (userText.length > 25 ? userText.slice(0, 25) + '...' : userText) : s.title,
                project_id: res.project?.id ?? s.project_id,
              }
            : s
        )
      );

      if (res.project && onSelectProject) {
        onSelectProject(res.project.id);
      }
    } catch (err: unknown) {
      const errorText =
        typeof err === 'string'
          ? err
          : err instanceof Error
          ? err.message
          : JSON.stringify(err);
      const errorMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        sender: 'Scrum Master',
        text: `Erro ao comunicar com o Scrum Master: ${errorText}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsProcessing(false);
    }
  };

  const toggleFolder = (folderId: number) => {
    setExpandedFolders((prev) => ({ ...prev, [folderId]: !prev[folderId] }));
  };

  const unassignedSessions = sessions.filter((s) => !s.folder_id);
  const activeSession = sessions.find((s) => s.id === activeSessionId);

  return (
    <section data-testid="chat-view" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {structureStatus === 'loading' && (
        <ResourceState status="loading" title="Carregando conversas reais" message="Consultando pastas e sessões do backend." testId="chat-state-loading" />
      )}
      {structureStatus === 'error' && (
        <ResourceState status="error" title="Conversas indisponíveis" message={`A API de chat não respondeu. ${structureError ?? ''}`} testId="chat-state-error" />
      )}
      {structureStatus === 'empty' && (
        <ResourceState status="empty" title="Nenhuma conversa retornada" message="Crie uma sessão para iniciar uma conversa persistida." testId="chat-state-empty" />
      )}
      <div className="chat-layout" style={{ display: 'flex', gap: '16px', height: 'calc(100vh - 120px)', width: '100%' }}>
      {/* ---------------------------------------------------------------- */}
      {/* Inner Chat Sidebar (Pastas de Projetos & Conversas Soltas) */}
      {/* ---------------------------------------------------------------- */}
      <Card
        style={{
          width: '300px',
          display: 'flex',
          flexDirection: 'column',
          padding: '16px',
          backgroundColor: 'var(--bg-secondary)',
          borderRight: '1px solid var(--border-color)',
          overflowY: 'auto',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
          <h2 style={{ fontSize: '15px', fontWeight: 800, margin: 0, color: 'var(--text-primary)' }}>
            📁 Projetos & Conversas
          </h2>
          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              type="button"
              onClick={handleCreateFolder}
              title="Nova Pasta de Projeto"
              style={{
                backgroundColor: 'rgba(255,255,255,0.06)',
                border: '1px solid var(--border-color)',
                color: 'var(--text-primary)',
                padding: '4px 8px',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '12px',
              }}
            >
              📁+
            </button>
            <button
              type="button"
              onClick={() => handleCreateSession(null)}
              title="Nova Conversa Solta"
              style={{
                backgroundColor: '#2563eb',
                border: 'none',
                color: '#fff',
                padding: '4px 10px',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '12px',
                fontWeight: 700,
              }}
            >
              + Nova
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', flex: 1 }}>
          {/* Pastas de Projetos */}
          <div>
            <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '0.5px' }}>
              Pastas de Projetos ({folders.length})
            </div>

            {folders.map((folder) => {
              const folderSessions = sessions.filter((s) => s.folder_id === folder.id);
              const isExpanded = expandedFolders[folder.id] ?? true;

              return (
                <div key={folder.id} style={{ marginBottom: '8px' }}>
                  {/* Folder Header */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      backgroundColor: 'rgba(255,255,255,0.03)',
                      border: '1px solid var(--border-color)',
                      cursor: 'pointer',
                      fontSize: '13px',
                      fontWeight: 700,
                    }}
                    onClick={() => toggleFolder(folder.id)}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, overflow: 'hidden' }}>
                      <span>{isExpanded ? '📂' : '📁'}</span>
                      {editingFolderId === folder.id ? (
                        <input
                          type="text"
                          value={folderNameInput}
                          onChange={(e) => setFolderNameInput(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && handleSaveFolderRename(folder.id)}
                          onBlur={() => handleSaveFolderRename(folder.id)}
                          autoFocus
                          style={{
                            backgroundColor: 'var(--bg-input)',
                            border: '1px solid #3b82f6',
                            color: '#fff',
                            fontSize: '12px',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            width: '100%',
                          }}
                        />
                      ) : (
                        <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {folder.name}
                        </span>
                      )}
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }} onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        onClick={() => handleCreateSession(folder.id)}
                        title="Nova Conversa nesta pasta"
                        style={{ background: 'none', border: 'none', color: '#60a5fa', cursor: 'pointer', fontSize: '12px' }}
                      >
                        ➕
                      </button>
                      <button
                        type="button"
                        onClick={() => handleStartRenameFolder(folder)}
                        title="Renomear Pasta"
                        style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '11px' }}
                      >
                        ✏️
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteFolder(folder.id)}
                        title="Excluir Pasta"
                        style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: '11px' }}
                      >
                        🗑️
                      </button>
                    </div>
                  </div>

                  {/* Folder Sub-Sessions */}
                  {isExpanded && (
                    <div style={{ marginLeft: '12px', marginTop: '4px', display: 'flex', flexDirection: 'column', gap: '2px', borderLeft: '2px solid rgba(255,255,255,0.08)', paddingLeft: '8px' }}>
                      {folderSessions.map((session) => {
                        const isActive = session.id === activeSessionId;
                        return (
                          <div
                            key={session.id}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              padding: '6px 10px',
                              borderRadius: '6px',
                              backgroundColor: isActive ? '#2563eb' : 'transparent',
                              color: isActive ? '#fff' : 'var(--text-primary)',
                              cursor: 'pointer',
                              fontSize: '12px',
                            }}
                            onClick={() => setActiveSessionId(session.id)}
                          >
                            {editingSessionId === session.id ? (
                              <input
                                type="text"
                                value={sessionTitleInput}
                                onChange={(e) => setSessionTitleInput(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && handleSaveSessionRename(session.id)}
                                onBlur={() => handleSaveSessionRename(session.id)}
                                autoFocus
                                style={{
                                  backgroundColor: 'var(--bg-input)',
                                  border: '1px solid #60a5fa',
                                  color: '#fff',
                                  fontSize: '11px',
                                  padding: '2px 4px',
                                  borderRadius: '4px',
                                  width: '100%',
                                }}
                              />
                            ) : (
                              <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', flex: 1 }}>
                                💬 {session.title}
                              </span>
                            )}

                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }} onClick={(e) => e.stopPropagation()}>
                              <button
                                type="button"
                                onClick={() => handleStartRenameSession(session)}
                                title="Renomear Conversa"
                                style={{ background: 'none', border: 'none', color: isActive ? '#fff' : 'var(--text-muted)', cursor: 'pointer', fontSize: '10px' }}
                              >
                                ✏️
                              </button>
                              <button
                                type="button"
                                onClick={() => handleOpenMoveModal(session)}
                                title="Mover para outra Pasta"
                                style={{ background: 'none', border: 'none', color: isActive ? '#fff' : 'var(--text-muted)', cursor: 'pointer', fontSize: '10px' }}
                              >
                                📁
                              </button>
                              <button
                                type="button"
                                onClick={() => handleDeleteSession(session.id)}
                                title="Excluir Conversa"
                                style={{ background: 'none', border: 'none', color: isActive ? '#fff' : '#ef4444', cursor: 'pointer', fontSize: '10px' }}
                              >
                                🗑️
                              </button>
                            </div>
                          </div>
                        );
                      })}
                      {folderSessions.length === 0 && (
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)', padding: '4px 8px', fontStyle: 'italic' }}>
                          Nenhuma conversa nesta pasta
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Conversas Soltas (Unassigned Sessions) */}
          <div>
            <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '0.5px' }}>
              Conversas Soltas ({unassignedSessions.length})
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {unassignedSessions.map((session) => {
                const isActive = session.id === activeSessionId;
                return (
                  <div
                    key={session.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      backgroundColor: isActive ? '#2563eb' : 'rgba(255,255,255,0.03)',
                      color: isActive ? '#fff' : 'var(--text-primary)',
                      border: '1px solid var(--border-color)',
                      cursor: 'pointer',
                      fontSize: '12px',
                    }}
                    onClick={() => setActiveSessionId(session.id)}
                  >
                    {editingSessionId === session.id ? (
                      <input
                        type="text"
                        value={sessionTitleInput}
                        onChange={(e) => setSessionTitleInput(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSaveSessionRename(session.id)}
                        onBlur={() => handleSaveSessionRename(session.id)}
                        autoFocus
                        style={{
                          backgroundColor: 'var(--bg-input)',
                          border: '1px solid #60a5fa',
                          color: '#fff',
                          fontSize: '11px',
                          padding: '2px 4px',
                          borderRadius: '4px',
                          width: '100%',
                        }}
                      />
                    ) : (
                      <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', flex: 1 }}>
                        💬 {session.title}
                      </span>
                    )}

                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }} onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        onClick={() => handleStartRenameSession(session)}
                        title="Renomear Conversa"
                        style={{ background: 'none', border: 'none', color: isActive ? '#fff' : 'var(--text-muted)', cursor: 'pointer', fontSize: '10px' }}
                      >
                        ✏️
                      </button>
                      <button
                        type="button"
                        onClick={() => handleOpenMoveModal(session)}
                        title="Mover para Pasta"
                        style={{ background: 'none', border: 'none', color: isActive ? '#fff' : 'var(--text-muted)', cursor: 'pointer', fontSize: '10px' }}
                      >
                        📁
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteSession(session.id)}
                        title="Excluir Conversa"
                        style={{ background: 'none', border: 'none', color: isActive ? '#fff' : '#ef4444', cursor: 'pointer', fontSize: '10px' }}
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </Card>

      {/* ---------------------------------------------------------------- */}
      {/* Main Chat Box */}
      {/* ---------------------------------------------------------------- */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '16px', overflow: 'hidden' }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: 'var(--bg-secondary)', padding: '16px 20px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
          <div>
            <h1 style={{ fontSize: '18px', fontWeight: 800, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>💬</span>
              <span>{activeSession?.title || 'Mission Control & PO Chat'}</span>
            </h1>
            <p style={{ color: 'var(--text-secondary)', margin: '4px 0 0 0', fontSize: '13px' }}>
              Histórico de mensagens sincronizado via PostgreSQL com o Scrum Master.
            </p>
          </div>
          <Button variant="primary" onClick={() => onNavigateToTab('kanban')}>
            📋 Ir para Kanban Board →
          </Button>
        </div>

        {/* Chat Messages Card */}
        <Card style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '20px', overflow: 'hidden' }}>
          {loadingHistory ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '14px' }}>
              Carregando histórico da conversa do PostgreSQL...
            </div>
          ) : historyError ? (
            <ResourceState status="error" title="Histórico indisponível" message={historyError} testId="chat-history-state-error" />
          ) : messages.length === 0 ? (
            <ResourceState status="empty" title="Nenhuma mensagem nesta sessão" message="A sessão existe, mas a API ainda não retornou mensagens persistidas." testId="chat-history-state-empty" />
          ) : (
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
                  {msg.attachments && msg.attachments.length > 0 && (
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
              <div ref={messagesEndRef} />
            </div>
          )}

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
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
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
            <Button variant="primary" onClick={handleSend} disabled={isProcessing || !activeSessionId}>
              Enviar 🚀
            </Button>
          </div>
        </Card>
      </div>

      {/* Modal: Move Session to Folder */}
      {movingSession && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
          }}
          onClick={() => setMovingSession(null)}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-secondary)',
              padding: '24px',
              borderRadius: '12px',
              border: '1px solid var(--border-color)',
              width: '360px',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', fontWeight: 700 }}>
              📁 Mover Conversa para Pasta
            </h3>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
              Selecione a pasta de projeto de destino para a conversa <strong>"{movingSession.title}"</strong>:
            </p>
            <select
              value={targetFolderId}
              onChange={(e) => setTargetFolderId(e.target.value === 'none' ? 'none' : Number(e.target.value))}
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: '8px',
                backgroundColor: 'var(--bg-input)',
                border: '1px solid var(--border-color)',
                color: 'var(--text-primary)',
                fontSize: '14px',
                marginBottom: '20px',
              }}
            >
              <option value="none">🌐 Conversas Soltas (Sem Pasta)</option>
              {folders.map((f) => (
                <option key={f.id} value={f.id}>
                  📁 {f.name}
                </option>
              ))}
            </select>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <Button variant="secondary" onClick={() => setMovingSession(null)}>
                Cancelar
              </Button>
              <Button variant="primary" onClick={handleConfirmMoveSession}>
                Salvar Alteração
              </Button>
            </div>
          </div>
        </div>
      )}
      </div>
    </section>
  );
}
