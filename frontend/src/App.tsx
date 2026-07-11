import { useState, useRef, useEffect } from "react";
import {
  Send,
  Layers,
  CheckCircle,
  Terminal,
  Lock,
  Plus,
  UploadCloud,
  FileText,
  Loader2,
  ChevronLeft,
  ChevronRight
} from "lucide-react";

interface Message {
  id: string;
  sender: "customer" | "agent" | "system" | "audit";
  text: string;
  timestamp: string;
  authorName?: string;
}

interface CaseItem {
  id: string;
  subject: string;
  customerName: string;
  severity: "critical" | "major" | "minor";
  slaMinutesLeft: number;
  status: "ACTIVE" | "PENDING_CUSTOMER" | "RESOLVED";
  tier: string;
  messages: Message[];
  uploadedFileName?: string | null;
}

const INITIAL_CASES: CaseItem[] = [
  {
    id: "1042",
    subject: "SAML 2.0 SSO Signature Mismatch Failure",
    customerName: "Acme Corporation",
    severity: "critical",
    slaMinutesLeft: 12,
    status: "ACTIVE",
    tier: "Platinum Enterprise",
    messages: [
      {
        id: "m1",
        sender: "customer",
        text: "Hi support team, none of our developers can log into the GigaCorp staging console. They get a secure signature mismatch error.",
        timestamp: "17:30 UTC",
        authorName: "Sarah Jenkins"
      }
    ],
    uploadedFileName: null
  }
];
if (!localStorage.getItem("gigacorp_v5_clean")) {
  localStorage.clear();
  localStorage.setItem("gigacorp_v5_clean", "true");
}
export default function App() {
  const [cases, setCases] = useState<CaseItem[]>(() => {
    const savedCases = localStorage.getItem("gigacorp_cases");
    return savedCases ? JSON.parse(savedCases) : INITIAL_CASES;
  });

  const [selectedCaseId, setSelectedCaseId] = useState<string>(() => {
    const savedSelectedId = localStorage.getItem("gigacorp_selected_case_id");
    return savedSelectedId || "1042";
  });

  const [inputMessage, setInputMessage] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [auditLog, setAuditLog] = useState<string | null>(null);

  const [dragActive, setDragActive] = useState<boolean>(false);
  const [uploadingFile, setUploadingFile] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [leftSidebarOpen, setLeftSidebarOpen] = useState<boolean>(true);
  const [rightSidebarOpen, setRightSidebarOpen] = useState<boolean>(true);

  const activeCase = cases.find((c) => c.id === selectedCaseId) || cases[0] || INITIAL_CASES[0];

  useEffect(() => {
    localStorage.setItem("gigacorp_cases", JSON.stringify(cases));
  }, [cases]);

  useEffect(() => {
    localStorage.setItem("gigacorp_selected_case_id", selectedCaseId);
  }, [selectedCaseId]);

  const handleNewChat = () => {
    const newId = String(Math.floor(1000 + Math.random() * 9000));
    const newCase: CaseItem = {
      id: newId,
      subject: "New Dynamic RAG Session - Awaiting Document",
      customerName: "New Enterprise Client",
      severity: "minor",
      slaMinutesLeft: 60,
      status: "ACTIVE",
      tier: "Standard Custom Tier",
      messages: [
        {
          id: "sys-" + Date.now(),
          sender: "system",
          text: `Welcome to session #${newId}. Please upload a custom company PDF on the right panel to initialize RAG context routing.`,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) + " UTC"
        }
      ],
      uploadedFileName: null
    };
    setCases((prev) => [newCase, ...prev]);
    setSelectedCaseId(newId);
    setAuditLog(`NEW CHAT SESSION INITIALIZED: CASE #${newId}`);
    setTimeout(() => setAuditLog(null), 2500);
  };

  const handleSendResponse = async () => {
    if (!inputMessage.trim()) return;

    const userMsg: Message = {
      id: "agent-" + Date.now(),
      sender: "agent",
      text: inputMessage,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) + " UTC",
      authorName: "Support Engineer"
    };

    setCases((prev) =>
      prev.map((c) => (c.id === activeCase.id ? { ...c, messages: [...c.messages, userMsg] } : c))
    );
    
    const textToSubmit = inputMessage;
    setInputMessage("");
    setLoading(true);
    setAuditLog("API REQUEST DISPATCHED TO FASTAPI BACKEND...");

    try {
      const response = await fetch("http://localhost:8000//api/v1/support/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          case_id: activeCase.id,
          message: textToSubmit
        })
      });

      const data = await response.json();

      if (response.ok) {
        const aiMsg: Message = {
          id: "ai-" + Date.now(),
          sender: "system",
          text: data.answer,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) + " UTC"
        };

        setCases((prev) =>
          prev.map((c) => (c.id === activeCase.id ? { ...c, status: "PENDING_CUSTOMER", messages: [...c.messages, aiMsg] } : c))
        );
        setAuditLog("RESPONSE FETCHED AND CHECKPOINTED TO JSON DISK STORAGE.");
      } else {
        setAuditLog("SERVER ERROR DETECTED DURING ROUTING POOL TRANSFER.");
      }
    } catch (error) {
      setAuditLog("CONNECTION FAILED: MAKE SURE BACKEND IS RUNNING UP ON PORT 8000.");
    } finally {
      setLoading(false);
      setTimeout(() => setAuditLog(null), 3000);
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      await handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      await handleFileUpload(e.target.files[0]);
    }
  };

  const handleFileUpload = async (file: File) => {
    if (file.type !== "application/pdf") {
      setAuditLog("ERROR: ONLY PDF FILES ARE ALLOWED.");
      setTimeout(() => setAuditLog(null), 3000);
      return;
    }

    setUploadingFile(true);
    setAuditLog(`UPLOADING ${file.name.toUpperCase()} TO KNOWLEDGE BASE...`);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("case_id", activeCase.id);

    try {
      const response = await fetch("http://localhost:8000//api/v1/support/upload", {
        method: "POST",
        body: formData
      });

      if (response.ok) {
        const systemMsg: Message = {
          id: "sys-upload-" + Date.now(),
          sender: "audit",
          text: `Knowledge source injected successfully: ${file.name}. Vector database has re-indexed context for Case #${activeCase.id}.`,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) + " UTC"
        };

        setCases((prev) =>
          prev.map((c) => (c.id === activeCase.id ? { ...c, customerName: file.name, uploadedFileName: file.name, messages: [...c.messages, systemMsg] } : c))
        );
        setAuditLog("PDF EMBEDDED & INJECTED INTO VECTOR STORAGE!");
      } else {
        setAuditLog("UPLOAD FAILED ON STORAGE SERVICE SERVER.");
      }
    } catch (error) {
      setAuditLog("CONNECTION FAILED DURING FILE INGESTION PROTOCOL.");
    } finally {
      setUploadingFile(false);
      setTimeout(() => setAuditLog(null), 4000);
    }
  };

  return (
    <div className="h-screen w-screen bg-slate-100 flex flex-col overflow-hidden text-slate-800 font-sans relative">
      <header className="h-14 bg-slate-900 border-b border-slate-800 px-6 flex items-center justify-between text-white shadow-md z-10">
        <div className="flex items-center space-x-4">
          <span className="font-bold tracking-tight text-sm uppercase font-mono">GigaCorp Dashboard</span>
        </div>
        <div className="flex items-center space-x-2 text-xs text-slate-400 font-mono">
          <Lock className="w-3.5 h-3.5 text-emerald-500" />
          <span>SECURE CONSOLE</span>
        </div>
      </header>

      {auditLog && (
        <div className="absolute top-16 left-1/2 -translate-x-1/2 bg-slate-900 border border-slate-700 text-white text-xs px-4 py-2 rounded shadow-xl flex items-center space-x-2 z-50 font-mono animate-bounce">
          <Terminal className="w-3.5 h-3.5 text-blue-400" />
          <span>{auditLog}</span>
        </div>
      )}

      <div className="flex-1 flex overflow-hidden relative">
        
        <aside className={`bg-white border-r border-slate-200 flex flex-col transition-all duration-300 relative ${leftSidebarOpen ? "w-72" : "w-0 overflow-hidden border-r-0"}`}>
          <div className="p-4 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between min-w-[288px]">
            <span className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-slate-500" /> Incidents Stack
            </span>
            <button onClick={handleNewChat} className="p-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors flex items-center text-xs font-medium gap-0.5 shadow-sm">
              <Plus className="w-3.5 h-3.5" />
              <span className="pr-1">New</span>
            </button>
          </div>
          
          <div className="flex-1 overflow-y-auto min-w-[288px]">
            {cases.map((c) => (
              <button 
                key={c.id} 
                onClick={() => setSelectedCaseId(c.id)} 
                className={`w-full text-left p-4 border-b border-slate-100 flex flex-col space-y-1 transition-all ${c.id === activeCase.id ? "border-l-4 border-l-blue-600 bg-blue-50/40 font-medium" : "hover:bg-slate-50/60"}`}
              >
                <span className="font-mono text-[10px] text-slate-400">SESSION THREAD #{c.id}</span>
                <h4 className="font-semibold text-slate-800 text-xs truncate max-w-[240px]">{c.customerName}</h4>
                <p className="text-slate-500 text-xs truncate max-w-[240px]">{c.subject}</p>
                <div className="flex justify-between items-center pt-2 text-[10px] text-slate-400 font-mono">
                  <span>{c.tier}</span>
                </div>
              </button>
            ))}
          </div>
        </aside>

        <button 
          onClick={() => setLeftSidebarOpen(!leftSidebarOpen)} 
          className={`absolute bottom-6 bg-white border border-slate-200 p-1.5 rounded-full shadow-md hover:bg-slate-50 transition-all z-40 ${leftSidebarOpen ? "left-[270px]" : "left-4"}`}
        >
          {leftSidebarOpen ? <ChevronLeft className="w-4 h-4 text-slate-600" /> : <ChevronRight className="w-4 h-4 text-slate-600" />}
        </button>

        <section className="flex-1 bg-slate-50 flex flex-col overflow-hidden border-r border-slate-200 relative">
          <div className="h-14 bg-white border-b border-slate-200 px-6 flex items-center justify-between shadow-sm">
            <h2 className="font-semibold text-slate-800 text-sm truncate pr-4">{activeCase.customerName}</h2>
          </div>

          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {activeCase.messages.map((msg) => (
              <div key={msg.id} className={`flex flex-col space-y-1 max-w-xl ${msg.sender === "agent" ? "ml-auto" : "mr-auto"} ${msg.sender === "audit" ? "max-w-full w-full items-center" : ""}`}>
                {msg.sender !== "audit" && (
                  <div className="text-[10px] text-slate-400 font-mono px-1">
                    {msg.sender === "agent" ? "Support Engineer" : msg.authorName || "AI Core Agent"} • {msg.timestamp}
                  </div>
                )}
                
                <div className={`p-3 rounded text-xs leading-relaxed shadow-sm ${
                  msg.sender === "agent" 
                    ? "bg-blue-600 text-white rounded-br-none" 
                    : msg.sender === "audit"
                    ? "bg-amber-50 text-amber-800 border border-amber-200 w-full font-mono text-center rounded"
                    : "bg-white text-slate-800 border border-slate-200 rounded-bl-none"
                }`}>
                  {msg.text}
                </div>
              </div>
            ))}
          </div>

          <div className="p-4 bg-white border-t border-slate-200 flex items-center space-x-2">
            <input 
              type="text" 
              placeholder="Ask anything based on the context pool engine..." 
              value={inputMessage} 
              onChange={(e) => setInputMessage(e.target.value)} 
              onKeyDown={(e) => e.key === "Enter" && handleSendResponse()} 
              disabled={loading} 
              className="flex-1 px-4 py-2.5 bg-slate-50 border border-slate-200 rounded text-xs focus:outline-none focus:border-slate-400 focus:bg-white transition-all" 
            />
            <button onClick={handleSendResponse} disabled={loading} className="px-5 py-2.5 bg-slate-900 text-white rounded text-xs font-medium hover:bg-slate-800 flex items-center space-x-1.5 shadow transition-all">
              <Send className="w-3.5 h-3.5" />
              <span>{loading ? "Thinking..." : "Send"}</span>
            </button>
          </div>
        </section>

        <button 
          onClick={() => setRightSidebarOpen(!rightSidebarOpen)} 
          className={`absolute bottom-6 bg-white border border-slate-200 p-1.5 rounded-full shadow-md hover:bg-slate-50 transition-all z-40 ${rightSidebarOpen ? "right-[302px]" : "right-4"}`}
        >
          {rightSidebarOpen ? <ChevronRight className="w-4 h-4 text-slate-600" /> : <ChevronLeft className="w-4 h-4 text-slate-600" />}
        </button>

        <aside className={`bg-white flex flex-col transition-all duration-300 relative ${rightSidebarOpen ? "w-80" : "w-0 overflow-hidden"}`}>
          <div className="p-4 border-b border-slate-100 bg-slate-50/50 min-w-[320px]">
            <span className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
              <UploadCloud className="w-4 h-4 text-slate-500" /> Vector Ingestion Engine
            </span>
          </div>

          <div className="p-6 flex-1 flex flex-col space-y-6 min-w-[320px]">
            <div className="text-xs text-slate-500 leading-relaxed">
              Upload a business-specific **PDF document** to bind contextual information directly to **Thread #{activeCase.id}**.
            </div>

            <div 
              onDragEnter={handleDrag}
              onDragOver={handleDrag}
              onDragLeave={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`flex-1 border-2 border-dashed rounded-lg flex flex-col items-center justify-center p-4 text-center cursor-pointer transition-all ${
                dragActive ? "border-blue-500 bg-blue-50/50" : "border-slate-200 hover:bg-slate-50/80"
              }`}
            >
              <input 
                ref={fileInputRef}
                type="file" 
                accept="application/pdf" 
                onChange={handleFileChange} 
                className="hidden" 
              />
              
              {uploadingFile ? (
                <div className="flex flex-col items-center space-y-2 animate-pulse">
                  <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
                  <span className="text-xs font-medium text-slate-600">Embedding Vectors...</span>
                </div>
              ) : (
                <div className="flex flex-col items-center space-y-3">
                  <UploadCloud className={`w-10 h-10 ${dragActive ? "text-blue-500" : "text-slate-400"}`} />
                  <div className="text-xs font-semibold text-slate-700">
                    {dragActive ? "Drop file now!" : "Drag & Drop company PDF"}
                  </div>
                  <span className="text-[10px] text-slate-400">or click to browse local files</span>
                </div>
              )}
            </div>

            <div className="bg-slate-50 border border-slate-100 rounded-md p-4 flex flex-col space-y-2">
              <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Active Workspace Binder</div>
              {activeCase.uploadedFileName ? (
                <div className="flex items-center space-x-2 text-xs text-emerald-700 font-medium">
                  <CheckCircle className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                  <span className="truncate max-w-[220px]">{activeCase.uploadedFileName}</span>
                </div>
              ) : (
                <div className="flex items-center space-x-2 text-xs text-slate-400 italic">
                  <FileText className="w-4 h-4 text-slate-300 flex-shrink-0" />
                  <span>Using fallback base index</span>
                </div>
              )}
            </div>

          </div>
        </aside>

      </div>
    </div>
  );
}