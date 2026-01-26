import React, { useState, useEffect, useRef } from 'react';
import { HashRouter, Routes, Route, useNavigate, useLocation, useParams, Navigate } from 'react-router-dom';
import { 
  Home as HomeIcon, 
  Plus, 
  History as HistoryIcon, 
  Camera, 
  FileText, 
  PenTool, 
  Trash2, 
  CheckCircle, 
  XCircle, 
  ChevronRight,
  ChevronLeft,
  ChevronsLeft,
  ChevronsRight,
  ArrowLeft,
  Save,
  Loader2,
  MoreVertical,
  Play,
  LogOut,
  User as UserIcon,
  Copy,
  ExternalLink,
  CheckSquare,
  Square,
  X,
  Settings,
  Moon,
  Sun,
  Upload,
  Share2,
  Download
} from 'lucide-react';
import { signInWithPopup, signOut, onAuthStateChanged, User } from 'firebase/auth';
import { auth, googleProvider } from './services/firebaseConfig';
import { Button, Card, Input, TextArea, Badge } from './components/UI';
import { storageService } from './services/storageService';
import { parseFileToQuiz } from './services/geminiService';
import { Test, Question, Option, TestResult, AnswerDetail } from './types';

// --- Utils ---
const generateId = () => Math.random().toString(36).substring(2, 9);

// --- Auth Context / Hook simple ---
const useAuth = () => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (currentUser) => {
      setUser(currentUser);
      setLoading(false);
    });
    return () => unsubscribe();
  }, []);

  return { user, loading };
};

// --- Dark Mode Context ---
const useDarkMode = () => {
  const [isDark, setIsDark] = useState(() => {
    return localStorage.getItem('theme') === 'dark';
  });

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  }, [isDark]);

  return { isDark, toggle: () => setIsDark(prev => !prev) };
};

// --- Components ---

// Modal para seleccionar lista existente o crear nueva
const ListSelectionModal = ({ 
  user, 
  onSelect, 
  onCancel 
}: { 
  user: User, 
  onSelect: (testId: string | null, title?: string) => void, 
  onCancel: () => void 
}) => {
  const [tests, setTests] = useState<Test[]>([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<'existing' | 'new'>('existing');
  const [newTitle, setNewTitle] = useState('');

  useEffect(() => {
    const load = async () => {
      const data = await storageService.getTests(user.uid);
      setTests(data);
      if (data.length === 0) setMode('new');
      setLoading(false);
    };
    load();
  }, [user]);

  if (loading) return <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"><Loader2 className="animate-spin text-white" /></div>;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl p-6 w-full max-w-md border-2 border-slate-100 dark:border-slate-700">
        <h2 className="text-xl font-bold mb-4 text-slate-800 dark:text-white">¿Dónde guardamos esto?</h2>
        
        {mode === 'existing' && tests.length > 0 ? (
          <div className="space-y-3">
             <p className="text-sm text-slate-500 dark:text-slate-400 mb-2">Elige una lista existente:</p>
             <div className="max-h-60 overflow-y-auto space-y-2 custom-scrollbar">
               {tests.map(t => (
                 <button 
                   key={t.id}
                   onClick={() => onSelect(t.id, t.title)}
                   className="w-full text-left p-3 rounded-xl border border-slate-200 bg-slate-50 hover:border-brand-500 hover:bg-brand-50 dark:bg-slate-700 dark:border-slate-600 dark:hover:border-brand-500 dark:text-slate-200 transition-all flex justify-between items-center"
                 >
                   <span className="font-medium truncate">{t.title}</span>
                   <span className="text-xs text-slate-400 bg-white dark:bg-slate-800 px-2 py-1 rounded-md border border-slate-100 dark:border-slate-600">{t.questions.length}</span>
                 </button>
               ))}
             </div>
             <div className="pt-4 border-t border-slate-100 dark:border-slate-700 mt-2">
               <Button variant="secondary" onClick={() => setMode('new')} className="w-full dark:bg-slate-700 dark:text-white dark:border-slate-600">
                 + Crear Nueva Lista
               </Button>
             </div>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-slate-500 dark:text-slate-400">Crear una lista nueva:</p>
            <Input 
              autoFocus
              placeholder="Ej: Matemáticas T1" 
              value={newTitle}
              onChange={e => setNewTitle(e.target.value)}
              className="bg-slate-50 dark:bg-slate-700 dark:border-slate-600 dark:text-white"
            />
            <div className="flex gap-2">
               {tests.length > 0 && (
                 <Button variant="ghost" onClick={() => setMode('existing')}>Volver</Button>
               )}
               <Button 
                 className="flex-1"
                 disabled={!newTitle.trim()}
                 onClick={() => onSelect(null, newTitle)}
               >
                 Crear y Continuar
               </Button>
            </div>
          </div>
        )}
        <button onClick={onCancel} className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 dark:hover:text-white"><XCircle /></button>
      </div>
    </div>
  );
};

// --- Pages ---

const SettingsPage = () => {
  const { isDark, toggle } = useDarkMode();
  const navigate = useNavigate();

  return (
    <div className="pb-24 max-w-lg mx-auto p-4">
      <header className="flex items-center gap-2 mb-8">
         <button onClick={() => navigate('/')} className="p-2 hover:bg-white/50 rounded-full text-slate-700 dark:text-slate-300"><ArrowLeft /></button>
         <h1 className="font-bold text-2xl text-slate-800 dark:text-white">Opciones</h1>
      </header>

      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-700 overflow-hidden">
        <div className="p-4 flex items-center justify-between border-b border-slate-100 dark:border-slate-700">
           <div className="flex items-center gap-3">
             <div className="bg-brand-50 dark:bg-slate-700 p-2 rounded-lg text-brand-600 dark:text-brand-400">
               {isDark ? <Moon size={24} /> : <Sun size={24} />}
             </div>
             <div>
               <h3 className="font-medium text-slate-800 dark:text-white">Modo Oscuro</h3>
               <p className="text-xs text-slate-500 dark:text-slate-400">Cambiar la apariencia de la aplicación</p>
             </div>
           </div>
           
           <button 
             onClick={toggle}
             className={`w-14 h-8 rounded-full p-1 transition-colors duration-300 ease-in-out ${isDark ? 'bg-brand-600' : 'bg-slate-200'}`}
           >
             <div className={`bg-white w-6 h-6 rounded-full shadow-sm transform transition-transform duration-300 ${isDark ? 'translate-x-6' : 'translate-x-0'}`} />
           </button>
        </div>
      </div>
      
      <p className="text-center text-slate-400 text-xs mt-8">StudySnap v1.0</p>
    </div>
  );
};

const SharePage = ({ user }: { user: User }) => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [test, setTest] = useState<Test | undefined>(undefined);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      if(!id) return;
      const t = await storageService.getTestById(id);
      setTest(t);
      setLoading(false);
    }
    load();
  }, [id]);

  const handleImport = async () => {
     if(!id) return;
     try {
       await storageService.copyTest(id, user.uid);
       alert("Lista importada correctamente!");
       navigate('/');
     } catch(e) {
       alert("Error al importar la lista.");
     }
  }

  if(loading) return <div className="flex justify-center h-screen items-center"><Loader2 className="animate-spin text-brand-500"/></div>;
  
  if(!test) return (
    <div className="flex flex-col items-center justify-center h-screen p-4 text-center">
      <XCircle size={48} className="text-red-400 mb-4"/>
      <h2 className="text-xl font-bold">Lista no encontrada</h2>
      <p className="text-slate-500 mt-2">El enlace puede ser incorrecto o la lista fue eliminada.</p>
      <Button onClick={() => navigate('/')} className="mt-6">Ir al Inicio</Button>
    </div>
  );

  return (
    <div className="flex flex-col items-center justify-center h-screen p-6 text-center max-w-md mx-auto">
       <div className="bg-white dark:bg-slate-800 p-8 rounded-3xl shadow-xl w-full border border-slate-100 dark:border-slate-700">
          <div className="bg-brand-100 dark:bg-slate-700 w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-6">
             <Download size={32} className="text-brand-600 dark:text-brand-400"/>
          </div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-white mb-2">Importar Lista</h1>
          <p className="text-slate-500 dark:text-slate-400 mb-6">
            ¿Quieres añadir <strong>"{test.title}"</strong> ({test.questions.length} preguntas) a tu colección?
          </p>
          <div className="flex gap-3">
             <Button variant="secondary" onClick={() => navigate('/')} className="flex-1 dark:bg-slate-700 dark:text-white dark:border-slate-600">Cancelar</Button>
             <Button onClick={handleImport} className="flex-1">Importar</Button>
          </div>
       </div>
    </div>
  );
};

