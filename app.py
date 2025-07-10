import os, sqlite3, json, torch
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, g
from typing import Dict, List, Optional
from sentence_transformers import SentenceTransformer
from pokemon_research import PokemonResearchAgent as Agent_

app = Flask(__name__)
app.config['DATABASE'] = 'chatbot.db'
app.config['ENCODER'] = SentenceTransformer("all-MiniLM-L6-v2")

# Database initialization
def init_db():
    """Initialize the database with required tables"""
    with app.app_context():
        db = get_db()
        db.executescript('''
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                title TEXT DEFAULT 'New Chat'
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                reasoning TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT,
                FOREIGN KEY (session_id) REFERENCES chat_sessions (session_id)
            );

            CREATE TABLE IF NOT EXISTS research_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_vector TEXT,
                query TEXT NOT NULL,
                results TEXT NOT NULL,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                access_count INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_research_cache_hash ON research_cache(query_hash);
        ''')
        db.commit()

def get_db():
    """Get database connection"""
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db

def app_close_db(error):
    """Close database connection"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

@app.teardown_appcontext
def close_db(error):
    app_close_db(error)

# Utility functions
def generate_session_id():
    """Generate a unique session ID"""
    import uuid
    return str(uuid.uuid4())

class ChatHistory:
    """Manage chat history operations"""
    
    @staticmethod
    def create_session(title: str = "New Chat") -> str:
        """Create a new chat session"""
        session_id = generate_session_id()
        db = get_db()
        db.execute(
            'INSERT INTO chat_sessions (session_id, title) VALUES (?, ?)',
            (session_id, title)
        )
        db.commit()
        return session_id
    
    @staticmethod
    def get_session_history(session_id: str) -> List[Dict]:
        """Get chat history for a session"""
        db = get_db()
        messages = db.execute(
            'SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp',
            (session_id,)
        ).fetchall()
        
        return [dict(msg) for msg in messages]
    
    @staticmethod
    def add_message(session_id: str, role: str, content: str, metadata: Dict = None):
        """Add a message to chat history"""
        db = get_db()
        
        # Update session last_active
        db.execute(
            'UPDATE chat_sessions SET last_active = CURRENT_TIMESTAMP WHERE session_id = ?',
            (session_id,)
        )
        
        # Add message
        db.execute(
            'INSERT INTO messages (session_id, role, content, metadata) VALUES (?, ?, ?, ?)',
            (session_id, role, content, json.dumps(metadata) if metadata else None)
        )
        db.commit()
    
    @staticmethod
    def get_all_sessions() -> List[Dict]:
        """Get all chat sessions"""
        db = get_db()
        sessions = db.execute(
            'SELECT * FROM chat_sessions ORDER BY last_active DESC'
        ).fetchall()
        
        return [dict(session) for session in sessions]

class ResearchCache:
    """Manage research result caching"""
    
    @staticmethod
    def get_cached_research(query: str) -> Optional[Dict]:
        """Get cached research results"""
        model = g["ENCODER"]
        query_vector = model.encode([query])

        db = get_db()
        query_cache = db.execute(
            'SELECT id, query_vector, query, results FROM research_cache WHERE expires_at > CURRENT_TIMESTAMP',
        ).fetchall()
        cache_vectors = torch.Tensor([json.loads(qc['query_vector']) for qc in query_cache])
        similarity_scores = model.similarity(query_vector, cache_vectors)
        max_score = torch.max(similarity_scores, 1)
        if max_score.values[0] >= 0.95:
            # Update access count
            max_query = max_score.indices[0].item()
            entry = query_cache[max_query]
            db.execute(
                'UPDATE research_cache SET access_count=access_count+1 WHERE id = ?',
                (entry['id'],)
            )
            db.commit()
            
            return {
                'results': json.loads(entry['results']),
                'cached_at': entry['cached_at']
            }
    
    @staticmethod
    def cache_research(query: str, results, cache_hours: int = 24):
        """Cache research results"""
        query_vector = json.dumps(g["ENCODER"].encode(query)[0].numpy().tolist())
        expires_at = datetime.now() + timedelta(hours=cache_hours)
        
        db = get_db()
        db.execute(
            '''INSERT OR REPLACE INTO research_cache 
               (query_vector, query, results, expires_at) 
               VALUES (?, ?, ?, ?, ?)''',
            (query_vector, query, json.dumps(results), expires_at)
        )
        db.commit()
    
    @staticmethod
    def cleanup_expired():
        """Remove expired cache entries"""
        db = get_db()
        db.execute('DELETE FROM research_cache WHERE expires_at < CURRENT_TIMESTAMP')
        db.commit()


class DeepResearchBot:
    """Main chatbot class with research capabilities"""
    
    def __init__(self):
        self.research_cache = ResearchCache()
        self.agent = Agent_(simulation=True)
    
    def conduct_research(self, query: str) -> Dict:
        """Conduct deep research on a query"""
        # Check cache first
        cached_result = self.research_cache.get_cached_research(query)
        if cached_result:
            cached_result["use_cache"] = True
            return cached_result
        
        # Simulate research process (replace with actual research logic)
        research_results = self.agent.research(query)
        
        # Cache results
        self.research_cache.cache_research(
            query, 
            research_results, 
        )
        
        research_results["use_cache"] = False
        return research_results

# Initialize bot
research_bot = DeepResearchBot()

# Routes
@app.route('/')
def index():
    """Main chat interface"""
    return render_template('index.html')

@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    """Get all chat sessions"""
    sessions = ChatHistory.get_all_sessions()
    return jsonify(sessions)

@app.route('/api/sessions', methods=['POST'])
def create_session():
    """Create new chat session"""
    data = request.get_json()
    title = data.get('title', 'New Chat')
    session_id = ChatHistory.create_session(title)
    return jsonify({'session_id': session_id})

@app.route('/api/sessions/<session_id>/messages', methods=['GET'])
def get_messages(session_id):
    """Get messages for a session"""
    messages = ChatHistory.get_session_history(session_id)
    return jsonify(messages)

@app.route('/api/sessions/<session_id>/messages', methods=['POST'])
def send_message(session_id):
    """Send a message and get bot response"""
    data = request.get_json()
    user_message = data.get('message', '')
    
    if not user_message:
        return jsonify({'error': 'Message cannot be empty'}), 400
    
    # Save user message
    ChatHistory.add_message(session_id, 'user', user_message)
    
    # Generate bot response
    try:
        research_result = research_bot.conduct_research(user_message)
        bot_response = research_result['results']
        
        # Save bot response with metadata
        metadata = {
            'reasoning': research_result['reasoning'],
            'cached': research_result['use_cache'],
            'research_query': user_message
        }
        ChatHistory.add_message(session_id, 'assistant', bot_response, metadata)
        
        return jsonify({
            'response': bot_response,
            'reasoning': research_result['reasoning'],
            'cached': research_result['use_cache']
        })
    
    except Exception as e:
        error_msg = f"I encountered an error while researching your question: {str(e)}"
        ChatHistory.add_message(session_id, 'assistant', error_msg)
        return jsonify({'error': error_msg}), 500

@app.route('/api/cache/stats', methods=['GET'])
def cache_stats():
    """Get cache statistics"""
    db = get_db()
    
    research_stats = db.execute(
        'SELECT COUNT(*) as count, SUM(access_count) as total_hits FROM research_cache'
    ).fetchone()
    
    return jsonify({
        'research_cache': {
            'entries': research_stats['count'],
            'total_hits': research_stats['total_hits'] or 0
        }
    })

@app.route('/api/cache/cleanup', methods=['POST'])
def cleanup_cache():
    """Cleanup expired cache entries"""
    ResearchCache.cleanup_expired()
    return jsonify({'message': 'Cache cleanup completed'})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5002)