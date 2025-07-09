import os
import sqlite3
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, g
from werkzeug.security import generate_password_hash
import hashlib
import requests
from typing import Dict, List, Optional

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['DATABASE'] = 'chatbot.db'

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
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT,
                FOREIGN KEY (session_id) REFERENCES chat_sessions (session_id)
            );

            CREATE TABLE IF NOT EXISTS research_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_hash TEXT UNIQUE NOT NULL,
                query TEXT NOT NULL,
                results TEXT NOT NULL,
                source_urls TEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                access_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS resource_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL,
                content_type TEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                size INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_research_cache_hash ON research_cache(query_hash);
            CREATE INDEX IF NOT EXISTS idx_resource_cache_url ON resource_cache(url);
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

def hash_query(query: str) -> str:
    """Generate hash for query caching"""
    return hashlib.md5(query.lower().strip().encode()).hexdigest()

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
        query_hash = hash_query(query)
        db = get_db()
        
        result = db.execute(
            'SELECT * FROM research_cache WHERE query_hash = ? AND expires_at > CURRENT_TIMESTAMP',
            (query_hash,)
        ).fetchone()
        
        if result:
            # Update access count
            db.execute(
                'UPDATE research_cache SET access_count = access_count + 1 WHERE id = ?',
                (result['id'],)
            )
            db.commit()
            
            return {
                'results': json.loads(result['results']),
                'source_urls': json.loads(result['source_urls']) if result['source_urls'] else [],
                'cached_at': result['cached_at']
            }
        return None
    
    @staticmethod
    def cache_research(query: str, results: List[Dict], source_urls: List[str] = None, cache_hours: int = 24):
        """Cache research results"""
        query_hash = hash_query(query)
        expires_at = datetime.now() + timedelta(hours=cache_hours)
        
        db = get_db()
        db.execute(
            '''INSERT OR REPLACE INTO research_cache 
               (query_hash, query, results, source_urls, expires_at) 
               VALUES (?, ?, ?, ?, ?)''',
            (query_hash, query, json.dumps(results), 
             json.dumps(source_urls) if source_urls else None, expires_at)
        )
        db.commit()
    
    @staticmethod
    def cleanup_expired():
        """Remove expired cache entries"""
        db = get_db()
        db.execute('DELETE FROM research_cache WHERE expires_at < CURRENT_TIMESTAMP')
        db.execute('DELETE FROM resource_cache WHERE expires_at < CURRENT_TIMESTAMP')
        db.commit()

class ResourceCache:
    """Manage web resource caching"""
    
    @staticmethod
    def get_cached_resource(url: str) -> Optional[Dict]:
        """Get cached web resource"""
        db = get_db()
        result = db.execute(
            'SELECT * FROM resource_cache WHERE url = ? AND expires_at > CURRENT_TIMESTAMP',
            (url,)
        ).fetchone()
        
        if result:
            return {
                'content': result['content'],
                'content_type': result['content_type'],
                'cached_at': result['cached_at']
            }
        return None
    
    @staticmethod
    def cache_resource(url: str, content: str, content_type: str = 'text/html', cache_hours: int = 6):
        """Cache web resource"""
        expires_at = datetime.now() + timedelta(hours=cache_hours)
        
        db = get_db()
        db.execute(
            '''INSERT OR REPLACE INTO resource_cache 
               (url, content, content_type, expires_at, size) 
               VALUES (?, ?, ?, ?, ?)''',
            (url, content, content_type, expires_at, len(content))
        )
        db.commit()

class DeepResearchBot:
    """Main chatbot class with research capabilities"""
    
    def __init__(self):
        self.research_cache = ResearchCache()
        self.resource_cache = ResourceCache()
    
    def conduct_research(self, query: str) -> Dict:
        """Conduct deep research on a query"""
        # Check cache first
        cached_result = self.research_cache.get_cached_research(query)
        if cached_result:
            return {
                'answer': self._generate_answer(cached_result['results']),
                'sources': cached_result['source_urls'],
                'cached': True
            }
        
        # Simulate research process (replace with actual research logic)
        research_results = self._perform_research(query)
        
        # Cache results
        self.research_cache.cache_research(
            query, 
            research_results['results'], 
            research_results.get('source_urls', [])
        )
        
        return {
            'answer': self._generate_answer(research_results['results']),
            'sources': research_results.get('source_urls', []),
            'cached': False
        }
    
    def _perform_research(self, query: str) -> Dict:
        """Perform actual research (placeholder for real implementation)"""
        # This is where you'd integrate with search APIs, web scraping, etc.
        # For now, returning mock data
        return {
            'results': [
                {
                    'title': f'Research Result for: {query}',
                    'content': f'This is simulated research content for the query: {query}',
                    'relevance': 0.95
                }
            ],
            'source_urls': ['https://example.com/research1', 'https://example.com/research2']
        }
    
    def _generate_answer(self, research_results: List[Dict]) -> str:
        """Generate answer from research results"""
        # Simple answer generation (replace with actual AI/NLP processing)
        if not research_results:
            return "I couldn't find relevant information for your query."
        
        content_parts = [result['content'] for result in research_results[:3]]
        return f"Based on my research: {' '.join(content_parts)}"

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
        bot_response = research_result['answer']
        
        # Save bot response with metadata
        metadata = {
            'sources': research_result['sources'],
            'cached': research_result['cached'],
            'research_query': user_message
        }
        ChatHistory.add_message(session_id, 'assistant', bot_response, metadata)
        
        return jsonify({
            'response': bot_response,
            'sources': research_result['sources'],
            'cached': research_result['cached']
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
    
    resource_stats = db.execute(
        'SELECT COUNT(*) as count, SUM(size) as total_size FROM resource_cache'
    ).fetchone()
    
    return jsonify({
        'research_cache': {
            'entries': research_stats['count'],
            'total_hits': research_stats['total_hits'] or 0
        },
        'resource_cache': {
            'entries': resource_stats['count'],
            'total_size': resource_stats['total_size'] or 0
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