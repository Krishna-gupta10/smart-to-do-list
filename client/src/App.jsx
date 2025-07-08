import { useState, useEffect } from 'react';
import { Send, Sun, Moon, Calendar, CheckCircle, Clock, User } from 'lucide-react';

function App() {
  const [prompt, setPrompt] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [isAuthorized, setIsAuthorized] = useState(false);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [darkMode, setDarkMode] = useState(false);
  const [showIntro, setShowIntro] = useState(true);
  const [authLoading, setAuthLoading] = useState(false);

  const API_BASE_URL = 'https://smart-to-do-list-4bi2.onrender.com';

  // Check auth status on component mount
  useEffect(() => {
    checkAuthStatus();
  }, []);

  // Listen for OAuth messages from popup
  useEffect(() => {
    const handleMessage = (event) => {
      const backendOrigin = new URL(API_BASE_URL).origin;
      if (event.origin !== backendOrigin) {
        return;
      }

      if (event.data.type === 'oauth_success') {
        console.log('OAuth success message received:', event.data);
        setIsAuthorized(true);
        setAuthLoading(false);
        // Double-check auth status
        setTimeout(() => {
          checkAuthStatus();
        }, 1000);
      } else if (event.data.type === 'oauth_error') {
        console.error('OAuth error:', event.data.error);
        setAuthLoading(false);
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [API_BASE_URL]);

  const checkAuthStatus = async () => {
    try {
      console.log('Checking auth status...');
      const res = await fetch(`${API_BASE_URL}/check-auth`, {
        method: 'GET',
      });
      const data = await res.json();
      console.log('Auth status response:', data);
      
      setIsAuthorized(data.authorized || false);
      
      if (data.authorized) {
        console.log('User is authorized');
      } else {
        console.log('User is not authorized');
      }
    } catch (error) {
      console.error('Error checking auth:', error);
      setIsAuthorized(false);
    }
    setCheckingAuth(false);
  };

  const handleAuthorize = async () => {
    setAuthLoading(true);
    console.log('Starting OAuth flow...');
    
    try {
      const res = await fetch(`${API_BASE_URL}/authorize`);
      const data = await res.json();
      
      if (data.auth_url) {
        console.log('Opening OAuth popup...');
        const authWindow = window.open(
          data.auth_url, 
          'oauth', 
          'width=600,height=700,scrollbars=yes,resizable=yes,left=' + 
          (window.screen.width / 2 - 300) + ',top=' + (window.screen.height / 2 - 350)
        );
        
        if (!authWindow) {
          console.error('Failed to open popup window');
          setAuthLoading(false);
          return;
        }
        
        // Poll for window closure as a fallback
        const checkClosed = setInterval(() => {
          if (authWindow.closed) {
            console.log('Popup window closed');
            clearInterval(checkClosed);
            setAuthLoading(false);
            
            // Check auth status after window closes (fallback)
            setTimeout(() => {
              checkAuthStatus();
            }, 1000);
          }
        }, 1000);
        
      } else {
        console.error('No auth URL received from backend');
        setAuthLoading(false);
      }
    } catch (error) {
      console.error('Error getting auth URL:', error);
      setAuthLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!prompt.trim()) return;
    
    const userMessage = { type: 'user', content: prompt };
    setMessages(prev => [...prev, userMessage]);
    setPrompt('');
    setLoading(true);
    
    try {
      const res = await fetch(`${API_BASE_URL}/parse-and-execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ task: prompt }),
      });
      
      if (res.status === 401) {
        // User is not authenticated
        setIsAuthorized(false);
        const errorMessage = { type: 'assistant', content: { error: 'Authentication required. Please connect your Google account.' } };
        setMessages(prev => [...prev, errorMessage]);
        setLoading(false);
        return;
      }
      
      const data = await res.json();
      const formattedResponse = formatMessage(data);
      const assistantMessage = { type: 'assistant', content: formattedResponse };
      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Error:', error);
      const errorMessage = { type: 'assistant', content: { error: 'Failed to fetch response' } };
      setMessages(prev => [...prev, errorMessage]);
    }
    setLoading(false);
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const formatMessage = (response) => {
    // Handle error messages
    if (response.error) {
      return `❌ Error: ${response.error}`;
    }

    // Handle different response types and extract meaningful messages
    if (response.status && response.message) {
      return response.message;
    }

    // Handle specific action responses
    if (response.status === "Scheduled ✅" && response.event) {
      return response.message || "Meeting scheduled successfully!";
    }

    if (response.status === "Schedule ✅" && response.events) {
      if (response.events.length === 0) {
        return "Your schedule is free for the requested time.";
      }
      const eventList = response.events.map(event => 
        `• ${event.summary} (${new Date(event.start).toLocaleString()})`
      ).join('\n');
      return `Here's your schedule:\n${eventList}`;
    }

    if (response.status === "Free Slots ✅" && response.slots) {
      if (response.slots.length === 0) {
        return "No free slots available for the requested time.";
      }
      const slotList = response.slots.map(slot => 
        `• ${new Date(slot.start).toLocaleString()} - ${new Date(slot.end).toLocaleString()}`
      ).join('\n');
      return `Available time slots:\n${slotList}`;
    }

    if (response.status === "Summary ✅" && response.emails) {
      if (response.emails.length === 0) {
        return "No emails found for the specified criteria.";
      }
      const emailList = response.emails.map(email => 
        `• From: ${email.sender}\n  Subject: ${email.subject}\n  Summary: ${email.summary}`
      ).join('\n\n');
      return `Email Summary:\n${emailList}`;
    }

    if (response.status === "Email Sent ✅") {
      return "Email sent successfully!";
    }

    if (response.status === "Unread ✅" && response.emails) {
      if (response.emails.length === 0) {
        return "No unread emails found.";
      }
      const emailList = response.emails.map(email => 
        `• From: ${email.sender}\n  Subject: ${email.subject}`
      ).join('\n\n');
      return `Unread emails:\n${emailList}`;
    }

    if (response.status === "Results ✅" && response.emails) {
      if (response.emails.length === 0) {
        return "No emails found matching your search.";
      }
      const emailList = response.emails.map(email => 
        `• From: ${email.sender}\n  Subject: ${email.subject}\n  Date: ${new Date(email.date).toLocaleString()}`
      ).join('\n\n');
      return `Search results:\n${emailList}`;
    }

    if (response.status === "Need Info ❓") {
      return response.message || "I need more information to proceed.";
    }

    if (response.status === "Message 💬") {
      return response.message || "I received your message.";
    }

    // Fallback for any other response
    if (response.message) {
      return response.message;
    }

    return "Task processed successfully!";
  };

  const renderMessage = (message, index) => {
    if (message.type === 'user') {
      return (
        <div key={index} className="flex justify-end mb-6">
          <div className={`max-w-[80%] rounded-2xl px-4 py-3 ${
            darkMode 
              ? 'bg-blue-600 text-white' 
              : 'bg-blue-500 text-white'
          }`}>
            {message.content}
          </div>
        </div>
      );
    }

    const formattedMessage = formatMessage(message.content);
    return (
      <div key={index} className="flex justify-start mb-6">
        <div className={`max-w-[80%] rounded-2xl px-4 py-3 ${
          darkMode 
            ? 'bg-gray-800 border border-gray-700 text-gray-200' 
            : 'bg-gray-100 border border-gray-200 text-gray-800'
        }`}>
          <div className="whitespace-pre-line">
            {formattedMessage}
          </div>
        </div>
      </div>
    );
  };

  // Intro Animation Component
  const IntroAnimation = () => {
    const [step, setStep] = useState(0);
    const [typedText, setTypedText] = useState('');
    const [strikePosition, setStrikePosition] = useState(0);
    
    const fullText = "Having or showing a quick-witted intelligence";
    
    useEffect(() => {
      const timer1 = setTimeout(() => setStep(1), 1000);
      
      // Start typing animation
      const startTyping = setTimeout(() => {
        setStep(2);
        let currentIndex = 0;
        const typingInterval = setInterval(() => {
          if (currentIndex < fullText.length) {
            setTypedText(fullText.substring(0, currentIndex + 1));
            currentIndex++;
          } else {
            clearInterval(typingInterval);
            // Start strike-through animation
            setTimeout(() => {
              setStep(3);
              let strikeIndex = 0;
              const strikeInterval = setInterval(() => {
                if (strikeIndex <= fullText.length) {
                  setStrikePosition(strikeIndex);
                  strikeIndex++;
                } else {
                  clearInterval(strikeInterval);
                  // Show "ME" after strike-through is complete
                  setTimeout(() => {
                    setStep(4);
                    setTimeout(() => {
                      setStep(5);
                      setTimeout(() => setShowIntro(false), 500);
                    }, 1000);
                  }, 500);
                }
              }, 30);
            }, 300);
          }
        }, 50);
      }, 2000);
      
      return () => {
        clearTimeout(timer1);
        clearTimeout(startTyping);
      };
    }, []);

    return (
      <div className={`fixed inset-0 z-50 flex items-center justify-center bg-gray-900 transition-all duration-500 ${
        step === 5 ? 'opacity-0' : 'opacity-100'
      }`}>
        <div className="text-center max-w-2xl px-8">
          <h1 className={`text-6xl font-bold mb-8 transition-all duration-1000 text-white ${
            step >= 0 ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'
          }`}>
            What is Smart?
          </h1>
          
          <div className="relative">
            <p className={`text-xl leading-relaxed transition-all duration-1000 text-gray-300 ${
              step >= 1 ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'
            }`}>
              <span className="inline-block">
                {typedText.split('').map((char, index) => (
                  <span
                    key={index}
                    className={`inline-block relative ${
                      step >= 3 && index < strikePosition ? 'line-through' : ''
                    }`}
                    style={{
                      textDecorationColor: '#ef4444',
                      textDecorationThickness: '2px'
                    }}
                  >
                    {char === ' ' ? '\u00A0' : char}
                  </span>
                ))}
              </span>
              {step === 2 && (
                <span className="inline-block w-0.5 h-6 bg-gray-300 ml-1 animate-pulse"></span>
              )}
            </p>
          </div>
          
          <div className={`mt-12 text-8xl font-bold bg-gradient-to-r from-blue-500 to-purple-600 bg-clip-text text-transparent transition-all duration-1000 ${
            step >= 4 ? 'opacity-100 scale-100' : 'opacity-0 scale-75'
          }`}>
            ME
          </div>
        </div>
      </div>
    );
  };

  if (showIntro) {
    return <IntroAnimation />;
  }

  if (checkingAuth) {
    return (
      <div className={`min-h-screen flex items-center justify-center ${
        darkMode ? 'bg-gray-900' : 'bg-white'
      }`}>
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className={darkMode ? 'text-gray-300' : 'text-gray-600'}>
            Checking authentication...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={`min-h-screen transition-colors duration-300 ${
      darkMode ? 'bg-gray-900' : 'bg-white'
    }`}>
      {/* Header */}
      <header className={`sticky top-0 z-10 border-b backdrop-blur-sm ${
        darkMode 
          ? 'bg-gray-900/80 border-gray-700' 
          : 'bg-white/80 border-gray-200'
      }`}>
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center">
              <span className="text-white font-bold text-sm">P</span>
            </div>
            <h1 className={`text-xl font-semibold ${
              darkMode ? 'text-white' : 'text-gray-900'
            }`}>
              Evernote
            </h1>
          </div>
          
          <div className="flex items-center gap-3">
            {isAuthorized && (
              <div className="flex items-center gap-2 text-sm text-green-600">
                <CheckCircle size={16} />
                <span>Connected</span>
              </div>
            )}
            <button
              onClick={() => setDarkMode(!darkMode)}
              className={`p-2 rounded-lg transition-colors ${
                darkMode 
                  ? 'hover:bg-gray-800 text-gray-300' 
                  : 'hover:bg-gray-100 text-gray-600'
              }`}
            >
              {darkMode ? <Sun size={20} /> : <Moon size={20} />}
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-6">
        {!isAuthorized ? (
          <div className="flex items-center justify-center min-h-[60vh]">
            <div className={`text-center p-8 rounded-2xl max-w-md ${
              darkMode 
                ? 'bg-gray-800 border border-gray-700' 
                : 'bg-gray-50 border border-gray-200'
            }`}>
              <Calendar className="mx-auto mb-4 text-blue-500" size={48} />
              <h2 className={`text-2xl font-semibold mb-4 ${
                darkMode ? 'text-white' : 'text-gray-900'
              }`}>
                Connect Your Google Account
              </h2>
              <p className={`mb-6 ${
                darkMode ? 'text-gray-300' : 'text-gray-600'
              }`}>
                Authorize with Google to access your calendar and manage your tasks.
              </p>
              <button 
                onClick={handleAuthorize}
                disabled={authLoading}
                className={`bg-white hover:bg-gray-50 text-gray-900 font-medium py-3 px-6 rounded-lg transition-colors duration-200 border border-gray-300 shadow-sm flex items-center gap-3 ${
                  authLoading ? 'opacity-50 cursor-not-allowed' : ''
                }`}
              >
                {authLoading ? (
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-gray-900"></div>
                ) : (
                  <svg width="20" height="20" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                  </svg>
                )}
                {authLoading ? 'Connecting...' : 'Continue with Google'}
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* Messages */}
            <div className="mb-6">
              {messages.length === 0 ? (
                <div className="text-center py-12">
                  <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center mx-auto mb-4">
                    <span className="text-white font-bold text-2xl">P</span>
                  </div>
                  <h2 className={`text-2xl font-semibold mb-2 ${
                    darkMode ? 'text-white' : 'text-gray-900'
                  }`}>
                    How can I help you today?
                  </h2>
                  <p className={`text-sm ${
                    darkMode ? 'text-gray-400' : 'text-gray-600'
                  }`}>
                    I can help you schedule meetings, check your calendar, and manage your tasks.
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  {messages.map((message, index) => renderMessage(message, index))}
                </div>
              )}
              
              {loading && (
                <div className="flex justify-start mb-6">
                  <div className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                    darkMode 
                      ? 'bg-gray-800 border border-gray-700' 
                      : 'bg-gray-100 border border-gray-200'
                  }`}>
                    <div className="flex items-center gap-2">
                      <div className="flex space-x-1">
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"></div>
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                      </div>
                      <span className={`text-sm ${
                        darkMode ? 'text-gray-400' : 'text-gray-600'
                      }`}>
                        Thinking...
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Input */}
            <div className={`sticky bottom-0 p-4 rounded-2xl border ${
              darkMode 
                ? 'bg-gray-800 border-gray-700' 
                : 'bg-white border-gray-200'
            } shadow-lg`}>
              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder="Message Evernote..."
                    rows="1"
                    className={`w-full resize-none border-0 bg-transparent focus:outline-none text-sm leading-6 ${
                      darkMode ? 'text-white placeholder-gray-400' : 'text-gray-900 placeholder-gray-500'
                    }`}
                    style={{ minHeight: '24px', maxHeight: '120px' }}
                    disabled={loading}
                  />
                </div>
                <button
                  onClick={handleSubmit}
                  disabled={loading || !prompt.trim()}
                  className={`p-2 rounded-lg transition-colors ${
                    loading || !prompt.trim()
                      ? 'bg-gray-300 cursor-not-allowed'
                      : 'bg-blue-600 hover:bg-blue-700'
                  }`}
                >
                  <Send size={16} className="text-white" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default App;