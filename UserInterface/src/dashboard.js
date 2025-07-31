// 👇 Updated DashboardFetcher with typewriter text, Baymax, Eve, chat-style query history, and top-right Eve toggle
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import LoginForm from './components/LoginForm';
import { Modal } from 'react-bootstrap';
import './App.css';
import toast from 'react-hot-toast';
import { DotLottieReact } from '@lottiefiles/dotlottie-react';

const DashboardFetcher = () => {
  const [query, setQuery] = useState('');
  const [dashboardHTML, setDashboardHTML] = useState('');
  const [s3Link, setS3Link] = useState('');
  const [error, setError] = useState(null);
  const [isloading, setIsloading] = useState(false);
  const [isModalView, setModalView] = useState(false);
  const [values, setValues] = useState({ email: '', password: '' });
  const [apiKey, setApiKey] = useState(() => sessionStorage.getItem("apiKey") || "");
  const [addbuttontohtml, setAddbuttontohtml] = useState('');
  const [isExpand, setIsExpand] = useState(false);
  const [chatHistory, setChatHistory] = useState([]);
  const [showChatHistory, setShowChatHistory] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const isValidQuery = (text) => {
    const wordCount = text.trim().split(/\s+/).filter(word => word.length > 2).length;
    const hasRealText = /[a-zA-Z]/.test(text);
    return text.length >= 15 && wordCount >= 3 && hasRealText;
  };

  useEffect(() => {
    const sync = () => setApiKey(sessionStorage.getItem("apiKey") || "");
    window.addEventListener("sessionStorageUpdated", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("sessionStorageUpdated", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  useEffect(() => {
    const listener = (event) => {
      if (event.data === 'expandClicked') setIsExpand(true);
      else if (event.data === 'collapseClicked') setIsExpand(false);
    };
    window.addEventListener('message', listener);
    return () => window.removeEventListener('message', listener);
  }, []);

  useEffect(() => {
    if (!dashboardHTML.includes('<button id="expand-button">')) {
      setAddbuttontohtml(dashboardHTML);
      return;
    }
    const str = `
      <button id="expand-button" onclick="toggleExpand()">
        <img src="https://ad-vise.ai/static/media/preview.8100a3e892e484e16cfbe8dfc4506719.svg"/>
      </button>
      <script>
        let isExpanded = ${isExpand};
        function toggleExpand() {
          isExpanded = !isExpanded;
          window.parent.postMessage(isExpanded ? 'expandClicked' : 'collapseClicked', '*');
        }
      </script>`;
    setAddbuttontohtml(dashboardHTML.replace('<button id="expand-button">', str));
  }, [dashboardHTML, isExpand]);

  useEffect(() => {
    const lines = ["Welcome", "to", "Agentic AI Dashboard"];
    const element = document.getElementById("typewriter");
    let lineIndex = 0;
    let charIndex = 0;
    let currentLines = ["", "", ""];
    let interval;

    function typeWriter() {
      if (lineIndex < lines.length) {
        currentLines[lineIndex] += lines[lineIndex].charAt(charIndex);
        charIndex++;
        if (charIndex === lines[lineIndex].length) {
          charIndex = 0;
          lineIndex++;
        }
        const finalText = currentLines.map((line, i) =>
          i === lineIndex ? line + '<span class="cursor">|</span>' : line
        );
        element.innerHTML = finalText.join('<br>');
      } else {
        clearInterval(interval);
      }
    }

    if (!apiKey && element) {
      element.innerHTML = '';
      interval = setInterval(typeWriter, 125);
    }
    return () => clearInterval(interval);
  }, [apiKey]);

  const fetchDashboard = async (attempt = 1) => {
    try {
      setIsloading(true);
      setError(null);
      setErrorMsg('');
      setDashboardHTML('');
      setShowChatHistory(false);
      setS3Link('');
      if (!isValidQuery(query)) {
        setErrorMsg("⚠️ Please enter a meaningful user query.");
        setIsloading(false);
        return;
      }

      const response = await axios.post(
        'https://b1z29r84v1.execute-api.us-east-1.amazonaws.com/prod/dashboard',
        JSON.stringify({ query }),
        {
          headers: {
            'Content-Type': 'application/json',
            'x-api-key': apiKey
          }
        }
      );

      if (response.data && response.data.body) {
        const parsed = JSON.parse(response.data.body);
  
        if (parsed.dashboard_html) {
          setDashboardHTML(parsed.dashboard_html);
          setShowChatHistory(false);
        }
  
        if (parsed.dashboard_url) {
          setS3Link(parsed.dashboard_url);
        }
  
        const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        setChatHistory(prev => [...prev, { user: query, timestamp }]);
  
        // 🚨 Retry if no dashboard output returned
        if (!parsed.dashboard_html && !parsed.dashboard_url && attempt < 2) {
          console.warn(`⚠️ No output on attempt ${attempt}. Retrying...`);
          setTimeout(() => fetchDashboard(attempt + 1), 3000);
        } else if (!parsed.dashboard_html && !parsed.dashboard_url) {
          setError("Dashboard generation failed. Please try again.");
        }
  
      } else {
        setError("No data returned from API.");
      }
  
    } catch (err) {
      console.error(err);
      if (attempt < 2) {
        console.warn(`⚠️ API error on attempt ${attempt}. Retrying...`);
        setTimeout(() => fetchDashboard(attempt + 1), 3000);
      } else {
        setError("Error fetching dashboard: " + err.message);
      }
  
    } finally {
      setIsloading(false);
    }
  };
  const handleCloseModal = () => setModalView(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!values.password) return toast.error("Please enter an API key");
    try {
      const res = await fetch('https://yjfimvn8y4.execute-api.us-east-1.amazonaws.com/vadilation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ x_api_key: values.password })
      });
      const data = await res.json();
      if (res.status === 200 && data.authorized) {
        sessionStorage.setItem('apiKey', values.password);
        setApiKey(values.password);
        setModalView(false);
        toast.success("API key validated!");
      } else toast.error("Invalid API key");
    } catch (err) {
      toast.error("Error validating API key");
    }
  };

  const handleLogout = () => {
    sessionStorage.removeItem('apiKey');
    setApiKey('');
    setQuery('');
    setDashboardHTML('');
    setS3Link('');
    setChatHistory([]);
    setError(null);
    setShowChatHistory(false);
    toast("Logged out successfully");
  };

  return (
    <>
      {apiKey && (
        <div style={{ position: 'absolute', top: 10, right: 20 }}>
          <button onClick={handleLogout} className="logout-btn">Logout</button>
        </div>
      )}

      {apiKey &&  (
        <div className="eve-chat-icon" onClick={() => setShowChatHistory(!showChatHistory)}>
          <DotLottieReact
            src="https://lottie.host/9afde054-2e2f-4e71-ac8e-1f70f3531c1d/KMDRPNDnxq.lottie"
            loop autoplay style={{ width: 80, height: 80 }}
          />
          <div className="eve-tooltip">Your queries are safe with me!</div>
        </div>
      )}

      <div className="dashboard-container">
        {!apiKey && (
          <>
            <div className="baymax-container">
              <DotLottieReact
                src="https://lottie.host/b262b2c3-5239-42ca-901d-4cdd71b9f584/6lX5j1ouXQ.lottie"
                loop autoplay style={{ width: 150, height: 150 }}
              />
            </div>
            <h1 id="typewriter" className="typewriter-text"></h1>
            <button onClick={() => setModalView(true)} className="key-btn" style={{ marginTop: '20px' }}>
              Enter API Key
            </button>
          </>
        )}

        {apiKey && (
          <>
            <div className="textarea-container">
              <textarea
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setErrorMsg('');  // 🧼 Clear error message on typing
                }}
                placeholder="Enter your question here..."
                className="query-box"
                rows="4"
              />
            </div>
            {errorMsg && (
              <p style={{
                color: '#D8000C',
                backgroundColor: '#FFBABA',
                padding: '8px',
                borderRadius: '5px',
                marginTop: '8px',
                fontWeight: 'bold'
              }}>
                {errorMsg}
              </p>
            )}
          
            <div className="button-row">
            <button onClick={() => fetchDashboard(1)} className="generate-btn" disabled={isloading}>Generate Dashboard</button>
              <button onClick={() => { setQuery(''); setDashboardHTML(''); setS3Link(''); setError(null);setErrorMsg(''); }} className="Clear-btn">
                Clear Dashboard
              </button>
            </div>
          </>
        )}

        {isloading && (
          <div style={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', backgroundColor: 'rgba(150,110,110,0.7)', backdropFilter: 'blur(4px)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
            <DotLottieReact src="https://lottie.host/04399171-a86a-4517-a43f-9ef060decb69/l4nm4ckO48.lottie" loop autoplay style={{ width: 500, height: 500 }} />
            <p style={{ marginTop: '0px', fontSize: '25px', fontStyle: 'italic', color: '#000000' }}>Generating your dashboard...</p>
          </div>
        )}

        

        {/* 💬 Chat History Toggle Section */}
        {showChatHistory && (
          <div className="chat-container">
            {chatHistory.length === 0 ? (
              <div className="chat-bubble info-bubble">No queries yet.</div>
            ) : (
              chatHistory.map((entry, i) => (
                <div key={i} className="chat-bubble-wrapper">
                  <div className="chat-bubble user-bubble">
                    {entry.user}
                    <time className="timestamp">{entry.timestamp}</time>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
         
        {dashboardHTML && (
          <div style={{ marginTop: '30px', width: isExpand ? '100%' : '80%', transition: 'width 0.3s ease-in-out' }}>
            <h2 style={{ textAlign: 'center', marginTop: '30px' }}>Dashboard View</h2>
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', width: '100%' }}>
              <iframe
                title="Cyber Dashboard"
                srcDoc={addbuttontohtml}
                sandbox="allow-scripts allow-same-origin allow-modals allow-downloads"
                style={{ width: '100%', height: '650px', border: '1px solid #ccc', backgroundColor: '#fff', borderRadius: '8px' }}
              />
              {s3Link && (
                <p style={{ marginTop: '15px' }}>
                  🔗 <a href={s3Link} target="_blank" rel="noopener noreferrer">Open in new tab</a>
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      <Modal show={isModalView} onHide={handleCloseModal} keyboard={false} className="apiKeyInTakeModal modal fade" centered>
        <Modal.Body>
          <LoginForm values={values} setValues={setValues} handleSubmit={handleSubmit} />
        </Modal.Body>
      </Modal>
    </>
  );
};

export default DashboardFetcher;