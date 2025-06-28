import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

import uuid
from analytics import generate_short_id, generate_user_id, record_user_event, execute_query
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_chroma import Chroma
from langchain.text_splitter import CharacterTextSplitter
from fastapi.staticfiles import StaticFiles
from langchain.chains import RetrievalQA
from langchain.chains import ConversationalRetrievalChain
from langchain_core.documents import Document

from langchain.prompts import PromptTemplate
import json
import time
from collections import defaultdict
import mysql.connector
from mysql.connector import Error
import json as json_lib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import hashlib
from analytics import router as analytics_router
import glob

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Initialize FastAPI with WebSocket support
app = FastAPI(title="Google Gen AI RAG App with ChromaDB")


# Add CORS middleware with specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Add your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add this function to get the latest processed CSV file
def get_latest_processed_file():
    processed_dir = os.path.join("data", "processed")
    csv_files = glob.glob(os.path.join(processed_dir, "*Processed.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No processed CSV files found in {processed_dir}")
    latest_file = max(csv_files, key=os.path.getmtime)
    return latest_file

# Prepare embeddings
EMBED_MODEL = os.getenv("EMBED_MODEL", "models/embedding-001")
embeddings = GoogleGenerativeAIEmbeddings(model=EMBED_MODEL, google_api_key=os.getenv("GEMINI_API_KEY"))

# Initialize ChromaDB vector store
PERSIST_DIRECTORY = os.getenv("PERSIST_DIRECTORY", "chroma_db")

def get_vector_store():
    # Check if vector store already exists
    if os.path.exists(PERSIST_DIRECTORY):
        print("Loading existing vector store...")
        vector_store = Chroma(
            persist_directory=PERSIST_DIRECTORY,
            embedding_function=embeddings
        )
    else:
        print("Creating new vector store...")
        vector_store = Chroma(
            persist_directory=PERSIST_DIRECTORY,
            embedding_function=embeddings
        )
    return vector_store

# Ingest the latest processed file into the vector store
print(f"Current working directory: {os.getcwd()}")
try:
    CSV_PATH = get_latest_processed_file()
    print(f"Auto-selected latest processed file: {CSV_PATH}")
except Exception as e:
    raise FileNotFoundError(f"Could not find a processed CSV file: {e}")

vector_store = get_vector_store()

# Ingest new data into the existing vector store
print(f"Ingesting data from: {CSV_PATH}")
df = pd.read_csv(CSV_PATH)
splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
documents = []
for idx, row in df.iterrows():
    row_dict = row.to_dict()
    content = "\n".join([f"{k}: {v}" for k, v in row_dict.items()])
    chunks = splitter.split_text(content)
    for chunk in chunks:
        documents.append(Document(page_content=chunk))
print(f"Created {len(documents)} document chunks")
ids = [str(uuid.uuid4()) for _ in documents]
vector_store.add_documents(documents=documents, ids=ids)
print("✅ Vector store updated and persisted with latest data.")

# Initialize LLM
llm = ChatGoogleGenerativeAI(
    model=os.getenv("LLM_MODEL", "gemini-2.0-flash"),
    google_api_key=os.getenv("GEMINI_API_KEY"),
    disable_streaming=True  # Changed from streaming=False
)

# Define system prompt
SYSTEM_PROMPT = PromptTemplate(
    input_variables=["context", "question", "chat_history"],
    template="""You are a helpful assistant specialized in answering questions about stocks, finance, and investments. Your role is to:
## Answer as you are talking to the user and don't mentioned that "as the data says", Talk from your own point of view
1. Help users research and understand stocks, companies, financial markets, and investment concepts.
2. Respond in the user's language, matching the language of their prompt.
3. Provide accurate, concise, and up-to-date information about stock prices, company performance, market trends, and financial news.
4. Guide users in finding reliable sources, interpreting financial data, and understanding investment risks.
5. Be professional, clear, and helpful in your responses.
6. Provide stock advice and recommendations based on the data and information provided.
7. Focus on factual information from the provided data and reputable sources.
8. Avoid discussing unrelated topics or providing medical, legal, or tax advice.

Context: {context}
Chat History: {chat_history}
Question: {question}

Answer:"""
)

# Store chat histories for different sessions
chat_histories = {}

# Add analytics storage
user_analytics = defaultdict(lambda: {
    "sessions": 0,
    "chatbot_opens": 0, 
    "questions_asked": 0,
    "last_active": None,
    "session_history": []
})

# Pydantic model for query
class QueryRequest(BaseModel):
    question: str
    session_id: str = None

@app.post("/query")
async def query_qa(req: QueryRequest):
    # Build retriever
    retriever = vector_store.as_retriever(search_kwargs={"k": 5})
    
    # Use session_id to maintain separate chat histories
    session_id = req.session_id or "default"
    
    if session_id not in chat_histories:
        chat_histories[session_id] = []
    
    # Use ConversationalRetrievalChain instead of RetrievalQA
    qa = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        # return_source_documents=True,
        combine_docs_chain_kwargs={"prompt": SYSTEM_PROMPT}
    )
    
    try:
        # Get answer using chat history
        result = qa({
            "question": req.question,
            "chat_history": chat_histories[session_id]
        })
        answer = result["answer"]
        
        # Update chat history with the new Q&A pair
        chat_histories[session_id].append((req.question, answer))
        
        # Limit chat history length to prevent context overflow
        if len(chat_histories[session_id]) > 10:
            chat_histories[session_id] = chat_histories[session_id][-10:]
        
        # Get source documents
        # source_docs = result.get("source_documents", [])
        # sources = [doc.metadata["source"] for doc in source_docs]
        
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Register the analytics router
app.include_router(analytics_router)

