import { useState, useEffect } from 'react';
import axios from 'axios';
import { ShieldAlert, Activity, CheckCircle2, AlertTriangle, RefreshCw } from 'lucide-react';

const API_URL = 'http://localhost:30000/api/v1';

interface Incident {
  id: string;
  timestamp: string;
  affected_service: string;
  severity: string;
  failure_type: string;
  status: string;
  hypothesis?: string;
  proposed_action?: string;
}

function App() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState('unknown');

  const fetchIncidents = async () => {
    try {
      const res = await axios.get(`${API_URL}/incidents`);
      setIncidents(res.data.incidents || []);
    } catch (err) {
      console.error("Failed to fetch incidents", err);
    }
  };

  const fetchHealth = async () => {
    try {
      const res = await axios.get(`http://localhost:30000/health`);
      setHealth(res.data.status);
    } catch {
      setHealth('offline');
    }
  };

  const refreshAll = async () => {
    setLoading(true);
    await Promise.all([fetchIncidents(), fetchHealth()]);
    setLoading(false);
  };

  useEffect(() => {
    refreshAll();
    const interval = setInterval(refreshAll, 5000);
    return () => clearInterval(interval);
  }, []);

  const triggerDetection = async () => {
    await axios.post(`${API_URL}/trigger_detection`);
    refreshAll();
  };

  const orchestrateIncident = async (id: string) => {
    await axios.post(`${API_URL}/orchestrate`, { incident_id: id });
    refreshAll();
  };

  return (
    <div className="min-h-screen p-8 max-w-6xl mx-auto">
      <header className="flex items-center justify-between mb-8 pb-4 border-b">
        <div className="flex items-center gap-3">
          <ShieldAlert className="w-8 h-8 text-blue-600" />
          <h1 className="text-2xl font-bold text-gray-800">AIOps Control Platform</h1>
        </div>
        <div className="flex items-center gap-4">
          <span className={`px-3 py-1 rounded-full text-sm font-semibold flex items-center gap-2 ${health === 'ok' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
            {health === 'ok' ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
            Backend: {health.toUpperCase()}
          </span>
          <button 
            onClick={refreshAll}
            className={`p-2 rounded-full hover:bg-gray-200 transition-colors ${loading ? 'animate-spin text-blue-500' : 'text-gray-600'}`}
          >
            <RefreshCw className="w-5 h-5" />
          </button>
        </div>
      </header>

      <main className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-2 space-y-6">
          <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold flex items-center gap-2">
                <Activity className="w-5 h-5 text-gray-500" />
                Active Incidents
              </h2>
              <button 
                onClick={triggerDetection}
                className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-sm font-medium rounded-lg transition-colors"
              >
                Run Detection Cycle
              </button>
            </div>
            
            {incidents.length === 0 ? (
              <div className="text-center py-12 text-gray-500 bg-gray-50 rounded-lg border border-dashed">
                No active incidents detected. All systems green.
              </div>
            ) : (
              <div className="space-y-4">
                {incidents.map(inc => (
                  <div key={inc.id} className="border rounded-lg p-4 bg-gray-50 flex flex-col gap-3">
                    <div className="flex justify-between items-start">
                      <div>
                        <h3 className="font-bold text-lg text-gray-900">{inc.id}</h3>
                        <p className="text-sm text-gray-500">{new Date(inc.timestamp).toLocaleString()}</p>
                      </div>
                      <span className={`px-2 py-1 text-xs font-bold rounded uppercase
                        ${inc.status === 'DETECTED' ? 'bg-red-100 text-red-700' : 
                          inc.status === 'RESOLVED' ? 'bg-green-100 text-green-700' : 
                          'bg-blue-100 text-blue-700'}`}
                      >
                        {inc.status}
                      </span>
                    </div>
                    
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div><span className="font-semibold text-gray-700">Service:</span> {inc.affected_service}</div>
                      <div><span className="font-semibold text-gray-700">Failure:</span> {inc.failure_type}</div>
                      <div className="col-span-2">
                        <span className="font-semibold text-gray-700">Hypothesis:</span> {inc.hypothesis || 'Waiting for RCA...'}
                      </div>
                      <div className="col-span-2">
                        <span className="font-semibold text-gray-700">Action:</span> {inc.proposed_action || 'N/A'}
                      </div>
                    </div>

                    {inc.status === 'DETECTED' && (
                      <button 
                        onClick={() => orchestrateIncident(inc.id)}
                        className="mt-2 w-full py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded transition-colors"
                      >
                        Trigger AI Healing (Orchestrate)
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 h-full">
            <h2 className="text-xl font-semibold mb-4">System Status</h2>
            <div className="space-y-4">
              <div className="flex justify-between items-center p-3 bg-gray-50 rounded">
                <span className="font-medium text-gray-700">Target App (RAG)</span>
                <span className="w-3 h-3 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]"></span>
              </div>
              <div className="flex justify-between items-center p-3 bg-gray-50 rounded">
                <span className="font-medium text-gray-700">Observability Stack</span>
                <span className="w-3 h-3 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]"></span>
              </div>
              <div className="flex justify-between items-center p-3 bg-gray-50 rounded">
                <span className="font-medium text-gray-700">Chaos Engine</span>
                <span className="w-3 h-3 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]"></span>
              </div>
              <div className="flex justify-between items-center p-3 bg-gray-50 rounded">
                <span className="font-medium text-gray-700">LangGraph Orchestrator</span>
                <span className="w-3 h-3 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]"></span>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