const LoginPage = () => {
  const [errorMessage, setErrorMessage] = useState('');

  const handleGoogleLogin = async () => {
    try {
      setErrorMessage('');
      await signInWithPopup(auth, googleProvider);
    } catch (err: any) {
      console.error(err);
      setErrorMessage(err.message);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 text-center">
      <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur p-8 rounded-3xl shadow-xl max-w-sm w-full border border-white dark:border-slate-700">
        <div className="bg-gradient-to-r from-brand-500 to-indigo-600 w-20 h-20 rounded-2xl rotate-3 flex items-center justify-center mx-auto mb-6 shadow-lg shadow-brand-500/30">
          <FileText className="text-white" size={40} />
        </div>
        <h1 className="text-3xl font-bold text-slate-900 dark:text-white mb-2 tracking-tight">StudySnap</h1>
        <p className="text-slate-500 dark:text-slate-400 mb-8 leading-relaxed">Escanea, crea y repasa tus tests en cualquier lugar.</p>
        
        <Button 
          variant="primary"
          onClick={handleGoogleLogin} 
          className="w-full flex items-center justify-center gap-3 py-4 text-lg shadow-lg shadow-brand-500/20 hover:shadow-brand-500/40 transition-all"
        >
          <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="Google" className="w-6 h-6 bg-white rounded-full p-0.5" />
          <span>Entrar con Google</span>
        </Button>
        
        {errorMessage && (
          <p className="mt-4 text-red-500 text-sm bg-red-50 p-2 rounded">{errorMessage}</p>
        )}
      </div>
    </div>
  );
};

const HomePage = ({ user }: { user: User }) => {
  const [tests, setTests] = useState<Test[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    loadTests();
  }, [user]);

  const loadTests = async () => {
    setLoading(true);
    const data = await storageService.getTests(user.uid);
    setTests(data);
    setLoading(false);
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (confirm('¿Quieres eliminar esta lista?')) {
      await storageService.deleteTest(id);
      setTests(prev => prev.filter(t => t.id !== id));
    }
  };
  
  const handleShare = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    const url = `${window.location.origin}/#/share/${id}`;
    try {
       await navigator.clipboard.writeText(url);
       alert("Enlace copiado al portapapeles! Envíaselo a quien quieras.");
    } catch(err) {
       alert("No se pudo copiar: " + url);
    }
  }

  const handleLogout = () => {
    if(confirm("¿Cerrar sesión?")) signOut(auth);
  }

  return (
    <div className="space-y-8 pb-24 max-w-7xl mx-auto w-full">
      <header className="flex justify-between items-center bg-white/80 dark:bg-slate-800/80 backdrop-blur-md p-4 rounded-2xl shadow-sm border border-white/50 dark:border-slate-700">
        <div className="flex items-center gap-3">
          <div className="bg-brand-100 dark:bg-slate-700 p-2 rounded-full hidden sm:block border border-brand-200 dark:border-slate-600">
            <UserIcon className="text-brand-600 dark:text-brand-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-800 dark:text-white">Mis Listas</h1>
            <p className="text-slate-500 dark:text-slate-400 text-sm">Hola, {user.displayName?.split(' ')[0]}</p>
          </div>
        </div>
        
        <div className="flex gap-2">
           <button 
             onClick={() => navigate('/settings')}
             className="p-2 text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 rounded-full transition-colors"
           >
             <Settings size={24} />
           </button>
           <button 
             onClick={handleLogout}
             className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 dark:text-slate-500 dark:hover:bg-slate-700 rounded-full transition-colors" 
             title="Cerrar sesión"
           >
             <LogOut size={24} />
           </button>
        </div>
      </header>

      {loading ? (
        <div className="flex justify-center py-20">
          <Loader2 className="animate-spin text-brand-500" size={40} />
        </div>
      ) : tests.length === 0 ? (
        <div className="text-center py-20 text-slate-400 bg-white/60 dark:bg-slate-800/60 rounded-3xl border border-white dark:border-slate-700 shadow-sm mx-auto max-w-lg">
          <div className="bg-slate-100 dark:bg-slate-700 w-24 h-24 rounded-full flex items-center justify-center mx-auto mb-6">
            <FileText size={40} className="text-slate-300 dark:text-slate-500" />
          </div>
          <h2 className="text-xl font-semibold text-slate-600 dark:text-slate-300 mb-2">No tienes listas guardadas</h2>
          <p className="text-slate-500 dark:text-slate-400">Pulsa el botón + para empezar.</p>
        </div>
      ) : (
        <div className="grid gap-6 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {tests.map(test => (
            <Card key={test.id} onClick={() => navigate(`/quiz/${test.id}`)} className="bg-white dark:bg-slate-800 border-2 border-slate-100 dark:border-slate-700 hover:border-brand-200 dark:hover:border-brand-700 hover:shadow-md transition-all cursor-pointer h-full flex flex-col justify-between">
              <div>
                <div className="flex justify-between items-start mb-3">
                  <div className="bg-brand-50 dark:bg-slate-700 p-2 rounded-lg text-brand-600 dark:text-brand-400 border border-brand-100 dark:border-slate-600">
                    <FileText size={20}/>
                  </div>
                  <div className="flex gap-1">
                    <button onClick={(e) => handleShare(e, test.id)} className="text-slate-300 hover:text-brand-500 p-1.5 hover:bg-brand-50 dark:hover:bg-slate-700 rounded-md transition-colors" title="Compartir">
                      <Share2 size={18} />
                    </button>
                    <button onClick={(e) => handleDelete(e, test.id)} className="text-slate-300 hover:text-red-500 p-1.5 hover:bg-red-50 dark:hover:bg-slate-700 rounded-md transition-colors" title="Borrar">
                      <Trash2 size={18} />
                    </button>
                  </div>
                </div>
                <h3 className="font-bold text-lg text-slate-800 dark:text-slate-100 line-clamp-2 mb-1">{test.title}</h3>
                <div className="text-sm text-slate-500 dark:text-slate-400 mb-4">{test.questions.length} preguntas</div>
              </div>
              
              <div className="flex gap-2 mt-auto pt-4 border-t border-slate-100 dark:border-slate-700">
                 <Button 
                    variant="secondary" 
                    className="flex-1 text-sm py-2 dark:bg-slate-700 dark:text-slate-200 dark:border-slate-600"
                    onClick={(e) => { e.stopPropagation(); navigate(`/editor/${test.id}?mode=manual`); }}
                 >
                   Editar
                 </Button>
                 <Button variant="primary" className="flex-1 text-sm py-2 flex justify-center items-center gap-1 shadow-md shadow-brand-200 dark:shadow-none">
                   <Play size={16} /> Jugar
                 </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

const EditorPage = ({ user }: { user: User }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const searchParams = new URLSearchParams(location.search);
  const modeParam = searchParams.get('mode'); // 'manual' | 'camera'
  const { id: editId } = useParams();

  // State
  const [title, setTitle] = useState('');
  const [questions, setQuestions] = useState<Question[]>([]);
  const [currentQIndex, setCurrentQIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [progressMsg, setProgressMsg] = useState('');
  const [showListSelector, setShowListSelector] = useState(false);
  const [viewMode, setViewMode] = useState<'editor' | 'scanner'>(modeParam === 'camera' ? 'scanner' : 'editor');

  // Inicialización
  useEffect(() => {
    const init = async () => {
      if (editId) {
        setIsLoading(true);
        const test = await storageService.getTestById(editId);
        if (test && test.userId === user.uid) {
          setTitle(test.title);
          setQuestions(test.questions);
          // Si venimos de cámara, activamos vista de escáner.
          // Si es manual, activamos vista editor y vamos a la 1ª pregunta.
          if (modeParam === 'camera') {
            setViewMode('scanner');
          } else {
            setViewMode('editor');
            setCurrentQIndex(0);
          }
        } else {
           alert("Error al cargar test.");
           navigate('/');
        }
        setIsLoading(false);
        return;
      }

      if (modeParam && !editId) {
        setShowListSelector(true);
      }
    };
    init();
  }, [editId, modeParam, user]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsLoading(true);
    setProgressMsg("Subiendo documento...");
    
    // Simulación de progreso
    const progressInterval = setInterval(() => {
        setProgressMsg(p => p === "Subiendo documento..." ? "Analizando con IA..." : (p === "Analizando con IA..." ? "Extrayendo preguntas..." : "Casi listo..."));
    }, 2000);

    const reader = new FileReader();
    reader.onloadend = async () => {
      try {
        const base64String = (reader.result as string).split(',')[1];
        const extractedQuestions = await parseFileToQuiz(base64String, file.type, (msg) => setProgressMsg(msg));
        
        setQuestions(prev => [...prev, ...extractedQuestions]);
        
        // Mantenernos en modo escáner, mostrando la lista abajo
        setViewMode('scanner');
        clearInterval(progressInterval);

      } catch (err: any) {
        alert(err.message);
      } finally {
        clearInterval(progressInterval);
        setIsLoading(false);
        setProgressMsg('');
        e.target.value = '';
      }
    };
    reader.readAsDataURL(file);
  };

  const getCurrentQuestion = (): Question => {
    // Para modo editor, si estamos en el final, es nueva
    if (currentQIndex === questions.length) {
      return {
        id: generateId(),
        text: '',
        options: Array(4).fill(null).map(() => ({ id: generateId(), text: '' })), 
        correctOptionId: ''
      };
    }
    return questions[currentQIndex];
  };

  const updateCurrentQuestion = (field: keyof Question, value: any) => {
    const newQs = [...questions];
    if (currentQIndex === questions.length) {
       const newQ = getCurrentQuestion();
       (newQ as any)[field] = value;
       setQuestions([...newQs, newQ]);
    } else {
       (newQs[currentQIndex] as any)[field] = value;
       setQuestions(newQs);
    }
  };

  const updateOption = (oIndex: number, text: string) => {
    const q = getCurrentQuestion();
    const newOptions = [...q.options];
    newOptions[oIndex] = { ...newOptions[oIndex], text };
    updateCurrentQuestion('options', newOptions);
  };

  const setCorrectOption = (oId: string) => {
    updateCurrentQuestion('correctOptionId', oId);
  };

  const navigateQuestion = (direction: 'prev' | 'next') => {
    if (direction === 'prev') {
      if (currentQIndex > 0) setCurrentQIndex(prev => prev - 1);
    } else {
      // Permitir ir al índice questions.length (nueva pregunta)
      if (currentQIndex < questions.length) setCurrentQIndex(prev => prev + 1);
      else {
        // Estamos en la nueva, si tiene texto, creamos otra nueva (movemos índice)
        const current = getCurrentQuestion();
        if(current.text.trim()) setCurrentQIndex(prev => prev + 1);
      }
    }
  };

  // Funciones de navegación extra
  const goToFirst = () => setCurrentQIndex(0);
  const goToLast = () => {
      // Si la última pregunta está vacía (modo añadir), vamos a la anterior válida, o al final
      if (questions.length > 0) setCurrentQIndex(questions.length - 1);
  };
  const goToPagePrompt = () => {
    const page = prompt(`Ir a pregunta (1 - ${questions.length + 1}):`);
    if (page) {
       const pageNum = parseInt(page);
       if (!isNaN(pageNum) && pageNum >= 1 && pageNum <= questions.length + 1) {
          setCurrentQIndex(pageNum - 1);
       }
    }
  };

  const handleSave = async () => {
    if (!title.trim()) return alert("Escribe un título para la lista.");
    
    // Filtrar preguntas vacías
    const validQuestions = questions.filter(q => q.text.trim() !== '');
    if (validQuestions.length === 0) return alert("Añade al menos una pregunta.");
    
    // Validar respuestas vacías
    const emptyOptionIndex = questions.findIndex(q => q.text.trim() !== '' && q.options.some(o => !o.text.trim()));
    if (emptyOptionIndex !== -1) {
        // IMPORTANTE: Cambiamos a modo editor y vamos a la pregunta
        setViewMode('editor');
        setCurrentQIndex(emptyOptionIndex);
        return alert(`La pregunta ${emptyOptionIndex + 1} tiene respuestas vacías.`);
    }

    // Validar respuesta correcta marcada
    const missingAnswerIndex = questions.findIndex(q => q.text.trim() !== '' && !q.correctOptionId);
    if (missingAnswerIndex !== -1) {
        setViewMode('editor');
        setCurrentQIndex(missingAnswerIndex);
        return alert(`La pregunta ${missingAnswerIndex + 1} no tiene marcada la respuesta correcta.`);
    }

    setIsLoading(true);
    setProgressMsg("Guardando...");
    
    try {
      const test: Test = {
        id: editId || generateId(), 
        userId: user.uid,
        title,
        createdAt: Date.now(),
        questions: validQuestions
      };

      await storageService.saveTest(test); 
      navigate('/');
    } catch (error: any) {
       alert("Error al guardar: " + error.message);
    } finally {
       setIsLoading(false);
       setProgressMsg('');
    }
  };

  const onListSelectFinal = (id: string | null, newTitle?: string) => {
    if (id) {
       navigate(`/editor/${id}?mode=${modeParam}`, { replace: true });
       setShowListSelector(false);
    } else if (newTitle) {
      setTitle(newTitle);
      setQuestions([]);
      // Si es cámara, vamos directo a scanner mode
      if (modeParam === 'camera') setViewMode('scanner');
      else {
        setViewMode('editor');
        setCurrentQIndex(0);
      }
      setShowListSelector(false);
    }
  };

  // Botón para editar pregunta específica desde el modo escáner
  const editQuestionFromList = (index: number) => {
    setViewMode('editor');
    setCurrentQIndex(index);
  }

  // Añadir pregunta manual nueva
  const addNewQuestionManual = () => {
     setViewMode('editor');
     setCurrentQIndex(questions.length); // Ir al final (nueva)
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-slate-50 dark:bg-slate-900 z-50 fixed inset-0">
        <Loader2 className="animate-spin text-brand-600 mb-4" size={48} />
        <p className="text-slate-600 dark:text-slate-300 font-bold text-lg mb-2">{progressMsg || "Procesando..."}</p>
        <div className="w-64 h-2 bg-slate-200 rounded-full overflow-hidden">
           <div className="h-full bg-brand-500 animate-pulse w-full origin-left"></div>
        </div>
      </div>
    );
  }

  const activeQ = getCurrentQuestion();
  
  // Total pages display logic:
  // Si estamos editando una existente: index + 1 / total
  // Si estamos en la "fantasma" (nueva): total + 1 / total + 1
  const displayTotal = currentQIndex === questions.length ? questions.length + 1 : questions.length;
  const displayIndex = currentQIndex + 1;

  return (
    <div className="pb-24 max-w-4xl mx-auto">
      {showListSelector && (
        <ListSelectionModal 
          user={user} 
          onSelect={onListSelectFinal} 
          onCancel={() => navigate('/')} 
        />
      )}

      <input 
        id="file-upload-trigger" 
        type="file" 
        className="hidden" 
        // Solo archivos e imágenes en PC (navegador gestiona cámara si es móvil)
        accept="image/*,application/pdf" 
        onChange={handleFileUpload} 
      />

      <header className="sticky top-0 bg-white/90 dark:bg-slate-900/90 backdrop-blur z-20 py-4 border-b border-slate-200 dark:border-slate-800 mb-6 flex justify-between items-center px-4 -mx-4 shadow-sm">
        <div className="flex items-center gap-2">
           <button onClick={() => navigate('/')} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full text-slate-600 dark:text-slate-300"><ArrowLeft /></button>
           <div className="flex flex-col">
             <span className="text-xs text-slate-400 dark:text-slate-500 font-bold uppercase">
               {viewMode === 'scanner' ? 'Modo Escáner' : 'Editor Manual'}
             </span>
             <input 
                value={title}
                onChange={e => setTitle(e.target.value)}
                placeholder="Título de la lista..."
                className="font-bold text-slate-800 dark:text-white bg-transparent focus:outline-none focus:border-b-2 border-brand-500 w-32 sm:w-auto placeholder:text-slate-300"
             />
           </div>
        </div>
        <div className="flex gap-2">
             {viewMode === 'editor' && (
               <Button variant="secondary" onClick={() => setViewMode('scanner')} className="p-2 rounded-full border-slate-200 dark:border-slate-700 dark:bg-slate-800" title="Volver a Escáner">
                  <Camera size={20} className="text-slate-600 dark:text-slate-300"/>
               </Button>
             )}
            
            <div className="flex flex-col items-center">
                <span className="text-[10px] font-bold text-brand-600 dark:text-brand-400 uppercase tracking-wider mb-1">Guardar</span>
                <Button onClick={handleSave} className="w-12 h-12 rounded-full p-0 flex items-center justify-center shadow-lg shadow-brand-200 dark:shadow-none bg-brand-600 hover:bg-brand-700">
                  <Save size={20} />
                </Button>
            </div>
        </div>
      </header>

      {/* --- VISTA ESCÁNER --- */}
      {viewMode === 'scanner' && (
        <div className="space-y-6">
           <div className="bg-brand-50 dark:bg-slate-800 border border-brand-200 dark:border-slate-700 rounded-2xl p-8 text-center shadow-sm">
              <div className="bg-white dark:bg-slate-700 w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-4 shadow-sm">
                  <Camera className="text-brand-500" size={36} />
              </div>
              <h3 className="font-bold text-xl text-slate-800 dark:text-white mb-2">Modo Escáner Activo</h3>
              <p className="text-slate-600 dark:text-slate-300 mb-6 max-w-xs mx-auto">
                 Haz fotos a tu libro o sube un PDF. La IA extraerá las preguntas automáticamente.
              </p>
              <Button onClick={() => document.getElementById('file-upload-trigger')?.click()} className="w-full sm:w-auto px-8 py-3 text-lg flex items-center justify-center gap-2 shadow-lg shadow-brand-500/20">
                 <Upload size={20} /> Abrir Cámara / Archivo
              </Button>
              <div className="mt-4">
                <button onClick={addNewQuestionManual} className="text-sm text-brand-600 dark:text-brand-400 font-medium hover:underline">
                  O añadir pregunta manual
                </button>
              </div>
           </div>

           {questions.length > 0 && (
             <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 overflow-hidden">
                <div className="p-4 bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 font-bold text-slate-500 dark:text-slate-400 text-sm uppercase">
                  Preguntas extraídas ({questions.length})
                </div>
                <div className="divide-y divide-slate-100 dark:divide-slate-700 max-h-[500px] overflow-y-auto">
                  {questions.map((q, idx) => (
                    <div key={q.id} onClick={() => editQuestionFromList(idx)} className="p-4 hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer flex gap-3 group transition-colors">
                       <span className="font-bold text-slate-300 dark:text-slate-600 group-hover:text-brand-500">{idx + 1}.</span>
                       <div className="flex-1">
                          <p className="text-sm font-medium text-slate-800 dark:text-slate-200 line-clamp-2">{q.text}</p>
                          <span className="text-xs text-slate-400">{q.options.length} opciones {q.correctOptionId ? '• Respuesta marcada' : '• Sin respuesta'}</span>
                       </div>
                       <ChevronRight size={16} className="text-slate-300 self-center"/>
                    </div>
                  ))}
                </div>
             </div>
           )}
        </div>
      )}

      {/* --- VISTA EDITOR MANUAL --- */}
      {viewMode === 'editor' && (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-300">
          
          <div className="flex justify-between items-center bg-white dark:bg-slate-800 p-2 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 mb-4">
             <div className="flex gap-1">
                 <Button variant="ghost" onClick={goToFirst} disabled={currentQIndex === 0} className="px-2 dark:text-slate-400 dark:hover:bg-slate-700" title="Ir al principio">
                   <ChevronsLeft size={20} />
                 </Button>
                 <Button variant="ghost" onClick={() => navigateQuestion('prev')} disabled={currentQIndex === 0} className="px-2 dark:text-slate-300 dark:hover:bg-slate-700">
                   <ChevronLeft size={20} />
                 </Button>
             </div>
             
             <button onClick={goToPagePrompt} className="font-mono font-bold text-slate-500 dark:text-slate-400 hover:text-brand-600 dark:hover:text-brand-400 px-2 py-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors">
               {displayIndex} <span className="text-slate-300 dark:text-slate-600">/</span> {displayTotal}
             </button>
  
             <div className="flex gap-1">
                 <Button variant="ghost" onClick={() => navigateQuestion('next')} disabled={currentQIndex === questions.length} className="px-2 text-brand-600 dark:text-brand-400 dark:hover:bg-slate-700">
                   <ChevronRight size={20} />
                 </Button>
                 {/* Nuevo Botón + a la derecha */}
                 <Button variant="secondary" onClick={addNewQuestionManual} className="px-2 ml-1 border-l border-slate-200 dark:border-slate-600 rounded-none rounded-r-lg" title="Nueva Pregunta">
                    <Plus size={20} className="text-brand-600 dark:text-brand-400"/>
                 </Button>
             </div>
          </div>
  
          <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-md border border-slate-200 dark:border-slate-700 p-6 relative min-h-[400px]">
              <div className="mb-6">
                <label className="block text-xs uppercase text-slate-400 dark:text-slate-500 font-bold mb-2">Pregunta</label>
                <TextArea 
                  value={activeQ.text} 
                  onChange={e => updateCurrentQuestion('text', e.target.value)} 
                  placeholder="Escribe la pregunta aquí..."
                  className="text-lg bg-slate-50 dark:bg-slate-900 dark:text-white dark:border-slate-700 border-slate-200 min-h-[100px] focus:bg-white dark:focus:bg-slate-800 transition-colors"
                />
              </div>
  
              <div className="space-y-3">
                <label className="block text-xs uppercase text-slate-400 dark:text-slate-500 font-bold mb-2">Respuestas (Marca la correcta)</label>
                {activeQ.options.map((opt, oIndex) => (
                  <div key={opt.id} className="flex items-center gap-3 group">
                    <button 
                      onClick={() => setCorrectOption(opt.id)}
                      className={`flex-shrink-0 w-8 h-8 rounded-full border-2 flex items-center justify-center transition-all ${activeQ.correctOptionId === opt.id ? 'border-green-500 bg-green-500 text-white shadow-md shadow-green-200 dark:shadow-none' : 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-transparent hover:border-slate-400'}`}
                    >
                      <CheckCircle size={18} fill="currentColor" className={activeQ.correctOptionId === opt.id ? 'text-white' : ''} />
                    </button>
                    <div className="flex-1 relative">
                      <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 font-mono text-xs font-bold">
                         {String.fromCharCode(65 + oIndex)}
                      </span>
                      <Input 
                        value={opt.text} 
                        onChange={e => updateOption(oIndex, e.target.value)} 
                        placeholder={`Opción ${oIndex + 1}`}
                        className="pl-8 py-3 bg-slate-50 dark:bg-slate-900 dark:text-white dark:border-slate-700 border-slate-200 focus:bg-white dark:focus:bg-slate-800 transition-colors shadow-sm"
                      />
                    </div>
                    <button 
                       onClick={() => {
                          const newOptions = activeQ.options.filter((_, i) => i !== oIndex);
                          updateCurrentQuestion('options', newOptions);
                       }}
                       className="text-slate-300 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <XCircle size={20} />
                    </button>
                  </div>
                ))}
                
                <button 
                  onClick={() => {
                     const newOpt = { id: generateId(), text: '' };
                     updateCurrentQuestion('options', [...activeQ.options, newOpt]);
                  }}
                  className="mt-2 text-sm font-medium text-brand-600 dark:text-brand-400 hover:text-brand-700 flex items-center gap-1 px-2 py-1 rounded hover:bg-brand-50 dark:hover:bg-slate-700 transition-colors w-fit"
                >
                  <Plus size={16}/> Añadir otra opción
                </button>
              </div>
              
              {activeQ.id && currentQIndex < questions.length && (
                 <div className="absolute top-4 right-4">
                    <button 
                      onClick={() => {
                         if(confirm("¿Borrar esta pregunta?")) {
                            const newQs = questions.filter((_, i) => i !== currentQIndex);
                            setQuestions(newQs);
                            // Si borramos la última, vamos a la anterior
                            if(currentQIndex >= newQs.length) setCurrentQIndex(Math.max(0, newQs.length - 1));
                         }
                      }}
                      className="text-slate-300 hover:text-red-500 p-2 hover:bg-red-50 rounded-full"
                    >
                      <Trash2 size={20}/>
                    </button>
                 </div>
              )}
          </div>
        </div>
      )}
    </div>
  );
};

const QuizPage = ({ user }: { user: User }) => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [test, setTest] = useState<Test | undefined>(undefined);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedOptionId, setSelectedOptionId] = useState<string | null>(null);
  const [isAnswerChecked, setIsAnswerChecked] = useState(false);
  const [score, setScore] = useState(0);
  const [answers, setAnswers] = useState<AnswerDetail[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadTest = async () => {
      setLoading(true);
      const loadedTest = await storageService.getTestById(id || '');
      if (loadedTest) {
        setTest(loadedTest);
        const shuffled = [...loadedTest.questions].sort(() => Math.random() - 0.5);
        const fullyShuffled = shuffled.map(q => ({
          ...q,
          options: [...q.options].sort(() => Math.random() - 0.5)
        }));
        setQuestions(fullyShuffled);
      }
      setLoading(false);
    };
    loadTest();
  }, [id]);

  const handleOptionSelect = (optId: string) => {
    if (isAnswerChecked) return;
    setSelectedOptionId(optId);
    
    setIsAnswerChecked(true);
    const currentQ = questions[currentIndex];
    const isCorrect = optId === currentQ.correctOptionId;
    
    if (isCorrect) setScore(prev => prev + 1);

    setAnswers(prev => [...prev, {
      questionId: currentQ.id,
      questionText: currentQ.text,
      selectedOptionId: optId,
      correctOptionId: currentQ.correctOptionId,
      options: currentQ.options,
      isCorrect
    }]);
  };

  const handleNext = () => {
    if (currentIndex < questions.length - 1) {
      setCurrentIndex(prev => prev + 1);
      setSelectedOptionId(null);
      setIsAnswerChecked(false);
    } else {
      finishQuiz();
    }
  };

  const finishQuiz = async () => {
    if (!test) return;
    const result: TestResult = {
      id: generateId(),
      userId: user.uid,
      testId: test.id,
      testTitle: test.title,
      date: Date.now(),
      score: score,
      totalQuestions: answers.length,
      details: answers
    };
    await storageService.saveResult(result);
    navigate(`/history/${result.id}`, { replace: true });
  };

  if (loading) return <div className="flex justify-center h-screen items-center bg-slate-50 dark:bg-slate-900"><Loader2 className="animate-spin text-brand-500" /></div>;
  if (!test) return <div>No se encontró el test.</div>;
  if (questions.length === 0) return <div>Este test no tiene preguntas.</div>;

  const currentQ = questions[currentIndex];
  const labels = ['A', 'B', 'C', 'D', 'E', 'F']; 

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] max-w-2xl mx-auto w-full">
      <header className="flex justify-between items-center mb-6 pt-4">
        <button onClick={() => navigate('/')} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"><XCircle size={28} /></button>
        <div className="bg-white dark:bg-slate-800 px-4 py-1 rounded-full border border-slate-200 dark:border-slate-700 text-sm font-bold text-slate-600 dark:text-slate-300 shadow-sm">
          {currentIndex + 1} / {questions.length}
        </div>
        <button onClick={finishQuiz} className="text-brand-600 dark:text-brand-400 font-bold text-sm hover:underline">Terminar</button>
      </header>

      {/* Aplicar scrollbar-hide aquí */}
      <div className="flex-1 overflow-y-auto scrollbar-hide p-1">
        <Card className="mb-6 border-l-4 border-l-brand-500 shadow-lg bg-white dark:bg-slate-800 dark:border-none">
           <h2 className="text-xl md:text-2xl font-bold text-slate-800 dark:text-white leading-relaxed">{currentQ.text}</h2>
        </Card>

        <div className="space-y-3">
          {currentQ.options.map((opt, index) => {
            let stateStyle = "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 hover:border-slate-300";
            let icon = <div className="w-8 h-8 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400 font-bold flex items-center justify-center text-sm">{labels[index]}</div>;

            if (isAnswerChecked) {
              if (opt.id === currentQ.correctOptionId) {
                 stateStyle = "border-green-500 bg-green-50 dark:bg-green-900/20 ring-1 ring-green-500";
                 icon = <div className="w-8 h-8 rounded-full bg-green-500 text-white flex items-center justify-center"><CheckCircle size={18}/></div>;
              } else if (opt.id === selectedOptionId) {
                 stateStyle = "border-red-500 bg-red-50 dark:bg-red-900/20 ring-1 ring-red-500";
                 icon = <div className="w-8 h-8 rounded-full bg-red-500 text-white flex items-center justify-center"><XCircle size={18}/></div>;
              } else {
                 stateStyle = "opacity-60 border-slate-100 dark:border-slate-700 grayscale";
              }
            } else if (selectedOptionId === opt.id) {
               stateStyle = "border-brand-500 bg-brand-50 dark:bg-brand-900/20";
            }

            return (
              <div 
                key={opt.id}
                onClick={() => handleOptionSelect(opt.id)}
                className={`p-4 rounded-xl border-2 cursor-pointer transition-all flex items-center gap-4 shadow-sm ${stateStyle}`}
              >
                {icon}
                <span className="font-medium text-slate-700 dark:text-slate-200 text-lg">{opt.text}</span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mt-6 pt-4 border-t border-slate-200/50 dark:border-slate-700">
        {isAnswerChecked ? (
           <Button onClick={handleNext} className="w-full py-4 text-xl shadow-xl shadow-brand-500/20 dark:shadow-none rounded-2xl animate-in slide-in-from-bottom-2">
             {currentIndex === questions.length - 1 ? 'Ver Resultados' : 'Siguiente Pregunta'}
           </Button>
        ) : (
          <div className="text-center text-slate-400 text-sm font-medium animate-pulse">Selecciona tu respuesta...</div>
        )}
      </div>
    </div>
  );
};

const HistoryPage = ({ user }: { user: User }) => {
  const [results, setResults] = useState<TestResult[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const load = async () => {
      const data = await storageService.getResults(user.uid);
      setResults(data);
      setLoading(false);
    };
    load();
  }, [user]);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (confirm("¿Borrar este resultado?")) {
      await storageService.deleteResult(id);
      setResults(prev => prev.filter(r => r.id !== id));
    }
  };

  const handleClearHistory = async () => {
    if (confirm("¿Borrar TODO el historial?")) {
        await storageService.deleteAllResults(user.uid);
        setResults([]);
    }
  };

  if (loading) return <div className="flex justify-center pt-20"><Loader2 className="animate-spin text-brand-500"/></div>;

  return (
    <div className="pb-24 max-w-4xl mx-auto">
      <header className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-slate-800 dark:text-white">Historial</h1>
        {results.length > 0 && (
            <button onClick={handleClearHistory} className="text-red-400 hover:text-red-500 text-sm font-medium">
                Borrar todo
            </button>
        )}
      </header>

      {results.length === 0 ? (
        <div className="text-center py-20 bg-white dark:bg-slate-800 rounded-2xl border border-slate-100 dark:border-slate-700">
           <div className="bg-slate-100 dark:bg-slate-700 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4">
              <HistoryIcon size={32} className="text-slate-400 dark:text-slate-500" />
           </div>
           <p className="text-slate-500 dark:text-slate-400">Aún no has completado ningún test.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {results.map(r => (
            <div key={r.id} onClick={() => navigate(`/history/${r.id}`)} className="bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-100 dark:border-slate-700 shadow-sm hover:shadow-md transition-all cursor-pointer flex justify-between items-center group">
               <div>
                  <h3 className="font-bold text-slate-800 dark:text-white">{r.testTitle}</h3>
                  <div className="text-xs text-slate-500 dark:text-slate-400 flex gap-2 mt-1">
                     <span>{new Date(r.date).toLocaleDateString()}</span>
                     <span>•</span>
                     <span className={r.score === r.totalQuestions ? "text-green-500 font-bold" : "text-slate-500"}>
                        {r.score}/{r.totalQuestions} aciertos
                     </span>
                  </div>
               </div>
               <div className="flex items-center gap-3">
                  <div className={`text-lg font-bold ${r.score === r.totalQuestions ? 'text-green-500' : 'text-brand-600 dark:text-brand-400'}`}>
                    {Math.round((r.score / r.totalQuestions) * 100)}%
                  </div>
                  <button onClick={(e) => handleDelete(e, r.id)} className="p-2 text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Trash2 size={18} />
                  </button>
                  <ChevronRight size={18} className="text-slate-300"/>
               </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const ResultViewPage = ({ user }: { user: User }) => {
    const { id } = useParams();
    const navigate = useNavigate();
    const [result, setResult] = useState<TestResult | undefined>(undefined);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const load = async () => {
            if(!id) return;
            const r = await storageService.getResultById(id);
            setResult(r);
            setLoading(false);
        }
        load();
    }, [id]);

    if(loading) return <div className="flex justify-center pt-20"><Loader2 className="animate-spin text-brand-500"/></div>;
    if(!result) return <div className="text-center pt-20">Resultado no encontrado.</div>;

    const percentage = Math.round((result.score / result.totalQuestions) * 100);

    return (
        <div className="pb-24 max-w-3xl mx-auto">
            <header className="flex items-center gap-2 mb-6">
                <button onClick={() => navigate('/history')} className="p-2 hover:bg-white dark:hover:bg-slate-800 rounded-full text-slate-500 dark:text-slate-400"><ArrowLeft /></button>
                <h1 className="font-bold text-xl text-slate-800 dark:text-white">Resultados: {result.testTitle}</h1>
            </header>

            <div className="bg-white dark:bg-slate-800 p-6 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-700 mb-8 text-center">
                <div className="text-sm text-slate-500 dark:text-slate-400 uppercase font-bold tracking-wider mb-2">Puntuación Final</div>
                <div className="text-5xl font-black text-brand-600 dark:text-brand-400 mb-2">{percentage}%</div>
                <div className="text-slate-600 dark:text-slate-300">
                    Has acertado <strong>{result.score}</strong> de <strong>{result.totalQuestions}</strong> preguntas.
                </div>
            </div>

            <div className="space-y-6">
                {result.details.map((detail, idx) => (
                    <div key={idx} className={`bg-white dark:bg-slate-800 rounded-xl border-l-4 p-4 shadow-sm ${detail.isCorrect ? 'border-l-green-500' : 'border-l-red-500'}`}>
                        <div className="flex gap-3 mb-3">
                           <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${detail.isCorrect ? 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400' : 'bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400'}`}>
                             {detail.isCorrect ? <CheckCircle size={14}/> : <XCircle size={14}/>}
                           </div>
                           <h3 className="font-bold text-slate-800 dark:text-slate-200">{detail.questionText}</h3>
                        </div>

                        <div className="space-y-2 pl-9">
                            {detail.options.map(opt => {
                                let style = "border-slate-200 dark:border-slate-700 opacity-60";
                                let icon = null;

                                if (opt.id === detail.selectedOptionId) {
                                    if (detail.isCorrect) {
                                        style = "border-green-500 bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-200 opacity-100";
                                    } else {
                                        style = "border-red-500 bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-200 opacity-100";
                                    }
                                } else if (opt.id === detail.correctOptionId) {
                                     // Mostrar la correcta si falló
                                     if (!detail.isCorrect) {
                                         style = "border-green-500 bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-200 opacity-100";
                                     }
                                }

                                return (
                                    <div key={opt.id} className={`p-3 rounded-lg border text-sm flex justify-between ${style}`}>
                                        <span>{opt.text}</span>
                                        {opt.id === detail.selectedOptionId && (detail.isCorrect ? <CheckCircle size={16}/> : <XCircle size={16}/>)}
                                        {opt.id === detail.correctOptionId && !detail.isCorrect && <CheckCircle size={16}/>}
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

// --- Layout & Router ---

const FabMenu = ({ onAction }: { onAction: (action: 'manual' | 'camera') => void }) => {
  const [isOpen, setIsOpen] = useState(false);

  // Clases para animación de botones hijos: salen desde la posición del botón padre
  const btnCommon = "absolute left-1/2 -translate-x-1/2 w-12 h-12 rounded-full shadow-lg flex items-center justify-center border border-slate-200 dark:border-slate-600 transition-all duration-300 ease-out z-[60]";
  
  return (
    <div className="relative -top-6 h-16 w-16 flex justify-center items-center">
       
       {/* Botón Manual */}
       <button 
         onClick={() => { setIsOpen(false); onAction('manual'); }}
         className={`${btnCommon} ${isOpen ? '-translate-y-[90px] opacity-100' : 'translate-y-0 opacity-0 pointer-events-none'} bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-200 hover:bg-brand-50 hover:text-brand-600 dark:hover:bg-slate-600`}
       >
         <PenTool size={20} />
         <span className={`absolute top-full mt-1 bg-white/80 dark:bg-slate-800/80 backdrop-blur px-2 rounded text-[10px] font-bold text-slate-600 dark:text-slate-300 transition-opacity duration-300 ${isOpen ? 'opacity-100' : 'opacity-0'}`}>Manual</span>
       </button>

       {/* Botón Escanear - Más separado */}
       <button 
         onClick={() => { setIsOpen(false); onAction('camera'); }}
         className={`${btnCommon} ${isOpen ? '-translate-y-[180px] opacity-100' : 'translate-y-0 opacity-0 pointer-events-none'} bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-200 hover:bg-brand-50 hover:text-brand-600 dark:hover:bg-slate-600`}
       >
         <Camera size={20} />
         <span className={`absolute top-full mt-1 bg-white/80 dark:bg-slate-800/80 backdrop-blur px-2 rounded text-[10px] font-bold text-slate-600 dark:text-slate-300 transition-opacity duration-300 ${isOpen ? 'opacity-100' : 'opacity-0'}`}>Escanear</span>
       </button>

       {/* Botón Principal (+) */}
       <button 
         onClick={() => setIsOpen(!isOpen)} 
         className={`
           relative z-[60] w-16 h-16 rounded-full shadow-xl flex items-center justify-center transition-all duration-300
           ${isOpen ? 'bg-slate-800 dark:bg-slate-600 rotate-45 scale-90' : 'bg-brand-600 hover:scale-105 hover:bg-brand-700'}
           text-white
         `}
       >
         <Plus size={32} />
       </button>
       
       {/* Overlay para cerrar al hacer click fuera - FIXED para no afectar a la nav bar */}
       {isOpen && (
         <div className="fixed inset-0 z-[50] bg-black/10 backdrop-blur-[1px]" onClick={() => setIsOpen(false)}></div>
       )}
    </div>
  );
};

const Layout = ({ children, user }: { children?: React.ReactNode, user: User }) => {
  const location = useLocation();
  const navigate = useNavigate();
  
  if (location.pathname.startsWith('/quiz/')) {
    return <div className="max-w-4xl mx-auto min-h-screen p-4">{children}</div>;
  }

  return (
    <div className="w-full min-h-screen flex flex-col">
      <main className="flex-1 p-4 w-full">
        {children}
      </main>
      
      <nav className="bg-white/90 dark:bg-slate-900/90 backdrop-blur-md border-t border-slate-200 dark:border-slate-800 fixed bottom-0 left-0 right-0 z-40 shadow-lg pb-safe">
        <div className="max-w-md mx-auto flex justify-around items-center h-16 px-4 relative z-50">
          <button 
            onClick={() => navigate('/')} 
            className={`flex flex-col items-center p-2 rounded-xl transition-colors w-16 ${location.pathname === '/' ? 'text-brand-600 bg-brand-50 dark:bg-slate-800 dark:text-brand-400' : 'text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300'}`}
          >
            <HomeIcon size={24} />
            <span className="text-[10px] font-bold mt-1">Inicio</span>
          </button>
          
          <FabMenu onAction={(action) => navigate(`/editor?mode=${action}`)} />
          
          <button 
            onClick={() => navigate('/history')} 
            className={`flex flex-col items-center p-2 rounded-xl transition-colors w-16 ${location.pathname.startsWith('/history') ? 'text-brand-600 bg-brand-50 dark:bg-slate-800 dark:text-brand-400' : 'text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300'}`}
          >
            <HistoryIcon size={24} />
            <span className="text-[10px] font-bold mt-1">Historial</span>
          </button>
        </div>
      </nav>
    </div>
  );
};

const App = () => {
  const { user, loading } = useAuth();
  const { isDark } = useDarkMode(); // Initialize dark mode hook

  if (loading) {
     return <div className="h-screen flex items-center justify-center bg-brand-50 dark:bg-slate-900"><Loader2 className="animate-spin text-brand-500" size={32}/></div>;
  }

  if (!user) {
    return <LoginPage />;
  }

  return (
    <HashRouter>
      <Layout user={user}>
        <Routes>
          <Route path="/" element={<HomePage user={user} />} />
          <Route path="/editor" element={<EditorPage user={user} />} />
          <Route path="/editor/:id" element={<EditorPage user={user} />} />
          <Route path="/quiz/:id" element={<QuizPage user={user} />} />
          <Route path="/history" element={<HistoryPage user={user} />} />
          <Route path="/history/:id" element={<ResultViewPage user={user} />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/share/:id" element={<SharePage user={user} />} />
        </Routes>
      </Layout>
    </HashRouter>
  );
};

export default App;