@app.websocket("/ws")
async def websocket_endpoint_ws(websocket: WebSocket):
    try:
        print("New WebSocket connection attempt...")
        await websocket.accept()
        print("WebSocket connection accepted")
        
        # Create a unique session ID for this WebSocket connection
        session_id = generate_short_id()
        user_id = generate_user_id()  # Generate a meaningful user ID
        session_start_time = datetime.now()
        chat_histories[session_id] = []
        print(f"Created new session: {session_id} for user: {user_id}")
        
        # Get client info
        client = websocket.client
        page_url = "unknown"  # Default value
        
        # Record session start
        record_user_event(
            user_id=user_id,
            session_id=session_id,
            event_type="session_start",
            event_data={
                "page_url": page_url,
                "timestamp": session_start_time.isoformat(),
                "connection_type": "websocket",
                "client_info": {
                    "host": client.host if hasattr(client, 'host') else 'unknown',
                    "port": client.port if hasattr(client, 'port') else 'unknown'
                }
            }
        )
        
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                print(f"Received message from client: {data[:100]}...")
                message = json.loads(data)
                
                # Update page URL if provided in the message
                if "page_url" in message:
                    page_url = message["page_url"]
                    # Update session with page URL
                    execute_query(
                        """
                        UPDATE sessions 
                        SET page_url = %s 
                        WHERE session_id = %s
                        """,
                        (page_url, session_id),
                        fetch=False
                    )
                
                # Extract user_id from message if provided
                if "user_id" in message and message["user_id"]:
                    new_user_id = message["user_id"]
                    
                    # First ensure the user exists by recording the identification event
                    record_user_event(
                        new_user_id,
                        session_id,
                        "user_identified",
                        {
                            "timestamp": datetime.now().isoformat(),
                            "previous_id": user_id
                        }
                    )
                    
                    # Now that we know the user exists, update the session
                    execute_query(
                        """
                        UPDATE sessions 
                        SET user_id = %s 
                        WHERE session_id = %s
                        """,
                        (new_user_id, session_id),
                        fetch=False
                    )
                    
                    user_id = new_user_id
                
                # Process the message
                if "user_input" in message:
                    message_start_time = datetime.now()
                    print(f"Processing user input: {message['user_input'][:50]}...")
                    
                    # Record the user's question
                    record_user_event(
                        user_id,
                        session_id,
                        "question_asked",
                        {
                            "question": message["user_input"],
                            "timestamp": message_start_time.isoformat(),
                            "chat_history_length": len(chat_histories[session_id])
                        }
                    )

                    # Check if conversation exists for this session
                    conversation = execute_query(
                        """
                        SELECT conversation_id 
                        FROM conversations 
                        WHERE session_id = %s AND status = 'active'
                        """,
                        (session_id,)
                    )

                    if not conversation:
                        # Create new conversation if none exists
                        conversation_id = str(uuid.uuid4())
                        execute_query(
                            """
                            INSERT INTO conversations 
                            (conversation_id, session_id, user_id, start_time, status)
                            VALUES (%s, %s, %s, %s, 'active')
                            """,
                            (conversation_id, session_id, user_id, message_start_time.isoformat()),
                            fetch=False
                        )
                    else:
                        conversation_id = conversation[0]['conversation_id']

                    # Get chat history from message
                    chat_history = message.get("chat_history", [])
                    if chat_history:
                        formatted_history = [(msg["content"], "") for msg in chat_history if msg["role"] == "user"]
                        chat_histories[session_id] = formatted_history
                    
                    # Build retriever
                    retriever = vector_store.as_retriever(search_kwargs={"k": 5})
                    
                    # Use ConversationalRetrievalChain
                    qa = ConversationalRetrievalChain.from_llm(
                        llm=llm,
                        retriever=retriever,
                        # return_source_documents=True,
                        combine_docs_chain_kwargs={"prompt": SYSTEM_PROMPT}
                    )
                    
                    try:
                        # Get answer using chat history
                        result = qa({
                            "question": message["user_input"],
                            "chat_history": chat_histories[session_id]
                        })
                        answer = result["answer"]
                        response_time = (datetime.now() - message_start_time).total_seconds()
                        
                        # Record the bot's response
                        record_user_event(
                            user_id,
                            session_id,
                            "bot_response",
                            {
                                "response": answer,
                                "timestamp": datetime.now().isoformat(),
                                "response_time": response_time
                            }
                        )

                        # Update chat history
                        chat_histories[session_id].append((message["user_input"], answer))
                        
                        # Update message count in sessions table (count each interaction as 1)
                        execute_query(
                            """
                            UPDATE sessions 
                            SET message_count = message_count + 1,
                                last_message_time = %s
                            WHERE session_id = %s
                            """,
                            (datetime.now().isoformat(), session_id),
                            fetch=False
                        )
                        
                        # Limit chat history length
                        if len(chat_histories[session_id]) > 10:
                            chat_histories[session_id] = chat_histories[session_id][-10:]
                        
                        # Send response back to client
                        response = {
                            "text": answer,
                            "done": True
                        }
                        await websocket.send_json(response)
                        print(f"Response sent successfully for session {session_id}")
                    except Exception as e:
                        error_msg = f"Error processing request: {str(e)}"
                        print(error_msg)
                        
                        # Record error event
                        record_user_event(
                            user_id,
                            session_id,
                            "error",
                            {
                                "error": str(e),
                                "timestamp": datetime.now().isoformat(),
                                "question": message["user_input"]
                            }
                        )
                        
                        await websocket.send_json({
                            "error": error_msg,
                            "done": True
                        })
            except WebSocketDisconnect:
                print(f"WebSocket disconnected for session {session_id}")
                session_end_time = datetime.now()
                session_duration = (session_end_time - session_start_time).total_seconds()
                
                # Update session with end time and duration
                execute_query(
                    """
                    UPDATE sessions 
                    SET end_time = %s,
                        duration = %s,
                        status = 'completed'
                    WHERE session_id = %s
                    """,
                    (session_end_time.isoformat(), session_duration, session_id),
                    fetch=False
                )
                
                record_user_event(
                    user_id,
                    session_id,
                    "session_end",
                    {
                        "timestamp": session_end_time.isoformat(),
                        "total_messages": len(chat_histories[session_id]),
                        "duration": session_duration
                    }
                )
                break
            except Exception as e:
                print(f"Error in WebSocket loop: {str(e)}")
                if user_id:
                    record_user_event(
                        user_id,
                        session_id,
                        "error",
                        {
                            "error": str(e),
                            "timestamp": datetime.now().isoformat(),
                            "type": "websocket_error"
                        }
                    )
                await websocket.send_json({
                    "error": f"Internal server error: {str(e)}",
                    "done": True
                })
                break
    except Exception as e:
        print(f"Fatal WebSocket error: {str(e)}")
    finally:
        print(f"Cleaning up session {session_id}")
        if session_id in chat_histories:
            del chat_histories[session_id]
        try:
            await websocket.close()
        except:
            pass

# Keep the original endpoint for backward compatibility
@app.websocket("/ws/chat")
async def websocket_endpoint_chat(websocket: WebSocket):
    await websocket_endpoint_ws(websocket)

# Add a root endpoint for testing
@app.get("/")
async def root():
    return {"message": "API is running"}

class Person:
    def __init__(self, name, age):
        self.name = name
        self.age = age

    def greet(self):
        print("Hello my name is {self,name} and age is ")

# Update the sessions table schema
def update_sessions_table():
    try:
        # Check if columns exist first
        columns = execute_query("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'sessions' 
            AND TABLE_SCHEMA = DATABASE()
        """)
        existing_columns = [col['COLUMN_NAME'] for col in columns]

        # Add columns if they don't exist
        if 'message_count' not in existing_columns:
            execute_query("""
                ALTER TABLE sessions
                ADD COLUMN message_count INT DEFAULT 0
            """, fetch=False)

        if 'last_message_time' not in existing_columns:
            execute_query("""
                ALTER TABLE sessions
                ADD COLUMN last_message_time DATETIME
            """, fetch=False)

        if 'status' not in existing_columns:
            execute_query("""
                ALTER TABLE sessions
                ADD COLUMN status ENUM('active', 'completed', 'error') DEFAULT 'active'
            """, fetch=False)

        print("Sessions table schema updated successfully")
    except Error as e:
        print(f"Error updating sessions table: {e}")
        # Don't raise HTTPException here as this is a startup function

# Call this when the app starts
update_sessions_table()

def update_vector_store():
    """Update the vector store with the latest processed data."""
    try:
        latest_file = get_latest_processed_file()
        if not latest_file:
            print("No new data to ingest")
            return
            
        print(f"📊 Ingesting latest processed file: {latest_file}")
        
        # Load the latest processed data
        df = pd.read_csv(latest_file)
        
        # Split text into chunks
        splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        
        # Process all columns of the CSV
        documents = []
        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            content = "\n".join([f"{k}: {v}" for k, v in row_dict.items()])
            chunks = splitter.split_text(content)
            for chunk in chunks:
                documents.append(Document(page_content=chunk))
        
        print(f"Created {len(documents)} document chunks")
        
        # Generate unique IDs for documents
        ids = [str(uuid.uuid4()) for _ in documents]
        
        # Add new documents to existing vector store
        vector_store.add_documents(documents=documents, ids=ids)        
        print("✅ Successfully updated vector store with new data")
        
    except Exception as e:
        print(f"❌ Error updating vector store: {str(e)}")

def cleanup_old_data():
    """Remove data older than 7 days from the vector store."""
    try:
        # Get all document IDs and their metadata
        collection = vector_store._collection
        all_ids = collection.get()['ids']
        all_metadatas = collection.get()['metadatas']
        
        # Get current time
        current_time = datetime.now()
        
        # Find documents older than 7 days
        old_ids = []
        for idx, metadata in enumerate(all_metadatas):
            if metadata and 'timestamp' in metadata:
                doc_time = datetime.fromisoformat(metadata['timestamp'])
                if (current_time - doc_time) > timedelta(days=7):
                    old_ids.append(all_ids[idx])
        
        if old_ids:
            # Delete old documents
            collection.delete(ids=old_ids)
            print(f"🧹 Cleaned up {len(old_ids)} old documents")
        
    except Exception as e:
        print(f"❌ Error cleaning up old data: {str(e)}")

# Add a new endpoint to trigger data update
@app.post("/update-data")
async def update_data():
    """Endpoint to trigger data update and cleanup."""
    try:
        update_vector_store()
        cleanup_old_data()
        return {"status": "success", "message": "Data updated and cleaned successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    print("Starting server on http://0.0.0.0:9000")
    uvicorn.run(app, host="0.0.0.0", port=9000)


